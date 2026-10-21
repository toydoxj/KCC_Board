"""I-STUD 유효단면계수 Se 산정 — AISI S100-16 Appendix 1 (유효폭법).

단면(stud.dxf 폐합 폴리라인과 면적 일치하는 직사각형 분해, 강축 휨):
- 웨브 1겹(t), 폭 중앙(x = B/2 ± t/2).
- 웨브 한쪽 플랜지(폭 B/2 − t/2)는 2겹(외판 + 내판, 각 t).
- 반대쪽 플랜지는 외판 1겹, 자유단 HEM(3 mm) 구간만 내판(hem)이 있다.
- 상하 대칭이므로 상부 압축 1방향만 산정한다.

유효폭 가정(종전 독립 거동 DB Se를 0.72% 이내로 재현하는 모델, 2026-10-21):
- 1겹 플랜지: 비보강 요소(App.1 1.2.1, k = 0.43), 평판 폭 = hem 끝~웨브면. hem 구간 외판은 유효, hem 내판은 무효.
- 2겹 플랜지: 비보강 요소, 평판 폭 = 웨브면~자유단.
  · 일체(integral, 2026-10-21 사용자 확정): 두께 2t 판 1장.
  · 독립(independent, 종전 하한): 두께 t 판 2장.
- 웨브: 응력경사 보강 요소(App.1 1.1.2), 평판 높이 = H − 4t(2겹 플랜지 안쪽).
- 압축 플랜지 응력 f = Fy(App.1 §1.1(a), 압축 연단 선항복 — 인장 연단 선항복이면 예외). 웨브 f1·f2 = 선형 분포.
- 웨브 b2 식은 h0/b0 ≤ 4 범위만 구현(초과 시 예외).
- E = 계산엔진 STUD_ELASTIC_MODULUS, Fy = 자재 DB 기본 강재 Fy.

사용:
  python -m backend.tools.se_istud            # 산정표 출력
  python -m backend.tools.se_istud --check    # 시드 Se와 대조(불일치 시 종료코드 1)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.engine.constants import STUD_ELASTIC_MODULUS

I_STUD_GROUP = "I-STUD"
# stud.dxf I-STUD 단면: 1겹 플랜지 자유단 hem(내판) 길이(mm)
I_STUD_HEM_LENGTH_MM = 3.0
# 비보강 요소 판좌굴계수 (AISI S100-16 App.1 1.2.1)
UNSTIFFENED_K = 0.43
# 응력경사 웨브 b2 식 적용 한계 h0/b0 (App.1 1.1.2, h0 = 외측 전체 높이, b0 = 외측 플랜지 폭)
WEB_DEPTH_TO_FLANGE_LIMIT = 4.0
# 반복 수렴 조건
_MAX_ITERATIONS = 500
_TOLERANCE_MM = 1e-10

PlyMode = Literal["integral", "independent"]
_Rect = tuple[float, float, float, float]  # (x0, x1, y0, y1)


@dataclass(frozen=True)
class ISectionResult:
  name: str
  A_gross: float
  Ix_gross: float
  Se: float
  neutral_axis_mm: float


def _rho(lam: float) -> float:
  """유효폭 계수 ρ (App.1 Eq. 1.1-2)."""
  return 1.0 if lam <= 0.673 else (1.0 - 0.22 / lam) / lam


def _slenderness(k: float, w: float, t: float, f: float, E: float) -> float:
  """세장비 λ (App.1 Eq. 1.1-4)."""
  return 1.052 / math.sqrt(k) * (w / t) * math.sqrt(f / E)


def _rects(H: float, B: float, t: float, mode: PlyMode, Fy: float, E: float, na: float | None) -> list[_Rect]:
  """유효 직사각형 목록. na=None이면 총단면."""
  xw0, xw1 = B / 2 - t / 2, B / 2 + t / 2
  hem = I_STUD_HEM_LENGTH_MM
  # 하부(인장) 플랜지·웨브 위 외판 — 항상 유효
  rects: list[_Rect] = [(0.0, B, 0.0, t), (xw1, B, t, 2 * t), (0.0, hem, t, 2 * t), (xw0, xw1, H - t, H)]
  if na is None:
    rects += [(0.0, xw0, H - t, H), (0.0, hem, H - 2 * t, H - t), (xw1, B, H - 2 * t, H), (xw0, xw1, t, H - t)]
    return rects

  def stress(y: float) -> float:
    return Fy * (y - na) / (H - na)

  # 1겹 플랜지(좌측): hem 끝~웨브면, 웨브측에서 유효폭
  w_single = xw0 - hem
  b_single = _rho(_slenderness(UNSTIFFENED_K, w_single, t, Fy, E)) * w_single
  rects += [(xw0 - b_single, xw0, H - t, H), (0.0, hem, H - t, H)]
  # 2겹 플랜지(우측)
  w_double = B - xw1
  if mode == "integral":
    b = _rho(_slenderness(UNSTIFFENED_K, w_double, 2 * t, Fy, E)) * w_double
    rects.append((xw1, xw1 + b, H - 2 * t, H))
  elif mode == "independent":
    for y0 in (H - t, H - 2 * t):
      b = _rho(_slenderness(UNSTIFFENED_K, w_double, t, Fy, E)) * w_double
      rects.append((xw1, xw1 + b, y0, y0 + t))
  else:
    raise ValueError(f"알 수 없는 2겹 거동 모드: {mode}")
  # 웨브: 평판 y = 2t ~ H − 2t, 응력경사 (App.1 1.1.2)
  y_bot, y_top = 2 * t, H - 2 * t
  h = y_top - y_bot
  if H / B > WEB_DEPTH_TO_FLANGE_LIMIT:
    raise ValueError(f"h0/b0 = {H / B:.2f} > {WEB_DEPTH_TO_FLANGE_LIMIT:g}: App.1 1.1.2 b2 식 범위 밖")
  f1, f2 = stress(y_top), stress(y_bot)
  psi = abs(f2 / f1)
  k = 4 + 2 * (1 + psi) ** 3 + 2 * (1 + psi)
  be = _rho(_slenderness(k, h, t, f1, E)) * h
  b1 = be / (3 + psi)
  b2 = be / 2 if psi > 0.236 else be - b1
  if b1 + b2 >= y_top - na:
    rects.append((xw0, xw1, t, H - t))
  else:
    rects += [(xw0, xw1, t, na + b2), (xw0, xw1, y_top - b1, H - t)]
  return rects


def _props(rects: list[_Rect]) -> tuple[float, float, float]:
  """(A, 도심 y, 도심축 I)."""
  A = sum((x1 - x0) * (y1 - y0) for x0, x1, y0, y1 in rects)
  yc = sum((x1 - x0) * (y1 - y0) * (y0 + y1) / 2 for x0, x1, y0, y1 in rects) / A
  I = sum((x1 - x0) * (y1 - y0) ** 3 / 12 + (x1 - x0) * (y1 - y0) * ((y0 + y1) / 2 - yc) ** 2 for x0, x1, y0, y1 in rects)
  return A, yc, I


def compute_i_stud_se(name: str, H: float, B: float, t: float, Fy: float, mode: PlyMode = "integral", E: float = STUD_ELASTIC_MODULUS) -> ISectionResult:
  A_gross, _, I_gross = _props(_rects(H, B, t, mode, Fy, E, None))
  na = H / 2
  for _ in range(_MAX_ITERATIONS):
    _, yc, I = _props(_rects(H, B, t, mode, Fy, E, na))
    if abs(yc - na) < _TOLERANCE_MM:
      break
    na = yc
  else:
    raise RuntimeError(f"{name}: 유효 중립축이 수렴하지 않았습니다.")
  if yc > H - yc:
    raise RuntimeError(f"{name}: 인장 연단 선항복 — 압축 연단 응력 Fy 가정이 성립하지 않습니다.")
  return ISectionResult(name=name, A_gross=A_gross, Ix_gross=I_gross, Se=I / (H - yc), neutral_axis_mm=yc)


def _default_fy(seed_dir: Path) -> float:
  data = json.loads((seed_dir / "stud_steel.json").read_text(encoding="utf-8"))
  items = data["items"] if isinstance(data, dict) else data
  defaults = [item for item in items if item.get("is_default")]
  if len(defaults) != 1:
    raise ValueError(f"기본 스터드 강재가 정확히 1개가 아닙니다: {len(defaults)}개")
  return float(defaults[0]["Fy"])


def compute_seed_i_studs(seed_dir: Path) -> list[tuple[dict, ISectionResult]]:
  """시드의 I-STUD 전 규격 Se(일체)를 산정한다. 총단면 A가 시드와 0.1% 넘게 다르면 예외."""
  Fy = _default_fy(seed_dir)
  data = json.loads((seed_dir / "stud_section.json").read_text(encoding="utf-8"))
  rows = []
  for item in data["items"]:
    if item["group"] != I_STUD_GROUP:
      continue
    result = compute_i_stud_se(item["name"], float(item["H"]), float(item["B"]), float(item["t"]), Fy)
    if not math.isclose(result.A_gross, float(item["A"]), rel_tol=1e-3):
      raise ValueError(f"{item['name']}: 직사각형 분해 A {result.A_gross:.2f} ≠ 시드 A {item['A']}")
    rows.append((item, result))
  if not rows:
    raise ValueError("시드에 I-STUD 규격이 없습니다.")
  return rows


def main() -> None:
  parser = argparse.ArgumentParser(description="I-STUD 유효단면계수 Se(2겹 일체) 산정")
  parser.add_argument("--seed-dir", default="data/seed")
  parser.add_argument("--check", action="store_true", help="시드 Se와 대조")
  args = parser.parse_args()
  rows = compute_seed_i_studs(Path(args.seed_dir))
  mismatch = 0
  print(f"{'규격':16s} {'A':>8s} {'Ix':>10s} {'Sx':>7s} {'Se_seed':>8s} {'Se_calc':>8s} {'Se/Sx':>6s}")
  for item, r in rows:
    se_calc = round(r.Se)
    if se_calc != item.get("Se"):
      mismatch += 1
    print(f"{item['name']:16s} {r.A_gross:8.2f} {r.Ix_gross:10.0f} {item['Sx']:7d} {item.get('Se')!s:>8s} {se_calc:8d} {r.Se / item['Sx']:6.3f}")
  if args.check and mismatch:
    print(f"불일치 {mismatch}건", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
  main()
