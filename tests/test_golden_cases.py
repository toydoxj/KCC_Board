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
  _effective_inertia_correction_factor,
  _nominal_moment,
  calculate_wall_check,
  request_from_golden_case,
)
from backend.engine.models import BoardLayer, StudInput
from backend.engine.repository import JsonSeedRepository


ROOT = Path(__file__).resolve().parents[1]


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
    self.assertEqual(stud_only.max_height_mm, 5200.0)
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

    actual = _connection_capacity_kN(layer, request.bolt, request.span_mm)
    bolt_area = math.pi / 4.0 * request.bolt.diameter**2
    expected_shear_n = 0.5 * 0.6 * request.bolt.yield_strength * 0.85 * bolt_area / 1.25
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

    actual = _connection_capacity_kN(layer, request.bolt, request.span_mm)
    bolt_area = math.pi / 4.0 * request.bolt.diameter**2
    expected_shear_n = 0.5 * 0.6 * request.bolt.yield_strength * 0.85 * bolt_area / 1.25
    expected = expected_shear_n * (request.span_mm / 2.0) / 1000.0 * 1e-3

    self.assertAlmostEqual(actual, expected)

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

    actual = _connection_capacity_kN(layer, request.bolt, request.span_mm)
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
    distance = stud.H + 25.0 / 2.0
    expected_i = 2.0 * (stud.A * distance**2 + stud.Ix)

    self.assertEqual(section.stud_multiplier, 2.0)
    self.assertAlmostEqual(stud_layer.thickness_mm, 2.0 * stud.H + 25.0)
    self.assertAlmostEqual(stud_layer.transformed_area_mm2, 2.0 * stud.A)
    self.assertAlmostEqual(section.stud_unfactored_self_inertia_mm4, expected_i)
    self.assertAlmostEqual(stud_layer.self_inertia_mm4, expected_i)
    self.assertAlmostEqual(section.stud_section_modulus_depth_mm, stud.H)

    result = _calculate_wall_check_once(request, self.repository)
    self.assertAlmostEqual(result.intermediate["stud_connection_inertia_factor"], 1.0)
    self.assertAlmostEqual(result.intermediate["stud_I_unfactored_mm4"], expected_i)
    stud_result = next(layer for layer in result.layers if layer.layer_type == "stud")
    expected_stud_section_modulus = stud_result.inertia_about_neutral_axis_mm4 / stud.H * 2.0
    expected_stud_moment = 275.0 * expected_stud_section_modulus * 1e-6
    actual_stud_moment = _nominal_moment((stud_result,), {}, section.stud_section_modulus_depth_mm)

    self.assertAlmostEqual(actual_stud_moment, expected_stud_moment)

  def test_effective_inertia_correction_factor_mapping(self) -> None:
    cases = [
      ("C-STUD", "기본", 1.0),
      ("C-STUD", "맞댐이음", 1.0),
      ("C-STUD", "중앙부 이음", 0.22),
      ("C-STUD", "중앙부연결", 0.22),
      ("CH-STUD", "기본", 0.58),
      ("CH-STUD(개량형)", "기본", 0.58),
      ("T-Silent", "기본", 0.44),
      ("T.silent-STUD", "기본", 0.44),
      ("R.STUD", "기본", 0.28),
      ("R-STUD", "기본", 0.28),
      ("I-STUD", "기본", 0.8),
      ("HR-STUD", "기본", 0.78),
      ("RV-STUD", "기본", 0.45),
      ("MP-STUD", "기본", 0.45),
    ]

    for group, method, expected in cases:
      with self.subTest(group=group, method=method):
        self.assertAlmostEqual(_effective_inertia_correction_factor(group, method), expected)

  def test_effective_inertia_correction_factor_applies_only_to_i_eff(self) -> None:
    request = replace(
      request_from_golden_case(dict(self.cases[0])),
      rear_boards=(BoardLayer("방화", 25.0),),
      front_boards=(BoardLayer("방화", 19.0),),
      stud=StudInput(stud_type="CH-STUD", spec="102CHS-08", method="기본"),
    )

    result = _calculate_wall_check_once(request, self.repository)
    layer_inertia_sum = sum(layer.inertia_about_neutral_axis_mm4 for layer in result.layers)

    self.assertAlmostEqual(result.intermediate["I_eff_correction_factor"], 0.58)
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

    self.assertAlmostEqual(central_result.intermediate["I_eff_correction_factor"], 0.22)
    self.assertAlmostEqual(
      central_result.I_eff_mm4,
      central_result.intermediate["I_eff_raw_mm4"] * 0.22,
    )

  def test_reaction_result_is_converted_to_required_kN_per_m(self) -> None:
    request = request_from_golden_case(dict(self.cases[0]))
    result = _calculate_wall_check_once(request, self.repository)
    spacing_m = request.spacing_mm / 1000.0
    span_m = request.span_mm / 1000.0
    expected_live = request.live_load_kN_m2 * span_m * spacing_m / 2.0 / spacing_m
    expected_seismic = result.intermediate["Fp_kN"] / 2.0 * 2.0 / spacing_m
    expected_0_7E = 0.7 * expected_seismic
    expected_0_75L_0_7E = 0.75 * expected_live + 0.7 * expected_seismic
    expected_required = max(expected_live, expected_0_7E, expected_0_75L_0_7E)
    expected_anchor_spacing = request.anchor_capacity_kN / expected_required * 1000.0

    self.assertAlmostEqual(result.intermediate["reaction_L_kN_per_m"], expected_live)
    self.assertAlmostEqual(result.intermediate["reaction_0_7E_kN_per_m"], expected_0_7E)
    self.assertAlmostEqual(
      result.intermediate["reaction_0_75L_0_7E_kN_per_m"],
      expected_0_75L_0_7E,
    )
    self.assertAlmostEqual(result.intermediate["reaction_required_kN_per_m"], expected_required)
    self.assertAlmostEqual(result.intermediate["anchor_capacity_kN"], 0.4)
    self.assertAlmostEqual(result.intermediate["anchor_spacing_mm"], expected_anchor_spacing)

    stronger_anchor_result = _calculate_wall_check_once(
      replace(request, anchor_capacity_kN=0.8),
      self.repository,
    )
    self.assertAlmostEqual(stronger_anchor_result.intermediate["anchor_capacity_kN"], 0.8)
    self.assertAlmostEqual(stronger_anchor_result.intermediate["anchor_spacing_mm"], expected_anchor_spacing * 2.0)

  def test_non_seismic_case_checks_only_l_load_combination(self) -> None:
    seismic_request = request_from_golden_case(dict(self.cases[0]))
    non_seismic_request = replace(seismic_request, design_case="non_seismic")
    result = _calculate_wall_check_once(non_seismic_request, self.repository)
    expected_live_moment = result.intermediate["moment_L_kNm"]
    expected_live_reaction = result.intermediate["reaction_L_kN_per_m"]

    self.assertEqual(result.design_case, "non_seismic")
    self.assertNotIn("reaction_0_7E_kN_per_m", result.intermediate)
    self.assertNotIn("reaction_0_75L_0_7E_kN_per_m", result.intermediate)
    self.assertAlmostEqual(result.Mu_kNm, expected_live_moment)
    self.assertAlmostEqual(result.intermediate["reaction_required_kN_per_m"], expected_live_reaction)
    self.assertAlmostEqual(
      result.intermediate["anchor_spacing_mm"],
      non_seismic_request.anchor_capacity_kN / expected_live_reaction * 1000.0,
    )

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

  def test_ch_stud_rear_board_is_fully_composite_with_stud(self) -> None:
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

        self.assertAlmostEqual(rear_board.cumulative_shear_kN, rear_board.axial_strength_kN)

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
    self.assertAlmostEqual(rear_board.cumulative_shear_kN, rear_board.axial_strength_kN)

  def test_i_stud_rejects_non_fire_rated_25mm_rear_board(self) -> None:
    request = replace(
      request_from_golden_case(dict(self.cases[0])),
      rear_boards=(BoardLayer("일반", 25.0),),
      stud=StudInput(stud_type="I-STUD", spec="I-STUD 102-08", method="기본"),
    )

    with self.assertRaisesRegex(ValueError, "방화 25T"):
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
