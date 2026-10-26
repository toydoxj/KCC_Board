"""엑셀 골든 케이스 회귀테스트."""

from __future__ import annotations

import json
import math
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Mapping, cast

from backend.engine.calculator import (
  _build_section,
  _calculate_wall_check_once,
  _connection_capacity_kN,
  _count_for_order,
  _effective_inertia_correction_factor,
  _gypsum_screw_design_shear_N,
  _nominal_moment,
  _pitch_for_order,
  _screw_stud_side_shear_N,
  _stiffness_reference_shear_N,
  _shear_connection_by_layer,
  bolt_values_from_ply_order,
  calculate_wall_check,
  request_from_golden_case,
)
from backend.api.schemas import BoltPayload
from backend.engine.constants import (
  SCREW_SHEAR_OMEGA,
  STANDARD_SCREW_COUNT,
  STANDARD_SCREW_PITCH_MM,
  STIFFNESS_REF_SCREW_PITCH_MM,
  STIFFNESS_REF_SUPPORT_SHEAR_N_BY_TYPE,
  STIFFNESS_TYPE_C,
)
from backend.engine.models import BoardLayer, StudInput
from backend.engine.repository import JsonSeedRepository


ROOT = Path(__file__).resolve().parents[1]


def _stud_t(section) -> float:
  thickness = section.stud_section.t
  if thickness is None:
    raise AssertionError("스터드 두께 t가 없습니다.")
  return thickness


def _stud_fu(section) -> float:
  return section.stud_section.steel.Fu


class GoldenCaseTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.repository = JsonSeedRepository(ROOT / "data/seed")
    with (ROOT / "tests/golden/cases.json").open(encoding="utf-8") as file:
      data = cast(Mapping[str, object], json.load(file))
    cls.tolerance_rel = float(data["_tolerance_rel"])
    cls.cases = cast(list[Mapping[str, object]], data["cases"])

  def test_golden_cases(self) -> None:
    for case in self.cases:
      with self.subTest(case=case["id"]):
        request = request_from_golden_case(dict(case))
        result = calculate_wall_check(request, self.repository)
        expected = cast(Mapping[str, object], case["expected"])

        self._assert_close("neutral_axis_mm", result.neutral_axis_mm, expected)
        self._assert_close("I_full_mm4", result.I_full_mm4, expected)
        self._assert_close("eta", result.eta, expected)
        self._assert_close("I_eff_mm4", result.I_eff_mm4, expected)
        self._assert_close("Mn_kNm", result.Mn_kNm, expected)
        self._assert_close("Mu_kNm", result.Mu_kNm, expected)
        self._assert_close("stress_ratio", result.stress_ratio, expected)
        self._assert_close("deflection_mm", result.deflection_mm, expected)
        self._assert_close("deflection_limit_mm", result.deflection_limit_mm, expected)
        self._assert_close("seismic_moment_kNm", result.seismic_moment_kNm, expected)
        self.assertEqual(result.deflection_verdict, expected["deflection_verdict"])
        self.assertEqual(result.stress_verdict, expected["stress_verdict"])

  def test_golden_bolt_pitch_is_excel_ply_order(self) -> None:
    # 골든 bolt_pitch = 엑셀 VAR. C32:C34 = [1P(내측, 스터드 인접), 2P, 3P(외측)]
    request = request_from_golden_case(dict(self.cases[0]))

    self.assertEqual(request.bolt.pitch, STANDARD_SCREW_PITCH_MM)
    self.assertEqual(_pitch_for_order(request.bolt.pitch, 1), 600.0)
    self.assertEqual(_pitch_for_order(request.bolt.pitch, 3), 300.0)

  def test_stiffness_reference_pitch_has_inner_600(self) -> None:
    # E-8 시험 피스 간격: 1P(내측) 600, 2P·3P 300
    self.assertEqual(_pitch_for_order(STIFFNESS_REF_SCREW_PITCH_MM, 1), 600.0)
    self.assertEqual(_pitch_for_order(STIFFNESS_REF_SCREW_PITCH_MM, 2), 300.0)
    self.assertEqual(_pitch_for_order(STIFFNESS_REF_SCREW_PITCH_MM, 3), 300.0)

  def test_ply_order_pitch_requires_three_values(self) -> None:
    with self.assertRaises(ValueError):
      bolt_values_from_ply_order((600.0, 300.0))

  def test_default_screw_count_is_cumulative_1_3_5(self) -> None:
    # 연결 피스 개수 누계 1-3-5 = 층별 1번(내측) 1, 2번 2, 3번(외측) 2
    request = request_from_golden_case(dict(self.cases[0]))

    self.assertEqual(request.bolt.count, STANDARD_SCREW_COUNT)
    self.assertEqual(_count_for_order(request.bolt.count, 1), 1.0)
    self.assertEqual(_count_for_order(request.bolt.count, 2), 2.0)
    self.assertEqual(_count_for_order(request.bolt.count, 3), 2.0)
    self.assertEqual(BoltPayload(diameter=3.5, yield_strength=340.0, pitch=[300.0]).to_engine().count, STANDARD_SCREW_COUNT)

  def test_bolt_payload_backward_compatible_inputs(self) -> None:
    # 단일 count는 전 층 동일, pitch 1개는 전 층 동일, 2개는 [외측, 중간·내측]
    single = BoltPayload(diameter=3.5, yield_strength=340.0, pitch=[450.0], count=2.0).to_engine()
    pair = BoltPayload(diameter=3.5, yield_strength=340.0, pitch=[300.0, 600.0]).to_engine()

    for order in (1, 2, 3):
      self.assertEqual(_count_for_order(single.count, order), 2.0)
      self.assertEqual(_pitch_for_order(single.pitch, order), 450.0)
    self.assertEqual(_pitch_for_order(pair.pitch, 3), 300.0)
    self.assertEqual(_pitch_for_order(pair.pitch, 2), 600.0)
    self.assertEqual(_pitch_for_order(pair.pitch, 1), 600.0)

  def test_bolt_count_can_vary_by_board_order(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    base = calculate_wall_check(request, self.repository)
    reduced_middle_count = calculate_wall_check(
      replace(request, bolt=replace(request.bolt, count=(2.0, 1.0, 2.0))),
      self.repository,
    )

    self.assertLess(reduced_middle_count.eta, base.eta)
    self.assertLess(reduced_middle_count.Mn_kNm, base.Mn_kNm)

  def test_stud_only_strength_check_uses_only_stud_moment(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    composite = calculate_wall_check(request, self.repository)
    stud_only = calculate_wall_check(
      replace(request, strength_check_mode="stud_only"),
      self.repository,
    )

    self.assertEqual(composite.strength_check_mode, "composite")
    self.assertEqual(stud_only.strength_check_mode, "stud_only")
    self.assertAlmostEqual(stud_only.Mn_kNm, stud_only.intermediate["Mn_stud_only_kNm"])
    self.assertAlmostEqual(composite.Mn_kNm, composite.intermediate["Mn_composite_kNm"])
    self.assertLess(stud_only.Mn_kNm, composite.Mn_kNm)
    self.assertEqual(stud_only.max_height_mm, 6150.0)
    self.assertEqual(stud_only.stress_verdict, "N.G")

  def test_bolt_shear_uses_half_and_yield_conversion_factors(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    bolt = replace(
      request.bolt,
      yield_strength=10.0,
      pitch=(1000.0, 1000.0, 1000.0),
      count=(1.0, 1.0, 1.0),
    )
    request = replace(request, bolt=bolt)
    section = _build_section(request, self.repository)
    layer = next(
      layer for layer in section.layers if layer.layer_type == "board" and layer.order == 2
    )

    actual = _connection_capacity_kN(layer, request.bolt, request.span_mm, stud_thickness_mm=_stud_t(section), stud_tensile_strength=_stud_fu(section))
    bolt_area = math.pi / 4.0 * request.bolt.diameter**2
    expected_shear_n = 0.5 * 0.6 * request.bolt.yield_strength * bolt_area / 1.25
    expected = expected_shear_n * (request.span_mm / 2.0) / 1000.0 * 1e-3

    self.assertAlmostEqual(actual, expected)

  def test_inner_board_connection_does_not_use_extra_factor(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    bolt = replace(
      request.bolt,
      yield_strength=10.0,
      pitch=(1000.0, 1000.0, 1000.0),
      count=(1.0, 1.0, 1.0),
    )
    request = replace(request, bolt=bolt)
    section = _build_section(request, self.repository)
    layer = next(
      layer for layer in section.layers if layer.layer_type == "board" and layer.order == 1
    )

    actual = _connection_capacity_kN(layer, request.bolt, request.span_mm, stud_thickness_mm=_stud_t(section), stud_tensile_strength=_stud_fu(section))
    bolt_area = math.pi / 4.0 * request.bolt.diameter**2
    expected_shear_n = 0.5 * 0.6 * request.bolt.yield_strength * bolt_area / 1.25
    expected = expected_shear_n * (request.span_mm / 2.0) / 1000.0 * 1e-3

    self.assertAlmostEqual(actual, expected)

  def test_screw_shear_limited_by_stud_tilting_and_bearing(self) -> None:
    # AISI S100-16 J4.3.1 (t2/t1 ≤ 1.0): Pns = min(4.2(t2³d)^0.5·Fu2, 2.7·t2·d·Fu2), Ω = 3.0 — 강성 경로에도 적용
    request = request_from_golden_case(dict(self.cases[0]))
    bolt = replace(request.bolt, yield_strength=1_000_000.0, pitch=(1000.0, 1000.0, 1000.0), count=(1.0, 1.0, 1.0))
    request = replace(request, bolt=bolt)
    section = _build_section(request, self.repository)
    layer = next(layer for layer in section.layers if layer.layer_type == "board" and layer.order == 1)
    t2 = _stud_t(section)
    d = request.bolt.diameter

    actual = _connection_capacity_kN(layer, request.bolt, request.span_mm, stud_thickness_mm=t2, stud_tensile_strength=_stud_fu(section))
    tilting = 4.2 * math.sqrt(t2**3 * d) * 400.0
    bearing = 2.7 * t2 * d * 400.0
    expected = min(tilting, bearing) / SCREW_SHEAR_OMEGA * (request.span_mm / 2.0) / 1000.0 * 1e-3

    self.assertAlmostEqual(actual, expected)

  def test_strength_path_also_applies_stud_side_limit(self) -> None:
    # 스터드측 한계가 석고보드 피스 설계강도보다 작아지도록 얇은 가상 두께(0.1 mm)를 써서 강도 경로 적용을 확인
    request = request_from_golden_case(dict(self.cases[0]))
    bolt = replace(request.bolt, yield_strength=1_000_000.0, pitch=(1000.0, 1000.0, 1000.0), count=(1.0, 1.0, 1.0))
    request = replace(request, bolt=bolt)
    section = _build_section(request, self.repository)
    layer = next(layer for layer in section.layers if layer.layer_type == "board" and layer.order == 1)
    thin_t = 0.1
    stud_side = _screw_stud_side_shear_N(thin_t, request.bolt.diameter, _stud_fu(section))
    self.assertLess(stud_side, _gypsum_screw_design_shear_N(layer.thickness_mm))

    actual = _connection_capacity_kN(layer, request.bolt, request.span_mm, stud_thickness_mm=thin_t, stud_tensile_strength=_stud_fu(section), for_strength=True)

    self.assertAlmostEqual(actual, stud_side * (request.span_mm / 2.0) / 1000.0 * 1e-3)

  def test_missing_stud_thickness_raises(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    section = _build_section(request, self.repository)
    no_t = replace(section, stud_section=replace(section.stud_section, t=None))

    with self.assertRaisesRegex(ValueError, "두께 t"):
      _shear_connection_by_layer(no_t, request)

  def test_board_bearing_uses_fracture_strength(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    bolt = replace(
      request.bolt,
      yield_strength=1_000_000.0,
      pitch=(1000.0, 1000.0, 1000.0),
      count=(1.0, 1.0, 1.0),
    )
    request = replace(request, bolt=bolt)
    section = _build_section(request, self.repository)
    layer = next(
      layer for layer in section.layers if layer.layer_type == "board" and layer.order == 2
    )
    if layer.board_property is None:
      self.fail("보드 물성이 누락되었습니다.")
    layer = replace(layer, board_property=replace(layer.board_property, Fy=1000.0, Fu=2.0))

    actual = _connection_capacity_kN(layer, request.bolt, request.span_mm, stud_thickness_mm=_stud_t(section), stud_tensile_strength=_stud_fu(section))
    expected_bearing_n = 2.0 * 0.85 * layer.thickness_mm * request.bolt.diameter * 2.0
    expected = expected_bearing_n * (request.span_mm / 2.0) / 1000.0 * 1e-3

    self.assertAlmostEqual(actual, expected)

  def test_c_stud_central_joint_uses_two_studs_with_25mm_gap(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    request = replace(
      request,
      stud=replace(request.stud, stud_type="C-STUD", method="중앙부 이음"),
    )

    section = _build_section(request, self.repository)
    stud = self.repository.get_stud("C-STUD", request.stud.spec)
    stud_layer = section.stud_layer
    # 조립 도심 ~ 각 스터드 도심 거리 = H + g/2 - cy (대칭 C형: H/2 + g/2)
    distance = stud.H + 25.0 / 2.0 - stud.cy
    self.assertAlmostEqual(distance, stud.H / 2.0 + 25.0 / 2.0)
    expected_i = 2.0 * (stud.A * distance**2 + stud.Ix)

    self.assertEqual(section.stud_multiplier, 2.0)
    self.assertAlmostEqual(stud_layer.thickness_mm, 2.0 * stud.H + 25.0)
    self.assertAlmostEqual(stud_layer.transformed_area_mm2, 2.0 * stud.A)
    self.assertAlmostEqual(section.stud_unfactored_self_inertia_mm4, expected_i)
    self.assertAlmostEqual(stud_layer.self_inertia_mm4, expected_i)

    result = _calculate_wall_check_once(request, self.repository)
    self.assertAlmostEqual(result.intermediate["stud_connection_inertia_factor"], 1.0)
    self.assertAlmostEqual(result.intermediate["stud_I_unfactored_mm4"], expected_i)
    stud_result = next(layer for layer in result.layers if layer.layer_type == "stud")
    se_ratio = stud.Se / stud.Sx
    # 부분합성: 합성 중립축 ~ 조립 스터드 최외단 거리 기준
    neutral_axis = result.neutral_axis_mm
    y_bottom = stud_layer.y_centroid_mm - stud_layer.thickness_mm / 2.0
    c_composite = max(neutral_axis - y_bottom, y_bottom + stud_layer.thickness_mm - neutral_axis)
    expected_s_composite = stud_result.inertia_about_neutral_axis_mm4 / c_composite * se_ratio
    # 스터드 단독: 조립 자체 도심 기준
    expected_s_stud_only = expected_i / (stud_layer.thickness_mm / 2.0) * se_ratio
    self.assertAlmostEqual(result.intermediate["stud_Se_composite_mm3"], expected_s_composite)
    self.assertAlmostEqual(result.intermediate["stud_Se_stud_only_mm3"], expected_s_stud_only)
    expected_stud_moment = 295.0 * expected_s_stud_only * 1e-6
    actual_stud_moment = _nominal_moment((stud_result,), {}, result.intermediate["stud_Se_stud_only_mm3"], result.intermediate["stud_yield_strength_MPa"])

    self.assertAlmostEqual(actual_stud_moment, expected_stud_moment)
    self.assertAlmostEqual(result.intermediate["Mn_stud_only_kNm"], expected_stud_moment)

  def test_effective_inertia_correction_factor_mapping(self) -> None:
    cases = [
      # E-11(2026-10-24): 허용처짐 상태 실측 할선강성 기준(backend/tools/r_calibration.py), 상한 1.0
      ("C-STUD", "기본", 1.00),
      ("C-STUD", "맞댐이음", 1.00),
      ("C-STUD", "중앙부 이음", 0.44),
      ("C-STUD", "중앙부연결", 0.44),
      ("CH-STUD", "기본", 0.79),
      ("CH-STUD(개량형)", "기본", 0.79),
      ("T-Silent", "기본", 0.70),
      ("T.silent-STUD", "기본", 0.70),
      ("R.STUD", "기본", 0.31),
      ("R-STUD", "기본", 0.31),
      ("I-STUD", "기본", 1.00),
      ("HR-STUD", "기본", 0.77),
      ("RV-STUD", "기본", 0.66),
      ("MP-STUD", "기본", 0.63),
    ]

    for group, method, expected in cases:
      with self.subTest(group=group, method=method):
        self.assertAlmostEqual(_effective_inertia_correction_factor(group, method), expected)

    self.assertAlmostEqual(
      _effective_inertia_correction_factor("C-STUD", "기본", has_rear_board=False),
      1.0,
    )
    self.assertAlmostEqual(
      _effective_inertia_correction_factor("C-STUD", "C-STUD", has_rear_board=False),
      1.0,
    )

  def test_effective_inertia_correction_factor_applies_only_to_i_eff(self) -> None:
    request = replace(
      request_from_golden_case(dict(self.cases[0])),
      rear_boards=(BoardLayer("방화", 25.0),),
      front_boards=(BoardLayer("방화", 19.0),),
      stud=StudInput(stud_type="CH-STUD", spec="102CHS-08", method="기본"),
    )

    result = _calculate_wall_check_once(request, self.repository)
    layer_inertia_sum = sum(layer.inertia_about_neutral_axis_mm4 for layer in result.layers)

    self.assertAlmostEqual(result.intermediate["I_eff_correction_factor"], 0.79)
    self.assertAlmostEqual(result.I_full_mm4, layer_inertia_sum)
    self.assertAlmostEqual(
      result.I_eff_mm4,
      result.intermediate["I_eff_raw_mm4"] * result.intermediate["I_eff_correction_factor"],
    )

    central_request = replace(
      request_from_golden_case(dict(self.cases[0])),
      stud=StudInput(stud_type="C-STUD", spec="50S-45-08", method="중앙부 이음"),
    )
    central_result = _calculate_wall_check_once(central_request, self.repository)

    self.assertAlmostEqual(central_result.intermediate["I_eff_correction_factor"], 0.44)
    self.assertAlmostEqual(
      central_result.I_eff_mm4,
      max(
        central_result.intermediate["I_eff_raw_mm4"] * 0.44,
        central_result.intermediate["I_eff_lower_bound_mm4"],
      ),
    )

  def test_effective_inertia_is_not_below_bare_stud_inertia(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    # 피스 간격을 극단적으로 넓혀 합성도를 0에 가깝게 → 하한(스터드 단독 강성) 지배
    sparse = replace(request, bolt=replace(request.bolt, pitch=(1.0e9, 1.0e9, 1.0e9)))
    result = _calculate_wall_check_once(sparse, self.repository)
    stud = self.repository.get_stud("C-STUD", request.stud.spec)

    self.assertAlmostEqual(result.intermediate["I_eff_lower_bound_mm4"], 2.0 * stud.Ix)
    self.assertGreaterEqual(result.I_eff_mm4, result.intermediate["I_eff_lower_bound_mm4"])
    self.assertEqual(result.intermediate["I_eff_lower_bound_governs"], 1.0)

  def test_asymmetric_stud_only_section_modulus_uses_larger_extreme_fiber(self) -> None:
    request = replace(
      request_from_golden_case(dict(self.cases[0])),
      rear_boards=(BoardLayer("방화", 25.0),),
      front_boards=(BoardLayer("방화", 19.0),),
      stud=StudInput(stud_type="CH-STUD", spec="102CHS-08", method="기본"),
    )
    result = _calculate_wall_check_once(request, self.repository)
    stud = self.repository.get_stud("CH-STUD", "102CHS-08")
    c_max = max(stud.cy, stud.H - stud.cy)

    self.assertAlmostEqual(result.intermediate["stud_extreme_fiber_stud_only_mm"], c_max)
    self.assertAlmostEqual(result.intermediate["stud_Se_stud_only_mm3"], stud.Ix / c_max * stud.Se / stud.Sx)
    self.assertAlmostEqual(result.intermediate["Mn_stud_only_kNm"], 295.0 * stud.Se * stud.Ix / c_max / stud.Sx * 1e-6)

  def test_reaction_result_is_converted_to_required_kN_per_m(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    result = _calculate_wall_check_once(request, self.repository)
    spacing_m = request.spacing_mm / 1000.0
    span_m = request.span_mm / 1000.0
    expected_live = request.live_load_kN_m2 * span_m * spacing_m / 2.0 / spacing_m
    expected_seismic = result.intermediate["Fp_kN"] / 2.0 * 2.0 / spacing_m
    expected_0_7E = 0.7 * expected_seismic
    expected_0_75L_0_525E = 0.75 * expected_live + 0.75 * 0.7 * expected_seismic
    expected_required = max(expected_live, expected_0_7E, expected_0_75L_0_525E)
    expected_anchor_allowable_spacing = 200.0
    expected_anchor_capacity_per_m = request.anchor_capacity_kN / (request.anchor_spacing_mm / 1000.0)
    expected_anchor_utilization = expected_required / expected_anchor_capacity_per_m

    self.assertAlmostEqual(result.intermediate["reaction_L_kN_per_m"], expected_live)
    self.assertAlmostEqual(result.intermediate["reaction_0_7E_kN_per_m"], expected_0_7E)
    self.assertAlmostEqual(
      result.intermediate["reaction_0_75L_0_525E_kN_per_m"],
      expected_0_75L_0_525E,
    )
    self.assertAlmostEqual(result.intermediate["reaction_required_kN_per_m"], expected_required)
    self.assertAlmostEqual(result.intermediate["anchor_capacity_kN"], 0.4)
    self.assertAlmostEqual(result.intermediate["anchor_spacing_mm"], request.anchor_spacing_mm)
    self.assertAlmostEqual(result.intermediate["anchor_allowable_spacing_mm"], expected_anchor_allowable_spacing)
    self.assertAlmostEqual(result.intermediate["anchor_capacity_kN_per_m"], expected_anchor_capacity_per_m)
    self.assertAlmostEqual(result.intermediate["anchor_utilization"], expected_anchor_utilization)

    stronger_anchor_result = _calculate_wall_check_once(
      replace(request, anchor_capacity_kN=0.8),
      self.repository,
    )
    self.assertAlmostEqual(stronger_anchor_result.intermediate["anchor_capacity_kN"], 0.8)
    expected_stronger_spacing = math.floor(0.8 / expected_required * 1000.0 / 50.0) * 50.0
    self.assertAlmostEqual(expected_stronger_spacing, 450.0)
    self.assertAlmostEqual(stronger_anchor_result.intermediate["anchor_allowable_spacing_mm"], expected_stronger_spacing)

  def test_screw_tension_pullout_and_pull_through(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    result = _calculate_wall_check_once(request, self.repository)
    stud = self.repository.get_stud("C-STUD", request.stud.spec)
    intermediate = result.intermediate
    max_pitch = max(request.bolt.pitch)
    # 양면 2P → 피치는 order 1·2 기준. 요구 인장력 = q × s × p
    expected_demand = (
      intermediate["screw_tension_pressure_kN_m2"] * 1e-3 * request.spacing_mm * intermediate["screw_tension_spacing_mm"]
    )
    expected_pullout = 0.85 * stud.t * request.bolt.diameter * 400.0

    self.assertLessEqual(intermediate["screw_tension_spacing_mm"], max_pitch)
    self.assertGreaterEqual(intermediate["screw_tension_pressure_kN_m2"], request.live_load_kN_m2)
    self.assertAlmostEqual(intermediate["screw_tension_demand_N"], expected_demand)
    self.assertAlmostEqual(intermediate["screw_pullout_nominal_N"], expected_pullout)
    self.assertAlmostEqual(intermediate["screw_pullout_allowable_N"], expected_pullout / 3.0)
    self.assertAlmostEqual(intermediate["screw_pull_through_allowable_N"], 343.0 / 3.0)
    self.assertAlmostEqual(
      intermediate["screw_tension_utilization"],
      max(intermediate["screw_pullout_utilization"], intermediate["screw_pull_through_utilization"]),
    )
    self.assertEqual(result.screw_tension_verdict, "O.K")

    non_seismic = _calculate_wall_check_once(replace(request, design_case="non_seismic"), self.repository)
    self.assertAlmostEqual(non_seismic.intermediate["screw_tension_pressure_kN_m2"], request.live_load_kN_m2)

  def test_screw_tension_ng_blocks_allowable_height(self) -> None:
    request = replace(request_from_golden_case(dict(self.cases[0])), screw_pull_through_nominal_N=10.0)
    result = calculate_wall_check(request, self.repository)

    self.assertEqual(result.screw_tension_verdict, "N.G")
    self.assertEqual(result.max_height_mm, 0.0)
    self.assertEqual(result.anchor_max_height_mm, 0.0)

  def test_screw_pull_through_must_be_positive(self) -> None:
    request = replace(request_from_golden_case(dict(self.cases[0])), screw_pull_through_nominal_N=0.0)
    with self.assertRaisesRegex(ValueError, "풀스루"):
      _calculate_wall_check_once(request, self.repository)

  def test_deflection_uses_live_load_kn_m2(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    base = _calculate_wall_check_once(request, self.repository)
    legacy_horizontal_changed = _calculate_wall_check_once(
      replace(request, horizontal_load_kg_m2=request.horizontal_load_kg_m2 * 2.0),
      self.repository,
    )
    live_load_changed = _calculate_wall_check_once(
      replace(request, live_load_kN_m2=request.live_load_kN_m2 * 2.0),
      self.repository,
    )

    self.assertAlmostEqual(legacy_horizontal_changed.deflection_mm, base.deflection_mm)
    self.assertGreater(live_load_changed.deflection_mm, base.deflection_mm)

  def test_non_seismic_case_checks_only_l_load_combination(self) -> None:
    seismic_request = request_from_golden_case(dict(self.cases[0]))
    non_seismic_request = replace(seismic_request, design_case="non_seismic")
    result = _calculate_wall_check_once(non_seismic_request, self.repository)
    expected_live_moment = result.intermediate["moment_L_kNm"]
    expected_live_reaction = result.intermediate["reaction_L_kN_per_m"]

    self.assertEqual(result.design_case, "non_seismic")
    self.assertNotIn("reaction_0_7E_kN_per_m", result.intermediate)
    self.assertNotIn("reaction_0_75L_0_525E_kN_per_m", result.intermediate)
    self.assertNotIn("anchor_capacity_kN", result.intermediate)
    self.assertNotIn("anchor_spacing_mm", result.intermediate)
    self.assertAlmostEqual(result.Mu_kNm, expected_live_moment)
    self.assertAlmostEqual(result.intermediate["reaction_required_kN_per_m"], expected_live_reaction)

  def test_ch_stud_rear_board_is_inserted_without_offsetting_stud_centroid(self) -> None:
    request = replace(
      request_from_golden_case(dict(self.cases[0])),
      rear_boards=(BoardLayer("방화", 25.0),),
      front_boards=(BoardLayer("방화", 19.0),),
      stud=StudInput(stud_type="CH-STUD", spec="102CHS-08", method="기본"),
    )

    section = _build_section(request, self.repository)
    result = _calculate_wall_check_once(request, self.repository)
    stud = self.repository.get_stud("CH-STUD", "102CHS-08")
    stud_layer = section.stud_layer
    front_layer = next(layer for layer in section.layers if layer.layer_type == "board" and layer.y_centroid_mm > stud.H)
    expected_neutral_axis = sum(layer.transformed_area_mm2 * layer.y_centroid_mm for layer in section.layers) / sum(
      layer.transformed_area_mm2 for layer in section.layers
    )

    self.assertAlmostEqual(stud_layer.thickness_mm, stud.H)
    self.assertAlmostEqual(stud_layer.y_centroid_mm, stud.cy)
    self.assertAlmostEqual(front_layer.y_centroid_mm, stud.H + 19.0 / 2.0)
    self.assertAlmostEqual(result.neutral_axis_mm, expected_neutral_axis)

  def test_ch_stud_rear_board_is_screwed_at_fixed_pitch(self) -> None:
    cases = [
      ("CH-STUD", 25.0, "방화-25-0"),
      ("CH-STUD(개량형)", 12.5, "방화-12.5-0"),
    ]
    for group, thickness, rear_board_prefix in cases:
      with self.subTest(group=group):
        request = replace(
          request_from_golden_case(dict(self.cases[0])),
          rear_boards=(BoardLayer("방화", thickness),),
          front_boards=(BoardLayer("방화", 19.0),),
          stud=StudInput(stud_type=group, spec="102CHS-08", method="기본"),
        )

        result = _calculate_wall_check_once(request, self.repository)
        rear_board = next(
          layer
          for layer in result.layers
          if layer.layer_type == "board" and layer.name.startswith(rear_board_prefix)
        )

        # 고정 후면 보드: 피스 간격 300 mm, 피치당 2개(완전합성 가정 폐지)
        per_screw = min(
          785.0840041320893,
          2.0 * 0.85 * thickness * 3.5 * self.repository.get_board("방화", thickness).Fu,
          _screw_stud_side_shear_N(_stud_t(_build_section(request, self.repository)), 3.5, 400.0),
        )
        expected = min(rear_board.axial_strength_kN, per_screw * 2.0 * (request.span_mm / 2.0) / 300.0 * 1e-3)
        self.assertAlmostEqual(rear_board.cumulative_shear_kN, expected, places=6)
        self.assertLessEqual(rear_board.strength_shear_kN, rear_board.cumulative_shear_kN)

  def test_ch_stud_improved_keeps_group_and_uses_12mm_class_rear_board(self) -> None:
    request = replace(
      request_from_golden_case(dict(self.cases[0])),
      rear_boards=(BoardLayer("방화", 12.5),),
      front_boards=(BoardLayer("방화", 19.0),),
      stud=StudInput(stud_type="CH-STUD(개량형)", spec="102CHS-08", method="기본"),
    )

    section = _build_section(request, self.repository)
    stud = self.repository.get_stud("CH-STUD(개량형)", "102CHS-08")
    stud_layer = section.stud_layer

    self.assertEqual(stud_layer.name, "CH-STUD(개량형)-102CHS-08")
    self.assertAlmostEqual(stud_layer.y_centroid_mm, stud.cy)
    self.assertAlmostEqual(stud_layer.self_inertia_mm4, stud.Ix)

  def test_ch_stud_rejects_invalid_rear_board_layout(self) -> None:
    request = replace(
      request_from_golden_case(dict(self.cases[0])),
      rear_boards=(BoardLayer("방화", 19.0),),
      stud=StudInput(stud_type="CH-STUD", spec="102CHS-08", method="기본"),
    )

    with self.assertRaisesRegex(ValueError, "25T"):
      _build_section(request, self.repository)

  def test_i_stud_uses_fixed_fire_rated_25mm_rear_board_without_offsetting_stud(self) -> None:
    request = replace(
      request_from_golden_case(dict(self.cases[0])),
      rear_boards=(BoardLayer("방화", 25.0),),
      front_boards=(BoardLayer("방화", 19.0),),
      stud=StudInput(stud_type="I-STUD", spec="I-STUD 102-08", method="기본"),
    )

    section = _build_section(request, self.repository)
    result = _calculate_wall_check_once(request, self.repository)
    stud = self.repository.get_stud("I-STUD", "I-STUD 102-08")
    stud_layer = section.stud_layer
    front_layer = next(layer for layer in section.layers if layer.layer_type == "board" and layer.y_centroid_mm > stud.H)
    rear_board = next(layer for layer in result.layers if layer.layer_type == "board" and layer.name.startswith("방화-25-0"))

    self.assertAlmostEqual(stud_layer.y_centroid_mm, stud.cy)
    self.assertAlmostEqual(front_layer.y_centroid_mm, stud.H + 19.0 / 2.0)
    per_screw = min(
      785.0840041320893,
      2.0 * 0.85 * 25.0 * 3.5 * self.repository.get_board("방화", 25.0).Fu,
      _screw_stud_side_shear_N(_stud_t(section), 3.5, _stud_fu(section)),
    )
    expected = min(rear_board.axial_strength_kN, per_screw * 2.0 * (request.span_mm / 2.0) / 300.0 * 1e-3)
    self.assertAlmostEqual(rear_board.cumulative_shear_kN, expected, places=6)

  def test_stiffness_load_factor_is_one_sided(self) -> None:
    base = request_from_golden_case(dict(self.cases[0]))
    result = _calculate_wall_check_once(base, self.repository)
    # 표준 조건: 피스력이 시험 수준 이하 → 보정 없음
    self.assertLess(result.intermediate["screw_utilization_ratio"], 1.0)
    self.assertEqual(result.intermediate["stiffness_load_factor"], 1.0)

    # 피스 간격 2배·고하중 → u/u_ref > 1 → 강성 저감
    heavy = replace(
      base,
      live_load_kN_m2=1.0,
      bolt=replace(base.bolt, pitch=tuple(2.0 * value for value in base.bolt.pitch)),
    )
    heavy_result = _calculate_wall_check_once(heavy, self.repository)
    # 형식별 V* (C-STUD 맞댐 → C-STUD 형식, R 보정점 피스력)
    v_ref = STIFFNESS_REF_SUPPORT_SHEAR_N_BY_TYPE[STIFFNESS_TYPE_C]
    self.assertAlmostEqual(_stiffness_reference_shear_N("C-STUD", "맞댐"), v_ref)
    expected_ratio = 1.0e-3 * heavy.spacing_mm * heavy.span_mm / 2.0 / v_ref * 2.0
    m = heavy_result.intermediate["stiffness_curve_exponent_m"]
    self.assertAlmostEqual(heavy_result.intermediate["screw_utilization_ratio"], expected_ratio)
    self.assertGreater(expected_ratio, 1.0)
    self.assertAlmostEqual(heavy_result.intermediate["stiffness_load_factor"], expected_ratio ** (1.0 - m))
    self.assertAlmostEqual(
      heavy_result.I_eff_mm4,
      max(
        heavy_result.intermediate["I_eff_raw_mm4"]
        * heavy_result.intermediate["I_eff_correction_factor"]
        * heavy_result.intermediate["stiffness_load_factor"],
        heavy_result.intermediate["I_eff_lower_bound_mm4"],
      ),
    )

  def test_gypsum_screw_design_shear_from_aisi_s240(self) -> None:
    # AISI S240-20 해설 Table C-B3.2-1 (No.6): 12.7 mm 516 N, 15.9 mm 605 N, 설계 = 극한 / 2.0
    self.assertAlmostEqual(_gypsum_screw_design_shear_N(12.7), 258.0)
    self.assertAlmostEqual(_gypsum_screw_design_shear_N(15.9), 302.5)
    self.assertAlmostEqual(_gypsum_screw_design_shear_N(19.0), 302.5)
    self.assertAlmostEqual(_gypsum_screw_design_shear_N(9.5), 516.0 * 9.5 / 12.7 / 2.0)

  def test_screw_design_strength_applies_only_to_mn(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    result = _calculate_wall_check_once(request, self.repository)
    boards = [layer for layer in result.layers if layer.layer_type == "board"]
    # 강도용 누계는 강성용 이하, η(강성)는 강성용 누계 기준
    for layer in boards:
      self.assertLessEqual(layer.strength_shear_kN, layer.cumulative_shear_kN + 1e-12)
    expected_mn = sum(
      abs(min(layer.axial_strength_kN, layer.strength_shear_kN) * layer.distance_to_neutral_axis_mm * 1e-3)
      for layer in boards
    ) + 295.0 * result.intermediate["stud_Se_composite_mm3"] * 1e-6
    self.assertAlmostEqual(result.intermediate["Mn_composite_kNm"], expected_mn)

  def test_i_stud_rejects_unregistered_rear_board_material(self) -> None:
    request = replace(
      request_from_golden_case(dict(self.cases[0])),
      rear_boards=(BoardLayer("일반", 25.0),),
      stud=StudInput(stud_type="I-STUD", spec="I-STUD 102-08", method="기본"),
    )

    # 자유선택은 등록된 물성 범위 내에서만 허용한다. 일반 25T는 DB에 없다.
    with self.assertRaisesRegex(ValueError, "등록되지 않은 석고보드"):
      _build_section(request, self.repository)

  def test_r_stud_uses_12mm_clear_gap_between_1p_board_and_stud(self) -> None:
    request = replace(
      request_from_golden_case(dict(self.cases[0])),
      rear_boards=(BoardLayer("방화", 19.0),),
      front_boards=(BoardLayer("방화", 19.0),),
      stud=StudInput(stud_type="R-STUD", spec="75S-45-08", method="기본"),
    )

    section = _build_section(request, self.repository)
    stud = self.repository.get_stud("R-STUD", "75S-45-08")
    rear_board = next(layer for layer in section.layers if layer.name.startswith("방화-19-0"))
    stud_layer = next(layer for layer in section.layers if layer.layer_type == "stud")
    front_board = next(
      layer
      for layer in section.layers
      if layer.layer_type == "board" and not layer.name.startswith("방화-19-0")
    )

    self.assertAlmostEqual(rear_board.y_centroid_mm, 19.0 / 2.0)
    self.assertAlmostEqual(stud_layer.y_centroid_mm, 19.0 + 12.0 + stud.cy)
    self.assertAlmostEqual(front_board.y_centroid_mm, 19.0 + 12.0 + stud.H + 12.0 + 19.0 / 2.0)

  def test_max_height_is_checked_by_50mm_increment(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    result = calculate_wall_check(request, self.repository)

    self.assertGreater(result.max_height_mm, 0)
    self.assertEqual(result.max_height_increment_mm, 50.0)
    self.assertEqual(result.max_height_mm % result.max_height_increment_mm, 0)

    max_height_result = _calculate_wall_check_once(
      replace(request, span_mm=result.max_height_mm),
      self.repository,
    )
    next_height_result = _calculate_wall_check_once(
      replace(request, span_mm=result.max_height_mm + result.max_height_increment_mm),
      self.repository,
    )

    self.assertEqual(max_height_result.stress_verdict, "O.K")
    self.assertEqual(max_height_result.deflection_verdict, "O.K")
    self.assertTrue(
      next_height_result.stress_verdict == "N.G" or next_height_result.deflection_verdict == "N.G",
    )

  def _assert_close(self, key: str, actual: float, expected: Mapping[str, object]) -> None:
    target = float(expected[key])
    denominator = max(abs(target), 1.0)
    relative_error = abs(actual - target) / denominator
    self.assertLessEqual(
      relative_error,
      self.tolerance_rel,
      f"{key}: actual={actual}, expected={target}, rel={relative_error}",
    )


if __name__ == "__main__":
  unittest.main()
