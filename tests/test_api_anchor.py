"""런너 고정 앵커 제품 API 테스트 — /api/db/anchor-products, /api/check 제품 조회·덮어쓰기."""

from __future__ import annotations

import json
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, cast

from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.engine.calculator import request_from_golden_case
from backend.engine.repository import JsonSeedRepository


ROOT = Path(__file__).resolve().parents[1]


class ApiAnchorTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.client = TestClient(create_app(JsonSeedRepository(ROOT / "data/seed")))
    with (ROOT / "tests/golden/cases.json").open(encoding="utf-8") as file:
      data = cast(Mapping[str, object], json.load(file))
    cls.base_payload = asdict(request_from_golden_case(dict(cast(list[Mapping[str, object]], data["cases"])[0])))

  def _payload(self, **overrides: object) -> dict[str, object]:
    payload = dict(self.base_payload)
    payload.update(overrides)
    return payload

  def test_anchor_products_endpoint(self) -> None:
    response = self.client.get("/api/db/anchor-products")
    self.assertEqual(response.status_code, 200)
    body = response.json()
    self.assertTrue(body["success"])
    self.assertEqual(body["data"]["seismic_shear_cap_N"], 400.0)
    self.assertIn("400 N", body["data"]["seismic_shear_cap_note"])
    self.assertEqual(body["data"]["seismic_shear_cap_families"], ["dx", "gx"])
    items = body["data"]["items"]
    self.assertEqual(len(items), 13)
    default = [item for item in items if item["is_default"]]
    self.assertEqual([item["anchor_id"] for item in default], ["hilti_x_u"])
    hilti = default[0]
    # 2026-11-09 사용자 확정: 기본 매입깊이 27 mm → 400 N(v0.8.0 기본값 0.4 kN과 동일)
    self.assertEqual(hilti["default_embedment_mm"], 27.0)
    self.assertEqual(len(hilti["table"]), 4)
    self.assertIsNone(hilti["table"][0]["concrete_fc_MPa"])
    custom = [item for item in items if item["anchor_id"] == "custom"]
    self.assertEqual(len(custom), 1)
    self.assertEqual(custom[0]["table"], [])

  def test_check_without_product_keeps_client_capacity(self) -> None:
    response = self.client.post("/api/check", json=self._payload(anchor_capacity_kN=0.4))
    self.assertEqual(response.status_code, 200, response.text)
    data = response.json()["data"]
    self.assertEqual(data["intermediate"]["anchor_capacity_kN"], 0.4)
    self.assertFalse(data["anchor_capacity_overridden"])
    self.assertIsNone(data["anchor_product_summary"])
    self.assertNotIn("anchor_capacity_resolved_N", data["intermediate"])

  def test_check_with_product_overrides_capacity(self) -> None:
    payload = self._payload(
      design_case="seismic",
      anchor_capacity_kN=0.4,
      anchor_product_id="hilti_x_u",
      anchor_embedment_mm=22.0,
      anchor_concrete_fc_MPa=None,
    )
    response = self.client.post("/api/check", json=payload)
    self.assertEqual(response.status_code, 200, response.text)
    data = response.json()["data"]
    intermediate = data["intermediate"]
    self.assertEqual(intermediate["anchor_capacity_kN"], 0.3)
    self.assertEqual(intermediate["anchor_capacity_resolved_N"], 300.0)
    self.assertEqual(intermediate["anchor_seismic_cap_applied"], 0.0)
    self.assertEqual(intermediate["anchor_allowable_tension_N"], 300.0)
    self.assertTrue(data["anchor_capacity_overridden"])
    self.assertTrue(data["anchor_product_summary"].startswith("Hilti X-U P8 / hET 22 mm"))

    same_value = self.client.post("/api/check", json={**payload, "anchor_capacity_kN": 0.3}).json()["data"]
    self.assertFalse(same_value["anchor_capacity_overridden"])
    self.assertEqual(same_value["intermediate"]["anchor_capacity_kN"], 0.3)

  def test_check_with_asd_product_applies_seismic_cap(self) -> None:
    payload = self._payload(
      design_case="seismic",
      anchor_product_id="hilti_x_u_esr",
      anchor_embedment_mm=25.0,
      anchor_concrete_fc_MPa=27.6,
    )
    capped = self.client.post("/api/check", json=payload).json()["data"]
    self.assertEqual(capped["intermediate"]["anchor_capacity_kN"], 0.4)
    self.assertEqual(capped["intermediate"]["anchor_capacity_resolved_N"], 400.0)
    self.assertEqual(capped["intermediate"]["anchor_seismic_cap_applied"], 1.0)
    self.assertEqual(capped["intermediate"]["anchor_seismic_cap_eligible"], 1.0)
    self.assertEqual(capped["intermediate"]["anchor_table_shear_N"], 1001.0)
    self.assertIn("(내진 상한 400 N 적용)", capped["anchor_product_summary"])

    uncapped = self.client.post("/api/check", json={**payload, "anchor_apply_seismic_cap": False}).json()["data"]
    self.assertEqual(uncapped["intermediate"]["anchor_capacity_kN"], 1.001)
    self.assertEqual(uncapped["intermediate"]["anchor_seismic_cap_applied"], 0.0)

  def test_check_with_screw_product_is_not_capped_in_seismic(self) -> None:
    # 결정 2: 콘크리트 스크류(screw)는 상한 비적용 — 표 값 1,779 N 그대로, 별도 확인 문구
    payload = self._payload(
      design_case="seismic",
      anchor_product_id="simpson_titen_14",
      anchor_embedment_mm=38.0,
      anchor_concrete_fc_MPa=27.6,
      anchor_apply_seismic_cap=True,
    )
    data = self.client.post("/api/check", json=payload).json()["data"]
    self.assertEqual(data["intermediate"]["anchor_capacity_kN"], 1.779)
    self.assertEqual(data["intermediate"]["anchor_capacity_resolved_N"], 1779.0)
    self.assertEqual(data["intermediate"]["anchor_seismic_cap_applied"], 0.0)
    self.assertEqual(data["intermediate"]["anchor_seismic_cap_eligible"], 0.0)
    self.assertIn("내진 상한 비적용", data["anchor_product_summary"])

  def test_check_with_gx_product_at_cap_value_is_eligible_but_not_applied(self) -> None:
    # 표 값 400 = cap: 적용 대상(gx)이지만 초과가 아니므로 cap_applied 0
    payload = self._payload(
      design_case="seismic",
      anchor_product_id="hilti_gx3_esr",
      anchor_embedment_mm=19.0,
      anchor_concrete_fc_MPa=17.2,
    )
    data = self.client.post("/api/check", json=payload).json()["data"]
    self.assertEqual(data["intermediate"]["anchor_capacity_kN"], 0.4)
    self.assertEqual(data["intermediate"]["anchor_seismic_cap_applied"], 0.0)
    self.assertEqual(data["intermediate"]["anchor_seismic_cap_eligible"], 1.0)
    self.assertNotIn("내진 상한", data["anchor_product_summary"])

  def test_check_with_infinite_embedment_is_rejected(self) -> None:
    payload = self._payload(design_case="seismic", anchor_product_id="hilti_x_u", anchor_embedment_mm="Infinity")
    response = self.client.post("/api/check", json=payload)
    self.assertEqual(response.status_code, 422)

  def test_check_with_unknown_product_returns_lookup_error(self) -> None:
    response = self.client.post(
      "/api/check",
      json=self._payload(anchor_product_id="no_such_anchor", anchor_embedment_mm=22.0),
    )
    self.assertEqual(response.status_code, 400)
    self.assertEqual(response.json()["error"]["code"], "LOOKUP_ERROR")

  def test_check_with_missing_table_row_returns_calculation_error(self) -> None:
    response = self.client.post(
      "/api/check",
      json=self._payload(anchor_product_id="simpson_titen_14", anchor_embedment_mm=30.0, anchor_concrete_fc_MPa=27.6),
    )
    self.assertEqual(response.status_code, 400)
    self.assertEqual(response.json()["error"]["code"], "CALCULATION_ERROR")
    self.assertIn("허용하중 표에 없습니다", response.json()["error"]["message"])


if __name__ == "__main__":
  unittest.main()
