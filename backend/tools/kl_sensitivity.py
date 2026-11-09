"""I-STUD 하중 수준 보정 기준 모멘트 M*의 허용높이 민감도 표 (v0.9.3, PRD OI-12).

배경: 2026-11-08 고정 후면 보드 피스 2 → 4개 반영 재산정에서 I-STUD M*가 1.690(시험 최대모멘트) → 0.890 kN·m로
급감하였다(`docs/screw_count_changes.md` §6). 시험 M–δ 곡선 대조 전까지 상수는 유지하되(결정 4, 2026-11-09),
M*를 바꿨을 때 허용높이가 얼마나 움직이는지 기록해 둔다.

방법
- 시편 11(I-STUD 75-06 @600, 후면 방화 25T 1P + 전면 방화 15T 3P, `tests/golden/requested_shape_cases.json`) 입력을
  기준으로 규격만 75-06 / 75-08으로 바꾼다. 그 외 조건은 시편 공통값(활하중 0.25 kN/m², L/240, 피스 600/300/300 등).
- M* 후보 {0.890(현행), 1.290(중간), 1.690(종전)}를 **엔진 상수를 바꾸지 않고** 도구 실행 중 임시 주입
  (`mock.patch.dict`)하여 비내진·내진 × 부분합성·스터드 단독의 허용높이(max_height_mm)를 구한다.
- 내진은 시편 공통 지진 입력(S 0.22, Ip 1.5, Fa 1.3)·앵커 0.4 kN/450 mm. 내진 허용높이는 런너 고정못 조건을
  포함하지 않는 `max_height_mm`(응력·처짐·피스 인장)이다.
- 시험 엑셀이 없어도 실행된다(엑셀은 `r_calibration.py --check`에만 필요).

계산엔진에서는 호출하지 않는다. 상수·판정 변경 없음.

사용:
  python -m backend.tools.kl_sensitivity                 # 표 출력(Markdown)
  python -m backend.tools.kl_sensitivity --m-star 0.89 1.29 1.69 --spec "I-STUD 75-06" "I-STUD 75-08"
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from unittest import mock

import backend.engine.calculator as calculator
from backend.engine.constants import STIFFNESS_REF_MOMENT_KNM_BY_TYPE, STIFFNESS_TYPE_I
from backend.engine.models import StudInput, WallCheckRequest
from backend.engine.repository import JsonSeedRepository, MaterialRepository
from backend.tools.r_calibration import SEED_DIR, specimen_requests

# 기준 시편(I-STUD 75-06 @600, 후면 25T 1P + 전면 15T 3P)
BASE_SPECIMEN_ID = "requested_11_i_stud_75"
STUD_GROUP = "I-STUD"
DEFAULT_SPECS: tuple[str, ...] = ("I-STUD 75-06", "I-STUD 75-08")
# M* 후보(kN·m): 현행 0.890 / 중간 1.290 / 종전(시험 최대모멘트) 1.690
DEFAULT_M_STAR_KNM: tuple[float, ...] = (STIFFNESS_REF_MOMENT_KNM_BY_TYPE[STIFFNESS_TYPE_I], 1.290, 1.690)
DESIGN_CASES: tuple[tuple[str, str], ...] = (("non_seismic", "비내진"), ("seismic", "내진"))
STRENGTH_MODES: tuple[tuple[str, str], ...] = (
  (calculator.STRENGTH_CHECK_COMPOSITE, "부분합성"),
  (calculator.STRENGTH_CHECK_STUD_ONLY, "스터드 단독"),
)


@dataclass(frozen=True)
class SensitivityRow:
  spec: str
  m_star_kNm: float
  design_case_label: str
  strength_mode_label: str
  max_height_mm: float
  # 허용높이에서의 하중 수준 보정 k_L과 M_L/M* 활용도(intermediate)
  load_factor: float
  moment_utilization: float
  governing: str


@contextmanager
def injected_reference_moment(m_star_kNm: float) -> Iterator[None]:
  """도구 실행 중에만 I-STUD M*를 m_star_kNm로 바꾼다(상수 파일 불변)."""
  with mock.patch.dict(calculator.STIFFNESS_REF_MOMENT_KNM_BY_TYPE, {STIFFNESS_TYPE_I: float(m_star_kNm)}):
    yield


def base_request(spec: str) -> WallCheckRequest:
  request = specimen_requests()[BASE_SPECIMEN_ID]
  if request.stud.stud_type != STUD_GROUP:
    raise ValueError(f"기준 시편 {BASE_SPECIMEN_ID}의 스터드 형식이 {STUD_GROUP}이 아닙니다: {request.stud.stud_type}")
  return replace(request, stud=StudInput(stud_type=STUD_GROUP, spec=spec, method=request.stud.method))


def _governing_label(result_intermediate: dict[str, float]) -> str:
  if result_intermediate.get("stiffness_load_basis_moment", 0.0) == 1.0:
    return "M"
  return "V"


def run(
  specs: Sequence[str] = DEFAULT_SPECS,
  m_stars: Sequence[float] = DEFAULT_M_STAR_KNM,
  repository: MaterialRepository | None = None,
) -> list[SensitivityRow]:
  repo = repository or JsonSeedRepository(SEED_DIR)
  rows: list[SensitivityRow] = []
  for spec in specs:
    base = base_request(spec)
    for m_star in m_stars:
      with injected_reference_moment(m_star):
        for design_case, case_label in DESIGN_CASES:
          for mode, mode_label in STRENGTH_MODES:
            request = replace(base, design_case=design_case, strength_check_mode=mode)
            result = calculator.calculate_wall_check(request, repo)
            # 허용높이에서의 k_L·활용도: 산정 높이로 1회 재계산
            at_height = calculator._calculate_wall_check_once(replace(request, span_mm=result.max_height_mm), repo)
            rows.append(
              SensitivityRow(
                spec=spec,
                m_star_kNm=float(m_star),
                design_case_label=case_label,
                strength_mode_label=mode_label,
                max_height_mm=result.max_height_mm,
                load_factor=float(at_height.intermediate.get("stiffness_load_factor", float("nan"))),
                moment_utilization=float(at_height.intermediate.get("moment_utilization_ratio", float("nan"))),
                governing=_governing_label(dict(at_height.intermediate)),
              )
            )
  return rows


def markdown_table(rows: Sequence[SensitivityRow], m_stars: Sequence[float]) -> str:
  """규격 × (케이스·강도모드) 행, M* 열의 허용높이 표(mm). 괄호는 허용높이에서의 k_L."""
  current = STIFFNESS_REF_MOMENT_KNM_BY_TYPE[STIFFNESS_TYPE_I]
  headers = ["규격", "검토", "강도 산정"] + [
    f"M* {m:.3f}{' (현행)' if abs(m - current) < 1e-9 else ' (종전)' if abs(m - 1.690) < 1e-9 else ''}" for m in m_stars
  ]
  lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
  keys = sorted({(r.spec, r.design_case_label, r.strength_mode_label) for r in rows}, key=lambda k: (k[0], k[1] != "비내진", k[2] != "부분합성"))
  for spec, case_label, mode_label in keys:
    cells = [spec, case_label, mode_label]
    for m in m_stars:
      row = next(r for r in rows if r.spec == spec and r.design_case_label == case_label and r.strength_mode_label == mode_label and abs(r.m_star_kNm - m) < 1e-9)
      cells.append(f"{row.max_height_mm:,.0f} (k_L {row.load_factor:.3f}, M_L/M* {row.moment_utilization:.2f}, {row.governing})")
    lines.append("| " + " | ".join(cells) + " |")
  return "\n".join(lines)


def main() -> None:
  parser = argparse.ArgumentParser(description="I-STUD M* 허용높이 민감도 표(상수 불변, 임시 주입)")
  parser.add_argument("--spec", nargs="+", default=list(DEFAULT_SPECS), help="I-STUD 규격명(자재 DB name)")
  parser.add_argument("--m-star", nargs="+", type=float, default=list(DEFAULT_M_STAR_KNM), help="M* 후보(kN·m)")
  args = parser.parse_args()
  rows = run(args.spec, args.m_star)
  print(markdown_table(rows, args.m_star))
  print()
  print(f"현행 상수 M*(I-STUD) = {STIFFNESS_REF_MOMENT_KNM_BY_TYPE[STIFFNESS_TYPE_I]:.3f} kN·m (변경 없음). k_L: 허용높이에서의 하중 수준 보정, M/V: 지배 활용도")


if __name__ == "__main__":
  main()
