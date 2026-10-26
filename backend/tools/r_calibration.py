"""시험 보정계수 R과 E-8 기준 피스력 V* 산정 — 허용처짐 기준(심사의견 E-11·E-8, 2026-10-24).

정의
- R = 허용처짐(H/240) 상태의 사용하중 모멘트 M_L에서의 실측 할선강성 I_test / 엔진 Ieff,raw(L = 2,400).
- 설계 높이 H의 δ–M 그래프에서 H/240 수직선과 실측 환산 곡선의 교점을 계산 직선(R·Ieff,raw(H))이
  지나도록 하는 R이다. 교점은 M_L = q·s·H²/8 (q = 활하중, s = 스터드 간격)에 해당한다.
- 시험(단순보 1점 가력, 가력점 a = 1,500 / b = 900, L = 2,400 mm): P = M_L / (a·b/L),
  가력점 처짐 δ = P·a²·b² / (3·E·I·L) → I_test = K·P / δ_t, K = a²·b² / (3·E·L).
- δ_t: 실측 M–δ 곡선(분석 시트 Q열 M [N·m], U열 = ch4 가력점 변위 [mm], 최대모멘트까지)에서 M_L을 선형 보간.

산정(시편별, 비내진·부분합성, 골든 tests/golden/requested_shape_cases.json 입력)
1. 엔진 Ieff,raw(L = 2,400)를 구한다(R과 무관).
2. 높이 H마다 R_test(H) = I_test(M_L(H)) / Ieff,raw(2,400)를 넣은 엔진 처짐 δ(H)를 구하고,
   g(H) = δ(H) − H/240 = 0인 H*를 이분법으로 찾는다. R_conv = R_test(H*).
   (반복 R → H → M_L → R은 허용높이 50 mm 이산화 때문에 두 값 사이를 순환할 수 있어 연속 높이로 푼다.
   해는 같은 고정점이다.)
3. 설계 R = min(1.0, R_conv 소수 2자리 내림). M_L(H*)가 시험 최대모멘트를 넘으면 예외.
4. 검증: R_conv로 산정한 엔진 허용높이가 H*와 50 mm 이내.
5. V* = P*·a/L, P* = M_L(H_d)/(a·b/L). H_d = 설계 R의 엔진 허용높이(보정점 = 설계 상태).
   같은 형식에 시편이 여럿이면 V*의 최솟값(강성 저감이 큰 쪽)을 쓴다.
6. M*(하중 수준 보정 모멘트 기준, v0.7.4): 실측 할선강성비 I_test(M)/Ieff,raw(2,400)가 설계 R과 같아지는 모멘트.
   M_L(H*)(비 = R_conv ≥ R)와 시험 최대모멘트 사이에서 이분법으로 찾는다. 시험 범위 안에서 비가 R보다
   낮아지지 않으면 M* = 시험 최대모멘트(외삽 금지). 소수 셋째 자리 버림. 같은 형식은 최솟값.

계산엔진에서는 호출하지 않는다. R을 바꿔 넣기 위해 엔진의 R 함수만 도구 실행 중에 임시 대체한다.

사용:
  python -m backend.tools.r_calibration <분석 시트 엑셀 경로>          # 산정표 출력
  python -m backend.tools.r_calibration <분석 시트 엑셀 경로> --check  # constants 값과 대조(불일치 시 종료코드 1)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast
from unittest import mock

import backend.engine.calculator as calculator
from backend.engine.calculator import bolt_values_from_ply_order
from backend.engine.constants import (
  EFFECTIVE_INERTIA_CORRECTION_BY_TYPE,
  STIFFNESS_REF_MOMENT_KNM_BY_TYPE,
  STIFFNESS_REF_SUPPORT_SHEAR_N_BY_TYPE,
  STUD_ELASTIC_MODULUS,
)
from backend.engine.models import BoardLayer, BoltInput, SeismicInput, StudInput, WallCheckRequest
from backend.engine.repository import JsonSeedRepository, MaterialRepository
from backend.tools.xlsx_reader import Sheet, numeric_column_pairs, read_workbook

ROOT = Path(__file__).resolve().parents[2]
SPECIMEN_FILE = ROOT / "tests/golden/requested_shape_cases.json"
SEED_DIR = ROOT / "data/seed"

# 시험체 형상 (mm)
TEST_LOAD_POSITION_A_MM = 1500.0
TEST_LOAD_POSITION_B_MM = 900.0
TEST_SPAN_MM = 2400.0
# 분석 시트 0724: 5행부터 Q열 = M [N·m], U열 = ch4 가력점 변위 [mm]
CURVE_FIRST_ROW = 5
CURVE_MOMENT_COLUMN = 17
CURVE_DEFLECTION_COLUMN = 21
CURVE_MOMENT_TO_KNM = 1e-3
CALIBRATION_DEFLECTION_DENOM = 240
CALIBRATION_DESIGN_CASE = "non_seismic"
CALIBRATION_STRENGTH_MODE = "composite"
R_UPPER_LIMIT = 1.0
R_DECIMALS = 2
HEIGHT_SCAN_STEP_MM = 50.0
HEIGHT_TOLERANCE_MM = 0.01
VERIFY_HEIGHT_TOLERANCE_MM = 50.0
V_STAR_RELATIVE_TOLERANCE = 1e-3
M_STAR_DECIMALS = 3
M_STAR_TOLERANCE_KNM = 1e-7

# 분석 시트 이름 → 골든 시편 id
SHEET_TO_SPECIMEN = {
  "1": "requested_01_c_stud_central_joint",
  "2": "requested_02_c_stud_basic_front_only",
  "3": "requested_03_c_stud_butt_joint",
  "4": "requested_04_c_stud_basic",
  "5": "requested_05_ch_stud_75",
  "6 (2)": "requested_06_hr_stud_124",
  "7": "requested_07_mp_stud_74",
  "8": "requested_08_rv_stud_74",
  "9": "requested_09_t_silent_stud_74",
  "10": "requested_10_r_stud_75",
  "11": "requested_11_i_stud_75",
}


class CalibrationError(RuntimeError):
  """보정점을 구할 수 없을 때(시험 범위 초과 등)."""


@dataclass(frozen=True)
class SpecimenCalibration:
  specimen_id: str
  sheet: str
  calibration_type: str
  I_eff_raw_2400_mm4: float
  calibration_height_mm: float
  M_L_kNm: float
  test_deflection_mm: float
  R_converged: float
  R_design: float
  height_with_R_converged_mm: float
  design_height_mm: float
  design_deflection_mm: float
  design_deflection_limit_mm: float
  design_stiffness_load_factor: float
  V_star_N: float
  M_star_kNm: float
  test_max_moment_kNm: float


def rig_stiffness_constant() -> float:
  a, b, span = TEST_LOAD_POSITION_A_MM, TEST_LOAD_POSITION_B_MM, TEST_SPAN_MM
  return a * a * b * b / (3.0 * STUD_ELASTIC_MODULUS * span)


def rig_moment_arm_mm() -> float:
  """M = P·(a·b/L)."""
  return TEST_LOAD_POSITION_A_MM * TEST_LOAD_POSITION_B_MM / TEST_SPAN_MM


def load_curve(sheet: Sheet) -> list[tuple[float, float]]:
  """(M [kN·m], δ [mm]) — 첫 행부터 최대모멘트 첫 행까지."""
  pairs = numeric_column_pairs(sheet, CURVE_FIRST_ROW, CURVE_MOMENT_COLUMN, CURVE_DEFLECTION_COLUMN)
  if not pairs:
    raise CalibrationError("분석 시트에 M–δ 숫자 자료가 없습니다.")
  moments = [moment for moment, _ in pairs]
  peak = moments.index(max(moments))
  return [(moment * CURVE_MOMENT_TO_KNM, deflection) for moment, deflection in pairs[: peak + 1]]


def measured_deflection_at(curve: Sequence[tuple[float, float]], moment_kNm: float) -> float:
  """실측 곡선에서 M의 시험 변위(첫 도달 구간 선형 보간). 최대모멘트 초과면 예외."""
  if moment_kNm > curve[-1][0]:
    raise CalibrationError(f"M_L {moment_kNm:.4f} kN·m가 시험 최대모멘트 {curve[-1][0]:.4f} kN·m를 넘습니다.")
  for index, (moment, deflection) in enumerate(curve):
    if moment >= moment_kNm:
      if index == 0:
        return deflection
      previous_moment, previous_deflection = curve[index - 1]
      return previous_deflection + (deflection - previous_deflection) * (moment_kNm - previous_moment) / (
        moment - previous_moment
      )
  raise CalibrationError("곡선 보간 실패")


def measured_secant_inertia_mm4(curve: Sequence[tuple[float, float]], moment_kNm: float) -> tuple[float, float]:
  """(I_test [mm⁴], δ_t [mm]). I_test = K·P/δ_t, P = M/(a·b/L)."""
  deflection = measured_deflection_at(curve, moment_kNm)
  if deflection <= 0.0:
    raise CalibrationError(f"M_L {moment_kNm:.4f} kN·m의 시험 변위가 0 이하입니다({deflection:.4f} mm).")
  load_N = moment_kNm * 1e6 / rig_moment_arm_mm()
  return rig_stiffness_constant() * load_N / deflection, deflection


def service_moment_kNm(request: WallCheckRequest, height_mm: float) -> float:
  """M_L = q·s·H²/8 (q = 활하중 kN/m², s·H [m])."""
  return request.live_load_kN_m2 * (request.spacing_mm / 1000.0) * (height_mm / 1000.0) ** 2 / 8.0


def reference_moment_kNm(
  curve: Sequence[tuple[float, float]],
  I_raw_2400_mm4: float,
  R: float,
  start_moment_kNm: float,
) -> float:
  """M*: I_test(M)/Ieff,raw(2,400) = R인 모멘트(시험 최대모멘트 상한, 소수 셋째 자리 버림)."""

  def ratio(moment_kNm: float) -> float:
    return measured_secant_inertia_mm4(curve, moment_kNm)[0] / I_raw_2400_mm4

  max_moment = curve[-1][0]
  if ratio(max_moment) >= R:
    moment = max_moment
  else:
    low, high = start_moment_kNm, max_moment
    if ratio(low) < R:
      raise CalibrationError(f"M* 탐색 시작점 {low:.4f} kN·m에서 강성비가 이미 R {R:.2f}보다 작습니다.")
    while high - low > M_STAR_TOLERANCE_KNM:
      middle = 0.5 * (low + high)
      if ratio(middle) >= R:
        low = middle
      else:
        high = middle
    moment = low
  scale = 10**M_STAR_DECIMALS
  return math.floor(moment * scale + 1e-9) / scale


def v_star_N(moment_kNm: float) -> float:
  """V* = P*·a/L, P* = M/(a·b/L)."""
  load_N = moment_kNm * 1e6 / rig_moment_arm_mm()
  return load_N * TEST_LOAD_POSITION_A_MM / TEST_SPAN_MM


@contextmanager
def fixed_correction_factor(value: float) -> Iterator[None]:
  """도구 실행 중에만 엔진 R을 value로 고정한다."""
  with mock.patch.object(calculator, "_effective_inertia_correction_factor", lambda *args, **kwargs: value):
    yield


def _deflection_gap_mm(request: WallCheckRequest, repository: MaterialRepository, height_mm: float, R: float) -> float:
  with fixed_correction_factor(R):
    result = calculator._calculate_wall_check_once(replace(request, span_mm=height_mm), repository)
  return result.deflection_mm - result.deflection_limit_mm


def _allowable_height_mm(request: WallCheckRequest, repository: MaterialRepository, R: float) -> float:
  with fixed_correction_factor(R):
    return calculator.calculate_wall_check(request, repository).max_height_mm


def calibrate_specimen(
  specimen_id: str,
  sheet_name: str,
  request: WallCheckRequest,
  curve: Sequence[tuple[float, float]],
  repository: MaterialRepository,
) -> SpecimenCalibration:
  if request.deflection_limit_denom != CALIBRATION_DEFLECTION_DENOM:
    raise CalibrationError(f"{specimen_id}: 처짐 한계 L/{request.deflection_limit_denom} ≠ L/{CALIBRATION_DEFLECTION_DENOM}")
  group, method = calculator._parse_stud_type(request.stud)
  try:
    calibration_type = calculator._require_calibration_type(group, method, bool(request.rear_boards))
  except ValueError as error:
    raise CalibrationError(f"{specimen_id}: {error}") from error
  I_raw_2400 = calculator._calculate_wall_check_once(
    replace(request, span_mm=TEST_SPAN_MM), repository
  ).intermediate["I_eff_raw_mm4"]

  # 시험 최대모멘트에 해당하는 높이(탐색 상한)
  max_moment = curve[-1][0]
  height_limit = math.sqrt(8.0 * max_moment / (request.live_load_kN_m2 * request.spacing_mm / 1000.0)) * 1000.0

  def R_test(height_mm: float) -> float:
    if height_mm > height_limit:
      raise CalibrationError(f"{specimen_id}: 탐색 높이 {height_mm:.2f} mm가 시험 상한 {height_limit:.2f} mm를 넘습니다.")
    # 상한 높이의 부동소수 오차로 M_L이 Mmax를 미세하게 넘지 않도록 Mmax로 제한
    moment = min(service_moment_kNm(request, height_mm), max_moment)
    return measured_secant_inertia_mm4(curve, moment)[0] / I_raw_2400

  def gap(height_mm: float) -> float:
    return _deflection_gap_mm(request, repository, height_mm, R_test(height_mm))

  # 50 mm 간격(마지막 점은 상한 높이)으로 부호 변화(g < 0 → g ≥ 0)를 찾는다.
  low = TEST_SPAN_MM
  if gap(low) >= 0.0:
    raise CalibrationError(f"{specimen_id}: L = {low:.0f} mm에서 이미 처짐 한계에 도달합니다.")
  high = None
  while low < height_limit:
    height = min(low + HEIGHT_SCAN_STEP_MM, height_limit)
    if gap(height) >= 0.0:
      high = height
      break
    low = height
  if high is None:
    raise CalibrationError(
      f"{specimen_id}: 시험 최대모멘트 높이 {height_limit:.0f} mm까지 처짐 한계에 도달하지 않습니다(보정점이 시험 범위 밖)."
    )
  while high - low > HEIGHT_TOLERANCE_MM:
    middle = 0.5 * (low + high)
    if gap(middle) >= 0.0:
      high = middle
    else:
      low = middle
  calibration_height = low
  moment = service_moment_kNm(request, calibration_height)
  I_test, test_deflection = measured_secant_inertia_mm4(curve, moment)
  R_converged = I_test / I_raw_2400
  R_design = min(R_UPPER_LIMIT, math.floor(R_converged * 10**R_DECIMALS + 1e-9) / 10**R_DECIMALS)

  height_converged = _allowable_height_mm(request, repository, R_converged)
  if abs(height_converged - calibration_height) > VERIFY_HEIGHT_TOLERANCE_MM:
    raise CalibrationError(
      f"{specimen_id}: R_conv 허용높이 {height_converged:.0f} mm가 보정점 {calibration_height:.0f} mm와 "
      f"{VERIFY_HEIGHT_TOLERANCE_MM:.0f} mm 넘게 다릅니다(강도 지배 등)."
    )
  design_height = _allowable_height_mm(request, repository, R_design)
  with fixed_correction_factor(R_design):
    design = calculator._calculate_wall_check_once(replace(request, span_mm=design_height), repository)
  return SpecimenCalibration(
    specimen_id=specimen_id,
    sheet=sheet_name,
    calibration_type=calibration_type,
    I_eff_raw_2400_mm4=I_raw_2400,
    calibration_height_mm=calibration_height,
    M_L_kNm=moment,
    test_deflection_mm=test_deflection,
    R_converged=R_converged,
    R_design=R_design,
    height_with_R_converged_mm=height_converged,
    design_height_mm=design_height,
    design_deflection_mm=design.deflection_mm,
    design_deflection_limit_mm=design.deflection_limit_mm,
    design_stiffness_load_factor=float(design.intermediate["stiffness_load_factor"]),
    V_star_N=v_star_N(service_moment_kNm(request, design_height)),
    M_star_kNm=reference_moment_kNm(curve, I_raw_2400, R_design, moment),
    test_max_moment_kNm=max_moment,
  )


def specimen_requests(path: Path = SPECIMEN_FILE) -> dict[str, WallCheckRequest]:
  """골든 시편 입력 → 보정 조건(비내진·부분합성) 요청."""
  with path.open(encoding="utf-8") as file:
    data = cast(Mapping[str, object], json.load(file))
  common = cast(Mapping[str, object], data["common"])
  bolt = cast(Mapping[str, object], common["bolt"])
  seismic = cast(Mapping[str, object], common["seismic"])

  def boards(raw: Sequence[Mapping[str, object]]) -> tuple[BoardLayer, ...]:
    return tuple(
      BoardLayer(kind=str(item["kind"]), thickness=float(cast(float, item["thickness"])),
                 order=None if item.get("order") is None else int(cast(int, item["order"])))
      for item in raw
    )

  requests: dict[str, WallCheckRequest] = {}
  for case in cast(Sequence[Mapping[str, object]], data["cases"]):
    inputs = cast(Mapping[str, object], case["input"])
    requests[str(case["id"])] = WallCheckRequest(
      rear_boards=boards(cast(Sequence[Mapping[str, object]], inputs["rear_boards"])),
      front_boards=boards(cast(Sequence[Mapping[str, object]], inputs["front_boards"])),
      stud=StudInput(
        stud_type=str(inputs["stud_type"]),
        spec=str(inputs["stud_spec"]),
        method=None if inputs.get("method") is None else str(inputs["method"]),
      ),
      horizontal_load_kg_m2=float(cast(float, common["horizontal_load_kg_m2"])),
      live_load_kN_m2=float(cast(float, common["live_load_kN_m2"])),
      vertical_load_kN_m=float(cast(float, common["vertical_load_kN_m"])),
      spacing_mm=float(cast(float, inputs["spacing_mm"])),
      span_mm=TEST_SPAN_MM,
      deflection_limit_denom=int(cast(int, common["deflection_limit_denom"])),
      bolt=BoltInput(
        diameter=float(cast(float, bolt["diameter"])),
        yield_strength=float(cast(float, bolt["yield_strength"])),
        pitch=bolt_values_from_ply_order(tuple(float(v) for v in cast(Sequence[float], bolt["pitch"]))),
        count=bolt_values_from_ply_order(tuple(float(v) for v in cast(Sequence[float], bolt["count"]))),
      ),
      seismic=SeismicInput(
        S=float(cast(float, seismic["S"])),
        Ip=float(cast(float, seismic["Ip"])),
        Fa=float(cast(float, seismic["Fa"])),
      ),
      design_case=CALIBRATION_DESIGN_CASE,
      strength_check_mode=CALIBRATION_STRENGTH_MODE,
      omega=float(cast(float, common["omega"])),
      anchor_capacity_kN=float(cast(float, common["anchor_capacity_kN"])),
      anchor_spacing_mm=float(cast(float, common["anchor_spacing_mm"])),
    )
  return requests


def calibrate_workbook(path: Path, repository: MaterialRepository | None = None) -> list[SpecimenCalibration]:
  repo = repository or JsonSeedRepository(SEED_DIR)
  workbook = read_workbook(path, include=lambda name: name in SHEET_TO_SPECIMEN)
  missing = sorted(set(SHEET_TO_SPECIMEN) - set(workbook))
  if missing:
    raise CalibrationError(f"분석 시트가 없습니다: {missing}")
  requests = specimen_requests()
  return [
    calibrate_specimen(specimen_id, sheet, requests[specimen_id], load_curve(workbook[sheet]), repo)
    for sheet, specimen_id in SHEET_TO_SPECIMEN.items()
  ]


def design_table(results: Sequence[SpecimenCalibration]) -> dict[str, tuple[float, float, float]]:
  """형식 → (R, V* [N], M* [kN·m]). 같은 형식 시편이 여럿이면 R은 일치해야 하고 V*·M*는 최솟값."""
  table: dict[str, tuple[float, float, float]] = {}
  for result in results:
    if result.calibration_type in table:
      R, v_star, m_star = table[result.calibration_type]
      if abs(R - result.R_design) > 1e-9:
        raise CalibrationError(
          f"형식 {result.calibration_type}: 시편별 R이 다릅니다({R:.2f}, {result.R_design:.2f}) — 형식 분류 재검토 필요"
        )
      table[result.calibration_type] = (R, min(v_star, result.V_star_N), min(m_star, result.M_star_kNm))
    else:
      table[result.calibration_type] = (result.R_design, result.V_star_N, result.M_star_kNm)
  return table


def check_against_constants(table: Mapping[str, tuple[float, float, float]]) -> list[str]:
  problems: list[str] = []
  for calibration_type, (R, v_star, m_star) in table.items():
    current_R = EFFECTIVE_INERTIA_CORRECTION_BY_TYPE.get(calibration_type)
    current_v = STIFFNESS_REF_SUPPORT_SHEAR_N_BY_TYPE.get(calibration_type)
    current_m = STIFFNESS_REF_MOMENT_KNM_BY_TYPE.get(calibration_type)
    if current_m is None or abs(current_m - m_star) > 1e-9:
      problems.append(f"{calibration_type}: M* 산정 {m_star:.3f} kN·m ≠ constants {current_m}")
    if current_R is None or abs(current_R - R) > 1e-9:
      problems.append(f"{calibration_type}: R 산정 {R:.2f} ≠ constants {current_R}")
    if current_v is None or abs(current_v / v_star - 1.0) > V_STAR_RELATIVE_TOLERANCE:
      problems.append(f"{calibration_type}: V* 산정 {v_star:.1f} N ≠ constants {current_v}")
  for calibration_type in set(EFFECTIVE_INERTIA_CORRECTION_BY_TYPE) - set(table):
    problems.append(f"{calibration_type}: constants에 있으나 시편이 없습니다.")
  return problems


def main() -> None:
  parser = argparse.ArgumentParser(description="시험 보정계수 R(허용처짐 기준)·E-8 기준 피스력 V*·기준 모멘트 M* 산정")
  parser.add_argument("workbook", type=Path, help="벽체 시험 분석 시트(0724) 엑셀 경로")
  parser.add_argument("--check", action="store_true", help="constants 값과 대조")
  args = parser.parse_args()
  results = calibrate_workbook(args.workbook)
  print(
    f"{'시편':36s} {'Ieff,raw2400':>12s} {'H*':>8s} {'M_L':>7s} {'δt':>6s} {'R_conv':>7s} {'R':>5s} "
    f"{'H(Rconv)':>8s} {'H_d':>6s} {'δ/한계':>13s} {'E8':>5s} {'V*':>7s} {'M*':>6s} {'Mmax':>6s}"
  )
  for r in results:
    print(
      f"{r.specimen_id:36s} {r.I_eff_raw_2400_mm4:12.0f} {r.calibration_height_mm:8.1f} {r.M_L_kNm:7.4f} "
      f"{r.test_deflection_mm:6.3f} {r.R_converged:7.4f} {r.R_design:5.2f} {r.height_with_R_converged_mm:8.0f} "
      f"{r.design_height_mm:6.0f} {r.design_deflection_mm:6.2f}/{r.design_deflection_limit_mm:6.2f} "
      f"{r.design_stiffness_load_factor:5.3f} {r.V_star_N:7.1f} {r.M_star_kNm:6.3f} {r.test_max_moment_kNm:6.3f}"
    )
  table = design_table(results)
  print("\n형식별 설계값")
  for calibration_type, (R, v_star, m_star) in table.items():
    print(f"  {calibration_type:16s} R {R:.2f}  V* {v_star:.1f} N  M* {m_star:.3f} kN·m")
  if args.check:
    problems = check_against_constants(table)
    for problem in problems:
      print(f"불일치: {problem}", file=sys.stderr)
    if problems:
      sys.exit(1)
    print("constants 값과 일치")


if __name__ == "__main__":
  main()
