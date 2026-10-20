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

  def _c50_front_only(self, front: tuple[BoardLayer, ...]):
    return replace(
      self._with_pitch(STANDARD_SCREW_PITCH_MM),
      stud=StudInput(stud_type="C-STUD", spec="50S-45-08", method="기본"),
      rear_boards=(),
      front_boards=front,
    )

  def test_neutral_axis_within_inner_board_adds_notice(self) -> None:
    # 심사의견 E-9: 시험 시편 02 구성(전면 방화 19T 2겹) — 중립축 53.1 mm, 스터드 상단 50 mm, 1번 보드 50~69 mm
    request = self._c50_front_only((BoardLayer(kind="방화", thickness=19.0), BoardLayer(kind="방화", thickness=19.0)))
    result = _calculate_wall_check_once(request, self.repository)

    self.assertEqual(len(result.notices), 1)
    self.assertIn("중립축", result.notices[0])
    self.assertIn("1번(내측) 보드 두께 안", result.notices[0])

  def test_neutral_axis_in_board_stud_gap_uses_gap_wording(self) -> None:
    # R-STUD는 보드–스터드 12 mm 이격 — 중립축이 간극에 있으면 '간극' 문구로 경고
    request = replace(
      self._with_pitch(STANDARD_SCREW_PITCH_MM),
      stud=StudInput(stud_type="R-STUD", spec="100S-45-08", method="기본"),
      spacing_mm=600.0,
      rear_boards=(),
      front_boards=(BoardLayer(kind="방화", thickness=19.0), BoardLayer(kind="방화", thickness=19.0)),
    )
    result = _calculate_wall_check_once(request, self.repository)
    neutral = [notice for notice in result.notices if "중립축" in notice]

    self.assertEqual(len(neutral), 1)
    self.assertIn("간극", neutral[0])
    self.assertNotIn("두께 안", neutral[0])

  def test_rear_side_warning_and_rejection(self) -> None:
    rear_warn = replace(
      self._c50_front_only(()),
      rear_boards=(BoardLayer(kind="방화", thickness=19.0), BoardLayer(kind="방화", thickness=19.0)),
    )
    result = _calculate_wall_check_once(rear_warn, self.repository)
    self.assertTrue(any("후면" in notice and "중립축" in notice for notice in result.notices))

    # 후면 튜플은 외측(3번)→내측(1번) 순서 — 1번(내측) 일반 9.5T 아래 방화 25T 2겹
    rear_reject = replace(
      self._c50_front_only(()),
      rear_boards=(
        BoardLayer(kind="방화", thickness=25.0),
        BoardLayer(kind="방화", thickness=25.0),
        BoardLayer(kind="일반", thickness=9.5),
      ),
    )
    with self.assertRaisesRegex(ValueError, "후면"):
      _calculate_wall_check_once(rear_reject, self.repository)

  def test_neutral_axis_and_pitch_notices_are_both_returned(self) -> None:
    outer, middle, _ = STANDARD_SCREW_PITCH_MM
    request = replace(
      self._c50_front_only((BoardLayer(kind="방화", thickness=19.0), BoardLayer(kind="방화", thickness=19.0))),
      bolt=replace(self.request.bolt, pitch=(outer, middle, 450.0)),
    )
    result = _calculate_wall_check_once(request, self.repository)

    self.assertEqual(len(result.notices), 2)
    self.assertIn("중립축", result.notices[0])
    self.assertIn("1번(내측) 피스 간격", result.notices[1])

  def test_neutral_axis_inside_stud_has_no_notice(self) -> None:
    result = _calculate_wall_check_once(self._with_pitch(STANDARD_SCREW_PITCH_MM), self.repository)

    self.assertFalse(any("중립축" in notice for notice in result.notices))

  def test_neutral_axis_beyond_inner_board_is_rejected(self) -> None:
    # 1번 일반 9.5T(50~59.5 mm) 위에 방화 25T 2겹 — 중립축 62.9 mm로 1번 보드를 넘음
    request = self._c50_front_only(
      (BoardLayer(kind="일반", thickness=9.5), BoardLayer(kind="방화", thickness=25.0), BoardLayer(kind="방화", thickness=25.0))
    )

    with self.assertRaisesRegex(ValueError, "중립축"):
      _calculate_wall_check_once(request, self.repository)

    response = TestClient(create_app(self.repository)).post("/api/check", json=asdict(request))
    self.assertEqual(response.status_code, 400)
    self.assertIn("중립축", response.json()["error"]["message"])

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
