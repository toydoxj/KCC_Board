"""하중 수준 보정 k_L 모멘트 기준(v0.7.4, 심사의견 E-3·E-8).

u/u_ref = max(M_L/M*, V_d/V*) × 피치비, k_L = min[1, (u/u_ref)^(1−m)]
"""

from dataclasses import replace
import os
from pathlib import Path

import pytest

from backend.engine.calculator import (
  _calculate_wall_check_once,
  _parse_stud_type,
  _require_calibration_type,
  calculate_wall_check,
)
from backend.engine.constants import (
  STIFFNESS_REF_MOMENT_KNM_BY_TYPE,
  STIFFNESS_REF_SUPPORT_SHEAR_N_BY_TYPE,
)
from backend.engine.repository import JsonSeedRepository
from backend.tools import r_calibration

ROOT = Path(__file__).resolve().parents[1]
REPO = JsonSeedRepository(ROOT / "data/seed")
REQUESTS = r_calibration.specimen_requests()

# 시편별 R 보정점 높이 H* (mm). r_calibration 산정값(분석 시트 0724, 2026-10-26)
CALIBRATION_HEIGHT_MM = {
  "requested_01_c_stud_central_joint": 8727.0,
  "requested_02_c_stud_basic_front_only": 5616.8,
  "requested_03_c_stud_butt_joint": 8864.3,
  "requested_04_c_stud_basic": 7968.9,
  "requested_05_ch_stud_75": 6230.1,
  "requested_06_hr_stud_124": 10704.4,
  "requested_07_mp_stud_74": 6685.0,
  "requested_08_rv_stud_74": 6765.3,
  "requested_09_t_silent_stud_74": 7017.5,
  "requested_10_r_stud_75": 6330.4,
  "requested_11_i_stud_75": 6710.7,
}
WORKBOOK = Path(os.environ.get("KCC_WALL_TEST_WORKBOOK", ROOT / ".orca/drops/wall_test_analysis_20260724.xlsx"))


def _run(specimen_id: str, height_mm: float, **changes):
  request = replace(REQUESTS[specimen_id], span_mm=height_mm, **changes)
  return request, _calculate_wall_check_once(request, REPO)


def _calibration_type(request) -> str:
  group, method = _parse_stud_type(request.stud)
  return _require_calibration_type(group, method, bool(request.rear_boards))


@pytest.mark.parametrize("specimen_id", sorted(CALIBRATION_HEIGHT_MM))
def test_calibration_point_has_no_load_level_reduction(specimen_id: str) -> None:
  # 적용 R ≤ R_conv이므로 보정점 H*에서 M_L(H*) ≤ M*, 따라서 k_L = 1.0
  request, result = _run(specimen_id, CALIBRATION_HEIGHT_MM[specimen_id])
  m_star = STIFFNESS_REF_MOMENT_KNM_BY_TYPE[_calibration_type(request)]
  assert result.intermediate["service_moment_kNm"] <= m_star
  assert result.intermediate["reference_moment_kNm"] == pytest.approx(m_star)
  assert result.intermediate["moment_utilization_ratio"] <= 1.0
  assert result.intermediate["stiffness_load_factor"] == 1.0


@pytest.mark.parametrize("specimen_id", sorted(CALIBRATION_HEIGHT_MM))
def test_both_bases_within_reference_gives_unit_factor(specimen_id: str) -> None:
  _, result = _run(specimen_id, 2400.0)
  im = result.intermediate
  assert im["moment_utilization_ratio"] <= 1.0
  assert im["shear_utilization_ratio"] <= 1.0
  assert im["screw_utilization_ratio"] <= 1.0
  assert im["stiffness_load_factor"] == 1.0


def test_governing_basis_is_the_larger_utilization() -> None:
  # CH(M* 0.732): 높은 벽에서 모멘트 기준이 지배한다
  request, result = _run("requested_05_ch_stud_75", 7500.0)
  im = result.intermediate
  ratio_m = im["service_moment_kNm"] / STIFFNESS_REF_MOMENT_KNM_BY_TYPE[_calibration_type(request)]
  assert im["moment_utilization_ratio"] == pytest.approx(ratio_m)
  assert im["moment_utilization_ratio"] > im["shear_utilization_ratio"]
  assert im["stiffness_load_basis_moment"] == 1.0
  pitch_ratio = im["screw_utilization_ratio"] / im["moment_utilization_ratio"]
  assert pitch_ratio >= 1.0
  m = im["stiffness_curve_exponent_m"]
  expected = min(1.0, im["screw_utilization_ratio"] ** (1.0 - m))
  assert im["stiffness_load_factor"] == pytest.approx(expected)
  assert im["stiffness_load_factor"] < 1.0


