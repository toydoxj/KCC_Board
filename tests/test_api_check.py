"""FastAPI 단면검토 API 테스트."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, cast

from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.engine.calculator import request_from_golden_case
from backend.engine.repository import JsonSeedRepository, SqliteRepository, initialize_sqlite_from_seed


ROOT = Path(__file__).resolve().parents[1]


class ApiCheckTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    repository = JsonSeedRepository(ROOT / "data/seed")
    cls.client = TestClient(create_app(repository))
    with (ROOT / "tests/golden/cases.json").open(encoding="utf-8") as file:
      data = cast(Mapping[str, object], json.load(file))
    cls.tolerance_rel = float(data["_tolerance_rel"])
    cls.cases = cast(list[Mapping[str, object]], data["cases"])

  def test_health(self) -> None:
    response = self.client.get("/api/health")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json(), {"success": True, "data": {"status": "ok"}, "error": None})

  def test_material_catalog_endpoints(self) -> None:
    boards = self.client.get("/api/db/boards")
    self.assertEqual(boards.status_code, 200)
    boards_body = boards.json()
    self.assertTrue(boards_body["success"])
    self.assertEqual(len(boards_body["data"]), 22)
    complete_boards = [board for board in boards_body["data"] if board["is_complete"]]
    incomplete_boards = [board for board in boards_body["data"] if not board["is_complete"]]
    self.assertEqual(len(complete_boards), 9)
    self.assertEqual(len(incomplete_boards), 13)

    studs = self.client.get("/api/db/studs")
    self.assertEqual(studs.status_code, 200)
    studs_body = studs.json()
    self.assertTrue(studs_body["success"])
    self.assertEqual(len(studs_body["data"]), 69)

    stud_methods = self.client.get("/api/db/stud-methods")
    self.assertEqual(stud_methods.status_code, 200)
    stud_methods_body = stud_methods.json()
    self.assertTrue(stud_methods_body["success"])
    self.assertEqual(len(stud_methods_body["data"]), 9)
    c_stud_methods = [
      item["method"] for item in stud_methods_body["data"] if item["stud_type"] == "C-STUD"
    ]
    self.assertIn("맞댐이음", c_stud_methods)

    bolts = self.client.get("/api/db/bolts")
    self.assertEqual(bolts.status_code, 200)
    bolts_body = bolts.json()
    self.assertTrue(bolts_body["success"])
    self.assertEqual(len(bolts_body["data"]), 9)

  def test_check_matches_golden_cases(self) -> None:
    for case in self.cases:
      with self.subTest(case=case["id"]):
        payload = asdict(request_from_golden_case(dict(case)))
        response = self.client.post("/api/check", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertIsNone(body["error"])

        data = cast(Mapping[str, object], body["data"])
        expected = cast(Mapping[str, object], case["expected"])
        self.assertGreater(float(data["max_height_mm"]), 0)
        self.assertEqual(float(data["max_height_increment_mm"]), 50.0)
        for key in [
          "neutral_axis_mm",
          "I_full_mm4",
          "eta",
          "I_eff_mm4",
          "Mn_kNm",
          "Mu_kNm",
          "stress_ratio",
          "deflection_mm",
          "deflection_limit_mm",
          "seismic_moment_kNm",
        ]:
          self._assert_close(key, float(data[key]), expected)
        self.assertEqual(data["deflection_verdict"], expected["deflection_verdict"])
        self.assertEqual(data["stress_verdict"], expected["stress_verdict"])

  def test_check_accepts_legacy_bolt_fracture_strength_field(self) -> None:
    payload = asdict(request_from_golden_case(dict(self.cases[0])))
    bolt = cast(dict[str, object], payload["bolt"])
    bolt["fracture_strength"] = bolt.pop("yield_strength")

    response = self.client.post("/api/check", json=payload)
    self.assertEqual(response.status_code, 200)
    body = response.json()
    self.assertTrue(body["success"])
    self.assertIsNone(body["error"])

  def test_check_calculates_fa_from_site_class(self) -> None:
    payload = asdict(request_from_golden_case(dict(self.cases[0])))
    seismic = cast(dict[str, object], payload["seismic"])
    seismic.pop("Fa")
    seismic["site_class"] = "S5"

    response = self.client.post("/api/check", json=payload)
    self.assertEqual(response.status_code, 200)
    body = response.json()
    self.assertTrue(body["success"])
    intermediate = cast(Mapping[str, object], body["data"]["intermediate"])
    self.assertAlmostEqual(float(intermediate["Fa"]), 1.3)

  def test_check_applies_s5_unknown_bedrock_depth_factor_to_fa(self) -> None:
    payload = asdict(request_from_golden_case(dict(self.cases[0])))
    seismic = cast(dict[str, object], payload["seismic"])
    seismic.pop("Fa")
    seismic["site_class"] = "S5"
    seismic["s5_bedrock_depth_unknown"] = True

    response = self.client.post("/api/check", json=payload)
    self.assertEqual(response.status_code, 200)
    body = response.json()
    self.assertTrue(body["success"])
    intermediate = cast(Mapping[str, object], body["data"]["intermediate"])
    self.assertAlmostEqual(float(intermediate["Fa"]), 1.43)

  def test_unknown_board_returns_error_envelope(self) -> None:
    payload = asdict(request_from_golden_case(dict(self.cases[0])))
    rear_boards = cast(list[dict[str, object]], payload["rear_boards"])
    rear_boards[0]["kind"] = "미등록"

    response = self.client.post("/api/check", json=payload)
    self.assertEqual(response.status_code, 400)
    body = response.json()
    self.assertFalse(body["success"])
    self.assertIsNone(body["data"])
    self.assertEqual(body["error"]["code"], "LOOKUP_ERROR")

  def test_invalid_payload_returns_error_envelope(self) -> None:
    payload = asdict(request_from_golden_case(dict(self.cases[0])))
    payload["spacing_mm"] = -1

    response = self.client.post("/api/check", json=payload)
    self.assertEqual(response.status_code, 422)
    body = response.json()
    self.assertFalse(body["success"])
    self.assertIsNone(body["data"])
    self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")

  def test_check_with_sqlite_repository(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      db_path = Path(temp_dir) / "materials.sqlite3"
      initialize_sqlite_from_seed(db_path, ROOT / "data/seed")
      client = TestClient(create_app(SqliteRepository(db_path)))
      payload = asdict(request_from_golden_case(dict(self.cases[0])))

      response = client.post("/api/check", json=payload)
      self.assertEqual(response.status_code, 200)
      body = response.json()
      self.assertTrue(body["success"])
      self.assertEqual(body["data"]["stress_verdict"], "O.K")
      self.assertEqual(body["data"]["deflection_verdict"], "O.K")

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
