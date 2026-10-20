"""결과 안내(표준 외 피스 간격 경고, 심사의견 F-4) 테스트."""

from __future__ import annotations

import json
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from typing import Mapping, cast

from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.engine.calculator import _calculate_wall_check_once, request_from_golden_case
from backend.engine.constants import STANDARD_SCREW_PITCH_MM
from backend.engine.models import BoardLayer, StudInput
from backend.engine.repository import JsonSeedRepository


ROOT = Path(__file__).resolve().parents[1]


class ScrewPitchNoticeTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.repository = JsonSeedRepository(ROOT / "data/seed")
    with (ROOT / "tests/golden/cases.json").open(encoding="utf-8") as file:
      data = cast(Mapping[str, object], json.load(file))
    cases = cast(list[Mapping[str, object]], data["cases"])
    cls.request = request_from_golden_case(dict(cases[0]))

  def _with_pitch(self, pitch: tuple[float, ...]):
    return replace(self.request, bolt=replace(self.request.bolt, pitch=pitch))

  def test_standard_pitch_has_no_notice(self) -> None:
    result = _calculate_wall_check_once(self._with_pitch(STANDARD_SCREW_PITCH_MM), self.repository)

    self.assertEqual(result.notices, ())

  def test_non_standard_inner_pitch_adds_notice(self) -> None:
    outer, middle, _ = STANDARD_SCREW_PITCH_MM
    result = _calculate_wall_check_once(self._with_pitch((outer, middle, 450.0)), self.repository)

    self.assertEqual(len(result.notices), 1)
    self.assertIn("1번(내측)", result.notices[0])
    self.assertIn("450", result.notices[0])

  def test_ch_stud_fixed_rear_board_is_excluded(self) -> None:
    # CH-STUD 후면 보드는 피스 간격 300 mm 고정 — 입력 피치가 표준과 달라도 경고 대상이 아니다
    request = replace(
      self._with_pitch((450.0, 450.0, 450.0)),
      stud=StudInput(stud_type="CH-STUD", spec="75CHS-08"),
      rear_boards=(BoardLayer(kind="방화", thickness=25.0, order=1),),
      front_boards=(),
    )
    result = _calculate_wall_check_once(request, self.repository)

    self.assertEqual(result.notices, ())

  def test_order_above_three_does_not_duplicate_outer_notice(self) -> None:
    # order ≥ 3은 모두 3번(외측) 피치를 쓰므로 경고도 1건이어야 한다
    _, middle, inner = STANDARD_SCREW_PITCH_MM
    front = tuple(
      BoardLayer(kind=board.kind, thickness=board.thickness, order=order)
      for order, board in zip((1, 2, 3, 4), self.request.front_boards * 4)
    )
    request = replace(self._with_pitch((450.0, middle, inner)), front_boards=front)
    result = _calculate_wall_check_once(request, self.repository)

    self.assertEqual(len(result.notices), 1)
    self.assertIn("3번(외측)", result.notices[0])

  def test_api_returns_notices(self) -> None:
    outer, middle, _ = STANDARD_SCREW_PITCH_MM
    payload = asdict(self._with_pitch((outer, middle, 450.0)))
    response = TestClient(create_app(self.repository)).post("/api/check", json=payload)

    self.assertEqual(response.status_code, 200)
    notices = response.json()["data"]["notices"]
    self.assertEqual(len(notices), 1)
    self.assertIn("1번(내측)", notices[0])


if __name__ == "__main__":
  unittest.main()
