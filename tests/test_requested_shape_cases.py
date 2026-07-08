"""User-requested stud shape regression cases."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Mapping, Sequence, cast

from backend.engine.calculator import _calculate_wall_check_once, calculate_wall_check
from backend.engine.models import BoardLayer, BoltInput, SeismicInput, StudInput, WallCheckRequest
from backend.engine.repository import JsonSeedRepository


ROOT = Path(__file__).resolve().parents[1]


class RequestedShapeCaseTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.repository = JsonSeedRepository(ROOT / "data/seed")
    with (ROOT / "tests/golden/requested_shape_cases.json").open(encoding="utf-8") as file:
      data = cast(Mapping[str, object], json.load(file))
    cls.tolerance_rel = float(data["_tolerance_rel"])
    cls.common = cast(Mapping[str, object], data["common"])
    cls.cases = cast(Sequence[Mapping[str, object]], data["cases"])

  def test_requested_shape_reference_values(self) -> None:
    for case in self.cases:
      with self.subTest(case=case["id"]):
        request = self._request(case)
        result_at_2400 = calculate_wall_check(request, self.repository)
        expected = cast(Mapping[str, object], case["expected"])

        self.assertEqual(result_at_2400.max_height_mm, float(expected["max_height_mm"]))
        self._assert_close(
          "I_eff_raw_at_2400_mm4",
          float(result_at_2400.intermediate["I_eff_raw_mm4"]),
          expected,
        )
        self._assert_close(
          "I_eff_correction_factor",
          float(result_at_2400.intermediate["I_eff_correction_factor"]),
          expected,
        )

        result_at_expected_max = _calculate_wall_check_once(
          replace(request, span_mm=float(expected["max_height_mm"])),
          self.repository,
        )
        self._assert_close("Mu_at_max_height_kNm", result_at_expected_max.Mu_kNm, expected)

  def _request(self, case: Mapping[str, object]) -> WallCheckRequest:
    common = self.common
    input_data = cast(Mapping[str, object], case["input"])
    bolt = cast(Mapping[str, object], common["bolt"])
    seismic = cast(Mapping[str, object], common["seismic"])

    return WallCheckRequest(
      rear_boards=self._boards(cast(Sequence[Mapping[str, object]], input_data["rear_boards"])),
      front_boards=self._boards(cast(Sequence[Mapping[str, object]], input_data["front_boards"])),
      stud=StudInput(
        stud_type=str(input_data["stud_type"]),
        spec=str(input_data["stud_spec"]),
        method=None if input_data.get("method") is None else str(input_data["method"]),
      ),
      horizontal_load_kg_m2=float(common["horizontal_load_kg_m2"]),
      live_load_kN_m2=float(common["live_load_kN_m2"]),
      vertical_load_kN_m=float(common["vertical_load_kN_m"]),
      spacing_mm=float(input_data["spacing_mm"]),
      span_mm=float(common["span_for_ieff_mm"]),
      deflection_limit_denom=int(common["deflection_limit_denom"]),
      bolt=BoltInput(
        diameter=float(bolt["diameter"]),
        yield_strength=float(bolt["yield_strength"]),
        pitch=tuple(float(value) for value in cast(Sequence[object], bolt["pitch"])),
        count=tuple(float(value) for value in cast(Sequence[object], bolt["count"])),
      ),
      seismic=SeismicInput(
        S=float(seismic["S"]),
        Ip=float(seismic["Ip"]),
        Fa=float(seismic["Fa"]),
      ),
      design_case=str(common["design_case"]),
      strength_check_mode=str(common["strength_check_mode"]),
      omega=float(common["omega"]),
      anchor_capacity_kN=float(common["anchor_capacity_kN"]),
      anchor_spacing_mm=float(common["anchor_spacing_mm"]),
    )

  @staticmethod
  def _boards(raw_boards: Sequence[Mapping[str, object]]) -> tuple[BoardLayer, ...]:
    return tuple(
      BoardLayer(
        kind=str(board["kind"]),
        thickness=float(board["thickness"]),
        order=None if board.get("order") is None else int(board["order"]),
      )
      for board in raw_boards
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
