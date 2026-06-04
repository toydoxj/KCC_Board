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
  calculate_wall_check,
  request_from_golden_case,
)
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

  def test_bolt_shear_uses_yield_strength_factor(self) -> None:
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
    expected_shear_n = 0.6 * request.bolt.yield_strength * bolt_area / 1.25
    expected = expected_shear_n * (request.span_mm / 2.0) / 1000.0 * 1e-3

    self.assertAlmostEqual(actual, expected)

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
