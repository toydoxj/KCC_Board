"""2차 심사의견 반영 검증 (fix/review-round2)."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.engine.calculator import calculate_wall_check
from backend.engine.repository import JsonSeedRepository
from backend.tools.r_calibration import specimen_requests


ROOT = Path(__file__).resolve().parents[1]
REPO = JsonSeedRepository(ROOT / "data/seed")
REQUESTS = specimen_requests()
BASE = REQUESTS["requested_04_c_stud_basic"]


# ---------------------------------------------------------------- F-1 스터드 간격 범위
@pytest.mark.parametrize("spacing_mm", [100.0, 149.0, 601.0, 650.0])
def test_stud_spacing_out_of_range_is_rejected(spacing_mm: float) -> None:
  with pytest.raises(ValueError, match="스터드 간격은 150~600 mm 범위여야 합니다"):
    calculate_wall_check(replace(BASE, spacing_mm=spacing_mm), REPO)


@pytest.mark.parametrize("spacing_mm", [150.0, 600.0])
def test_stud_spacing_range_limits_are_accepted(spacing_mm: float) -> None:
  calculate_wall_check(replace(BASE, spacing_mm=spacing_mm), REPO)


@pytest.mark.parametrize("spacing_mm", [100.0, 650.0])
def test_stud_spacing_out_of_range_api_error_envelope(spacing_mm: float) -> None:
  client = TestClient(create_app(REPO))
  payload = asdict(replace(BASE, spacing_mm=spacing_mm))
  response = client.post("/api/check", json=payload)
  assert response.status_code == 400
  body = response.json()
  assert body["success"] is False
  assert body["error"]["code"] == "CALCULATION_ERROR"
  assert "150~600 mm" in body["error"]["message"]
