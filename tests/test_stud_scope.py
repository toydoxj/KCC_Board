"""스터드 형식 적용 범위 테스트 — 시험 보정계수 R이 없는 형식은 계산을 거부한다(2026-10-24)."""

from __future__ import annotations

import json
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.engine.calculator import (
  CH_STUD_IMPROVED_REAR_BOARD_THICKNESS_MM,
  _calculate_wall_check_once,
  _effective_inertia_correction_factor,
  _stiffness_curve_exponent,
  _stiffness_reference_shear_N,
  calculate_wall_check,
)
from backend.engine.models import StudInput, WallCheckRequest
from backend.engine.repository import JsonSeedRepository
from backend.tools.r_calibration import specimen_requests


ROOT = Path(__file__).resolve().parents[1]
UNREGISTERED_GROUPS = ("SH-STUD", "임의 형식")


class _AliasStudRepository(JsonSeedRepository):
  """미등록 그룹의 단면 조회를 C-STUD 단면으로 대체한다(단면 조립을 통과시켜 R 조회 시점 차단을 확인)."""

  def get_stud(self, group: str, spec: str):  # type: ignore[override]
    return super().get_stud("C-STUD" if group in UNREGISTERED_GROUPS else group, spec)


class UnregisteredStudTypeTest(unittest.TestCase):
  def test_stiffness_lookups_reject_unregistered_group(self) -> None:
    for group in UNREGISTERED_GROUPS:
      for has_rear_board in (True, False):
        with self.subTest(group=group, has_rear_board=has_rear_board):
          with self.assertRaisesRegex(ValueError, "적용 범위 밖"):
            _effective_inertia_correction_factor(group, group, has_rear_board)
          with self.assertRaisesRegex(ValueError, "적용 범위 밖"):
            _stiffness_reference_shear_N(group, group, has_rear_board)
          with self.assertRaisesRegex(ValueError, "적용 범위 밖"):
            _stiffness_curve_exponent(group, group, has_rear_board)

  def test_calculation_rejects_unregistered_group(self) -> None:
    repository = _AliasStudRepository(ROOT / "data/seed")
    base = specimen_requests()["requested_04_c_stud_basic"]
    for group in UNREGISTERED_GROUPS:
      with self.subTest(group=group):
        request = replace(base, stud=StudInput(stud_type=group, spec=base.stud.spec))
        with self.assertRaisesRegex(ValueError, "적용 범위 밖"):
          calculate_wall_check(request, repository)

  def test_api_returns_scope_error_message(self) -> None:
    client = TestClient(create_app(_AliasStudRepository(ROOT / "data/seed")))
    base = specimen_requests()["requested_04_c_stud_basic"]
    payload = asdict(replace(base, stud=StudInput(stud_type="SH-STUD", spec=base.stud.spec)))
    response = client.post("/api/check", json=payload)
    self.assertEqual(response.status_code, 400)
    body = response.json()
    self.assertFalse(body["success"])
    self.assertIsNone(body["data"])
    self.assertEqual(body["error"]["code"], "CALCULATION_ERROR")
    self.assertIn("SH-STUD(SH-STUD)은(는) 시험 보정계수 R이 산정되지 않은 형식", body["error"]["message"])


class RegisteredStudTypeTest(unittest.TestCase):
  def test_curve_exponent_values_unchanged(self) -> None:
    # 분류명 기준 표로 바꾼 뒤에도 형식별 m은 종전 값과 같아야 한다
    cases = [
      ("C-STUD", "기본", True, 1.38),
      ("C-STUD", "기본", False, 1.38),
      ("C-STUD", "일면마감", False, 1.38),
      ("C-STUD", "이중스터드", False, 1.38),
      ("C-STUD", "맞댐이음", True, 1.49),
      ("C-STUD", "맞댐이음", False, 1.49),
      ("C-STUD", "중앙부 이음", True, 1.49),
      ("C-STUD", "중앙부연결", True, 1.49),
      ("CH-STUD", "CH-STUD", True, 1.25),
      ("CH-STUD(개량형)", "CH-STUD(개량형)", True, 1.25),
      ("T-Silent", "T-Silent", True, 1.29),
      ("T.silent-STUD", "T.silent-STUD", True, 1.29),
      ("R.STUD", "R.STUD", True, 1.11),
      ("R-STUD", "R-STUD", True, 1.11),
      ("I-STUD", "I-STUD", True, 1.26),
      ("HR-STUD", "HR-STUD", True, 1.33),
      ("RV-STUD", "RV-STUD", True, 1.25),
      ("MP-STUD", "MP-STUD", True, 1.24),
    ]
    for group, method, has_rear_board, expected in cases:
      with self.subTest(group=group, method=method, has_rear_board=has_rear_board):
        self.assertEqual(_stiffness_curve_exponent(group, method, has_rear_board), expected)

  def test_all_seed_stud_sections_are_calculable(self) -> None:
    # 시드 DB의 모든 단면 그룹 × 공법이 차단되지 않아야 한다
    repository = JsonSeedRepository(ROOT / "data/seed")
    sections = json.loads((ROOT / "data/seed/stud_section.json").read_text(encoding="utf-8"))["items"]
    methods = json.loads((ROOT / "data/seed/stud_method.json").read_text(encoding="utf-8"))["items"]
    c_methods = [item["method"] for item in methods if item["stud_type"] == "C-STUD"]
    for section in sections:
      group = section["group"]
      for method in c_methods if group == "C-STUD" else [None]:
        with self.subTest(group=group, spec=section["name"], method=method):
          request = _base_request(group, method)
          request = replace(request, stud=StudInput(stud_type=group, spec=section["name"], method=method))
          _calculate_wall_check_once(request, repository)


def _base_request(group: str, method: str | None) -> WallCheckRequest:
  requests = specimen_requests()
  if group == "C-STUD":
    # 일면 검토 공법은 후면 보드 없음(시편 02), 그 외는 양면(시편 04)
    one_side = method is not None and method.replace(" ", "") in {"일면마감", "이중스터드"}
    return requests["requested_02_c_stud_basic_front_only" if one_side else "requested_04_c_stud_basic"]
  base_by_group = {
    "CH-STUD": "requested_05_ch_stud_75",
    "CH-STUD(개량형)": "requested_05_ch_stud_75",
    "HR-STUD": "requested_06_hr_stud_124",
    "MP-STUD": "requested_07_mp_stud_74",
    "RV-STUD": "requested_08_rv_stud_74",
    "T.silent-STUD": "requested_09_t_silent_stud_74",
    "R-STUD": "requested_10_r_stud_75",
    "I-STUD": "requested_11_i_stud_75",
  }
  request = requests[base_by_group[group]]
  if group == "CH-STUD(개량형)":
    rear = request.rear_boards[0]
    request = replace(request, rear_boards=(replace(rear, thickness=CH_STUD_IMPROVED_REAR_BOARD_THICKNESS_MM),))
  return request


if __name__ == "__main__":
  unittest.main()
