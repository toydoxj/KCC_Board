"""시험 보정계수 R(허용처짐 기준)·E-8 기준 피스력 산정 도구 테스트 — 엑셀 원본 의존 없음."""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from backend.engine.calculator import _calculate_wall_check_once, calculate_wall_check
from backend.engine.repository import JsonSeedRepository
from backend.tools.r_calibration import (
  CalibrationError,
  calibrate_specimen,
  service_moment_kNm,
  specimen_requests,
  measured_deflection_at as deflection_at,
  rig_moment_arm_mm as moment_arm_mm,
  measured_secant_inertia_mm4 as secant_inertia_mm4,
  rig_stiffness_constant as stiffness_constant,
  v_star_N,
)


ROOT = Path(__file__).resolve().parents[1]


def _linear_curve(inertia_mm4: float, max_moment_kNm: float, points: int = 200) -> list[tuple[float, float]]:
  """I가 일정한 시험 곡선 (M [kN·m], δ [mm]) — δ = K·P / I."""
  curve = []
  for index in range(points + 1):
    moment = max_moment_kNm * index / points
    load_N = moment * 1e6 / moment_arm_mm()
    curve.append((moment, stiffness_constant() * load_N / inertia_mm4))
  return curve


class TestFormulaTest(unittest.TestCase):
  def test_point_load_deflection_constant(self) -> None:
    # 단순보 1점 가력(a 1,500, b 900, L 2,400): δ = P·a²·b²/(3·E·I·L), M = P·a·b/L = P·562.5
    self.assertAlmostEqual(moment_arm_mm(), 562.5)
    self.assertAlmostEqual(stiffness_constant(), 1500.0**2 * 900.0**2 / (3.0 * 210000.0 * 2400.0))

  def test_secant_inertia_from_curve(self) -> None:
    curve = _linear_curve(500000.0, 2.0)
    inertia, deflection = secant_inertia_mm4(curve, 0.7)
    self.assertAlmostEqual(inertia, 500000.0, places=3)
    self.assertAlmostEqual(deflection, deflection_at(curve, 0.7))

  def test_moment_above_test_maximum_rejected(self) -> None:
    with self.assertRaises(CalibrationError):
      deflection_at(_linear_curve(500000.0, 1.0), 1.0001)

  def test_service_moment_and_v_star(self) -> None:
    request = specimen_requests()["requested_05_ch_stud_75"]
    # M_L = q·s·H²/8 = 0.25 × 0.6 × 6.2² / 8
    self.assertAlmostEqual(service_moment_kNm(request, 6200.0), 0.25 * 0.6 * 6.2**2 / 8.0)
    # V* = P*·a/L = M/(a·b/L)·a/L = M/b
    self.assertAlmostEqual(v_star_N(0.9), 0.9e6 / 900.0)


class CalibrationTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.repository = JsonSeedRepository(ROOT / "data/seed")
    cls.requests = specimen_requests()

  def test_linear_test_curve_recovers_its_stiffness_ratio(self) -> None:
    # 시험 강성이 R0·Ieff,raw(2,400)로 일정하면 보정점과 무관하게 R_conv = R0
    specimen_id = "requested_05_ch_stud_75"
    request = self.requests[specimen_id]
    I_raw = _calculate_wall_check_once(request, self.repository).intermediate["I_eff_raw_mm4"]
    result = calibrate_specimen(specimen_id, "5", request, _linear_curve(0.8 * I_raw, 3.0), self.repository)
    self.assertAlmostEqual(result.R_converged, 0.8, places=9)
    self.assertEqual(result.R_design, 0.8)
    self.assertLessEqual(abs(result.height_with_R_converged_mm - result.calibration_height_mm), 50.0)
    self.assertLessEqual(result.design_deflection_mm, result.design_deflection_limit_mm)

  def test_solution_in_last_partial_scan_interval_is_found(self) -> None:
    # 해가 마지막 50 mm 격자점과 시험 상한 사이(10 mm 앞)에 있어도 찾는다
    specimen_id = "requested_05_ch_stud_75"
    request = self.requests[specimen_id]
    I_raw = _calculate_wall_check_once(request, self.repository).intermediate["I_eff_raw_mm4"]
    reference = calibrate_specimen(specimen_id, "5", request, _linear_curve(0.8 * I_raw, 3.0), self.repository)
    limit_moment = service_moment_kNm(request, reference.calibration_height_mm + 10.0)
    result = calibrate_specimen(specimen_id, "5", request, _linear_curve(0.8 * I_raw, limit_moment), self.repository)
    self.assertAlmostEqual(result.calibration_height_mm, reference.calibration_height_mm, delta=0.02)
    self.assertAlmostEqual(result.R_converged, 0.8, places=9)

  def test_calibration_point_outside_test_range_rejected(self) -> None:
    specimen_id = "requested_05_ch_stud_75"
    request = self.requests[specimen_id]
    I_raw = _calculate_wall_check_once(request, self.repository).intermediate["I_eff_raw_mm4"]
    with self.assertRaises(CalibrationError):
      calibrate_specimen(specimen_id, "5", request, _linear_curve(0.8 * I_raw, 0.3), self.repository)

  def test_stiffness_load_factor_is_one_for_calibration_specimens(self) -> None:
    # E-8: 시험 11개 시편은 보정점과 설계 상태가 같으므로 피스 활용도 보정이 없어야 한다
    for specimen_id, request in self.requests.items():
      with self.subTest(specimen=specimen_id):
        height = calculate_wall_check(request, self.repository).max_height_mm
        result = _calculate_wall_check_once(replace(request, span_mm=height), self.repository)
        self.assertLess(result.intermediate["screw_utilization_ratio"], 1.0)
        self.assertEqual(result.intermediate["stiffness_load_factor"], 1.0)


if __name__ == "__main__":
  unittest.main()