def test_c_front_only_is_shear_governed_and_unchanged() -> None:
  # C 일면(V* 390.6 N, M* 1.692)은 피스력 기준이 지배하므로 v0.7.3 식과 결과가 같다
  for height_mm in (2400.0, 4000.0, 5600.0, 7000.0):
    request, result = _run("requested_02_c_stud_basic_front_only", height_mm)
    im = result.intermediate
    assert im["stiffness_load_basis_moment"] == 0.0
    v_d = request.live_load_kN_m2 * 1e-3 * request.spacing_mm * height_mm / 2.0
    v_star = STIFFNESS_REF_SUPPORT_SHEAR_N_BY_TYPE[_calibration_type(request)]
    assert im["shear_utilization_ratio"] == pytest.approx(v_d / v_star)
    old_ratio = im["shear_utilization_ratio"] * (im["screw_utilization_ratio"] / max(im["moment_utilization_ratio"], im["shear_utilization_ratio"]))
    old_factor = 1.0 if old_ratio <= 1.0 else old_ratio ** (1.0 - im["stiffness_curve_exponent_m"])
    assert im["stiffness_load_factor"] == pytest.approx(old_factor)


# 시편 11개 × 4개 조건 허용높이(mm). v0.7.3(피스력 기준만)과 같아야 한다.
# (비내진·부분합성, 비내진·STUD 단독, 내진·부분합성, 내진·STUD 단독)
SPECIMEN_MAX_HEIGHT_MM = {
  "requested_01_c_stud_central_joint": (8650.0, 8650.0, 8650.0, 8050.0),
  "requested_02_c_stud_basic_front_only": (5000.0, 5000.0, 5000.0, 5000.0),
  "requested_03_c_stud_butt_joint": (7400.0, 7400.0, 7400.0, 6150.0),
  "requested_04_c_stud_basic": (7100.0, 5750.0, 7100.0, 4400.0),
  "requested_05_ch_stud_75": (6200.0, 5100.0, 6200.0, 3950.0),
  "requested_06_hr_stud_124": (10650.0, 9500.0, 10650.0, 7250.0),
  "requested_07_mp_stud_74": (6650.0, 6100.0, 6650.0, 4650.0),
  "requested_08_rv_stud_74": (6750.0, 5150.0, 6750.0, 3950.0),
  "requested_09_t_silent_stud_74": (6950.0, 5700.0, 6950.0, 4350.0),
  "requested_10_r_stud_75": (6300.0, 6300.0, 6300.0, 5700.0),
  "requested_11_i_stud_75": (6300.0, 5150.0, 6300.0, 4000.0),
}
CONDITIONS = (
  ("non_seismic", "composite"),
  ("non_seismic", "stud_only"),
  ("seismic", "composite"),
  ("seismic", "stud_only"),
)


@pytest.mark.parametrize("specimen_id", sorted(SPECIMEN_MAX_HEIGHT_MM))
def test_specimen_allowable_heights_unchanged(specimen_id: str) -> None:
  for (design_case, mode), expected in zip(CONDITIONS, SPECIMEN_MAX_HEIGHT_MM[specimen_id]):
    request = replace(REQUESTS[specimen_id], design_case=design_case, strength_check_mode=mode)
    result = calculate_wall_check(request, REPO)
    assert result.max_height_mm == expected, (design_case, mode)


@pytest.mark.skipif(not WORKBOOK.exists(), reason="시험 분석 엑셀이 없음(KCC_WALL_TEST_WORKBOOK로 경로 지정)")
def test_r_calibration_reproduces_reference_moments() -> None:
  table = r_calibration.design_table(r_calibration.calibrate_workbook(WORKBOOK))
  assert r_calibration.check_against_constants(table) == []
