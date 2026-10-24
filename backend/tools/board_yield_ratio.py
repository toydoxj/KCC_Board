"""석고보드 항복비 Fy/Fu = Py/Pu 산정 — 휨-변위 곡선의 연속 이선형 근사 꺾임점(심사의견 B-3).

입력: KCC 휨실험 결과 정리 엑셀(시트 1장 = 시험체 1개). 3행부터 A열 = 하중, D열 = 변위.
CHART로 시작하는 시트와 '정리' 시트는 제외한다.

알고리즘(시험체별):
1. 원점(첫 행)~최대하중 행 구간 (x = 변위, y = 하중)을 취한다.
2. 꺾임점 후보 xb = x[j] (j = 3 … n − 4)마다 연속 이선형
   y = a + k1·min(x, xb) + k2·max(x − xb, 0)을 최소제곱으로 근사한다.
3. 잔차제곱합(SSE)이 최소인 xb의 근사 하중 Py = a + k1·xb를 항복하중으로 한다.
4. 항복비 = Py / Pu. 종류·두께별로 시험체 평균을 낸다.

시트 이름 '<종류> <두께>.<번호>' 또는 '<종류> <두께>-<번호>'에서 종류·두께를 읽는다
(예: '방화 12.5-1' → 방화 12.5, '고강도 12.5.0' → 고강도일반 12.5).

계산엔진에서는 호출하지 않는다(재현성 확보용). 엑셀 원본은 저장소에 넣지 않는다.

사용:
  python -m backend.tools.board_yield_ratio <엑셀 경로>           # 산정표 출력
  python -m backend.tools.board_yield_ratio <엑셀 경로> --check   # constants 시험값과 대조(불일치 시 종료코드 1)
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from backend.engine.constants import BOARD_YIELD_RATIO_BY_BOARD
from backend.tools.xlsx_reader import Sheet, numeric_column_pairs, read_workbook

DATA_FIRST_ROW = 3
LOAD_COLUMN = 1  # A열
DISPLACEMENT_COLUMN = 4  # D열
# 꺾임점 후보에서 양 끝 제외 점 수(각 직선에 최소 점 수 확보)
BREAKPOINT_EDGE_POINTS = 3
# 시트 이름의 종류 표기 → 자재 DB 종류
SHEET_KIND_ALIASES = {"고강도": "고강도일반"}
EXCLUDED_SHEET_NAMES = frozenset({"정리"})
EXCLUDED_SHEET_PREFIX = "CHART"
_SHEET_NAME = re.compile(r"^(\S+) (\d+(?:\.5)?)[.-]\d+$")
TEST_SOURCE = "시험"


@dataclass(frozen=True)
class BilinearFit:
  breakpoint_x: float
  intercept: float
  slope_before: float
  slope_after: float
  sse: float

  @property
  def breakpoint_y(self) -> float:
    return self.intercept + self.slope_before * self.breakpoint_x


@dataclass(frozen=True)
class SpecimenResult:
  sheet: str
  board_key: tuple[str, float]
  ultimate_load: float
  yield_load: float
  fit: BilinearFit

  @property
  def ratio(self) -> float:
    return self.yield_load / self.ultimate_load


def _solve_linear(matrix: list[list[float]], rhs: list[float]) -> list[float]:
  """가우스 소거(부분 피벗). 특이행렬이면 예외."""
  size = len(rhs)
  augmented = [row[:] + [rhs[index]] for index, row in enumerate(matrix)]
  for pivot in range(size):
    best = max(range(pivot, size), key=lambda row: abs(augmented[row][pivot]))
    if abs(augmented[best][pivot]) < 1e-12:
      raise ValueError("이선형 근사 정규방정식이 특이행렬입니다(꺾임점 후보 점 부족).")
    augmented[pivot], augmented[best] = augmented[best], augmented[pivot]
    for row in range(size):
      if row != pivot:
        factor = augmented[row][pivot] / augmented[pivot][pivot]
        augmented[row] = [a - factor * b for a, b in zip(augmented[row], augmented[pivot])]
  return [augmented[index][size] / augmented[index][index] for index in range(size)]


def fit_bilinear_at(x: Sequence[float], y: Sequence[float], breakpoint_x: float) -> BilinearFit:
  """꺾임점 xb를 고정한 연속 이선형 최소제곱 근사."""
  columns = (
    [1.0] * len(x),
    [min(value, breakpoint_x) for value in x],
    [max(value - breakpoint_x, 0.0) for value in x],
  )
  normal = [[sum(a * b for a, b in zip(ci, cj)) for cj in columns] for ci in columns]
  rhs = [sum(a * b for a, b in zip(ci, y)) for ci in columns]
  intercept, slope_before, slope_after = _solve_linear(normal, rhs)
  sse = sum(
    (intercept + slope_before * u + slope_after * w - target) ** 2
    for u, w, target in zip(columns[1], columns[2], y)
  )
  return BilinearFit(breakpoint_x, intercept, slope_before, slope_after, sse)


def fit_bilinear(x: Sequence[float], y: Sequence[float]) -> BilinearFit:
  """SSE 최소 꺾임점의 연속 이선형 근사. 후보는 x[3] … x[n−4]."""
  candidates = range(BREAKPOINT_EDGE_POINTS, len(x) - BREAKPOINT_EDGE_POINTS)
  if not candidates:
    raise ValueError(f"이선형 근사 점 수 부족: {len(x)}개(최소 {2 * BREAKPOINT_EDGE_POINTS + 1}개)")
  best: BilinearFit | None = None
  for index in candidates:
    fit = fit_bilinear_at(x, y, x[index])
    if best is None or fit.sse < best.sse:
      best = fit
  assert best is not None
  return best


def board_key_from_sheet(name: str) -> tuple[str, float]:
  match = _SHEET_NAME.match(name.strip())
  if match is None:
    raise ValueError(f"시트 이름에서 종류·두께를 읽을 수 없습니다: {name!r}")
  kind = SHEET_KIND_ALIASES.get(match.group(1), match.group(1))
  return kind, float(match.group(2))


def is_specimen_sheet(name: str) -> bool:
  return not name.startswith(EXCLUDED_SHEET_PREFIX) and name not in EXCLUDED_SHEET_NAMES


def analyze_specimen(name: str, sheet: Sheet) -> SpecimenResult:
  pairs = numeric_column_pairs(sheet, DATA_FIRST_ROW, LOAD_COLUMN, DISPLACEMENT_COLUMN)
  if not pairs:
    raise ValueError(f"시트 {name!r}: {DATA_FIRST_ROW}행부터 하중·변위 숫자 자료가 없습니다.")
  loads = [load for load, _ in pairs]
  peak = loads.index(max(loads))  # 최대하중 첫 행
  x = [displacement for _, displacement in pairs[: peak + 1]]
  y = loads[: peak + 1]
  fit = fit_bilinear(x, y)
  return SpecimenResult(name, board_key_from_sheet(name), loads[peak], fit.breakpoint_y, fit)


def analyze_workbook(path: Path) -> list[SpecimenResult]:
  workbook = read_workbook(path, include=is_specimen_sheet)
  return [analyze_specimen(name, sheet) for name, sheet in workbook.items()]


def group_mean_ratios(results: Sequence[SpecimenResult]) -> dict[tuple[str, float], list[SpecimenResult]]:
  groups: dict[tuple[str, float], list[SpecimenResult]] = {}
  for result in results:
    groups.setdefault(result.board_key, []).append(result)
  return groups


def duplicate_specimens(path: Path) -> list[tuple[str, str]]:
  """하중·변위 자료가 완전히 같은 시험체 쌍(원자료 중복 의심)."""
  workbook = read_workbook(path, include=is_specimen_sheet)
  seen: dict[tuple[tuple[float, float], ...], str] = {}
  duplicates: list[tuple[str, str]] = []
  for name, sheet in workbook.items():
    series = tuple(numeric_column_pairs(sheet, DATA_FIRST_ROW, LOAD_COLUMN, DISPLACEMENT_COLUMN))
    if series in seen:
      duplicates.append((seen[series], name))
    else:
      seen[series] = name
  return duplicates


def check_against_constants(groups: dict[tuple[str, float], list[SpecimenResult]]) -> list[str]:
  """시험 규격 항복비(소수 둘째 자리 반올림)와 constants 값 대조. 불일치 사유 목록."""
  problems: list[str] = []
  for key, (value, source) in BOARD_YIELD_RATIO_BY_BOARD.items():
    if source != TEST_SOURCE:
      continue
    if key not in groups:
      problems.append(f"{key}: 엑셀에 시험체가 없습니다.")
      continue
    computed = round(statistics.mean(result.ratio for result in groups[key]), 2)
    if abs(computed - value) > 1e-9:
      problems.append(f"{key}: 산정 {computed:.2f} ≠ constants {value:.2f}")
  for key in groups:
    if BOARD_YIELD_RATIO_BY_BOARD.get(key, (None, ""))[1] != TEST_SOURCE:
      problems.append(f"{key}: 시험 자료가 있으나 constants 근거가 '{TEST_SOURCE}'가 아닙니다.")
  return problems


def main() -> None:
  parser = argparse.ArgumentParser(description="석고보드 항복비(이선형 근사 꺾임점) 산정")
  parser.add_argument("workbook", type=Path, help="휨실험 결과 정리 엑셀 경로")
  parser.add_argument("--check", action="store_true", help="constants 시험값과 대조")
  parser.add_argument("--detail", action="store_true", help="시험체별 값 출력")
  args = parser.parse_args()
  results = analyze_workbook(args.workbook)
  groups = group_mean_ratios(results)
  print(f"{'종류':10s} {'두께':>5s} {'n':>2s} {'평균':>6s} {'최소':>6s} {'최대':>6s} {'반올림':>6s} {'constants':>9s}")
  for key in sorted(groups):
    ratios = [result.ratio for result in groups[key]]
    mean = statistics.mean(ratios)
    current = BOARD_YIELD_RATIO_BY_BOARD.get(key, (float("nan"), ""))[0]
    print(f"{key[0]:10s} {key[1]:5.1f} {len(ratios):2d} {mean:6.4f} {min(ratios):6.3f} {max(ratios):6.3f} {round(mean, 2):6.2f} {current:9.2f}")
    if args.detail:
      for result in groups[key]:
        print(f"    {result.sheet:16s} Pu {result.ultimate_load:8.2f} Py {result.yield_load:8.2f} Py/Pu {result.ratio:.3f}")
  for first, second in duplicate_specimens(args.workbook):
    print(f"주의: 시험체 '{first}'와 '{second}'의 하중·변위 자료가 같습니다(원자료 중복 확인 필요).", file=sys.stderr)
  if args.check:
    problems = check_against_constants(groups)
    for problem in problems:
      print(f"불일치: {problem}", file=sys.stderr)
    if problems:
      sys.exit(1)
    print("constants 시험값과 일치")


if __name__ == "__main__":
  main()
