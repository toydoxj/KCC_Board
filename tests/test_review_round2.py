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


# ---------------------------------------------------------------- A-1·F-2 시험 구성 대조
SPECIMEN_NO = {specimen_id: int(specimen_id.split("_")[1]) for specimen_id in REQUESTS}


@pytest.mark.parametrize("specimen_id", sorted(REQUESTS))
def test_specimen_configuration_matches_its_specimen(specimen_id: str) -> None:
  result = calculate_wall_check(REQUESTS[specimen_id], REPO)
  assert result.intermediate["tested_configuration_match"] == 1.0
  assert result.intermediate["matched_specimen_no"] == SPECIMEN_NO[specimen_id]
  assert result.tested_configuration_mismatch_fields == ()


@pytest.mark.parametrize("design_case", ["seismic", "non_seismic"])
def test_board_thickness_change_is_mismatch(design_case: str) -> None:
  boards = tuple(replace(board, thickness=15.0) for board in BASE.front_boards)
  result = calculate_wall_check(replace(BASE, front_boards=boards, design_case=design_case), REPO)
  assert result.intermediate["tested_configuration_match"] == 0.0
  assert result.intermediate["matched_specimen_no"] == 0.0
  assert result.intermediate["closest_specimen_no"] == 4.0
  assert "board_thickness" in result.tested_configuration_mismatch_fields
  assert "board_kind" not in result.tested_configuration_mismatch_fields


def test_spacing_and_layer_changes_are_listed() -> None:
  result = calculate_wall_check(replace(BASE, spacing_mm=300.0, rear_boards=BASE.rear_boards[:1]), REPO)
  assert set(result.tested_configuration_mismatch_fields) == {"spacing", "board_layers"}


def test_one_side_specimen_matches_basic_without_rear_boards() -> None:
  result = calculate_wall_check(replace(BASE, rear_boards=()), REPO)
  assert result.intermediate["matched_specimen_no"] == 2.0


def test_seed_specimens_follow_golden_specimen_inputs() -> None:
  # 시험 구성 정의(stud_method.json)와 R 보정 시편 입력(requested_shape_cases.json)이 어긋나지 않아야 한다
  specimens = {specimen.specimen_id: specimen for specimen in REPO.list_specimen_configurations()}
  assert set(specimens) == set(REQUESTS)
  for specimen_id, request in REQUESTS.items():
    specimen = specimens[specimen_id]
    assert specimen.stud_type == request.stud.stud_type
    assert specimen.stud_spec == request.stud.spec
    assert specimen.spacing_mm == request.spacing_mm
    assert specimen.front_boards == tuple((b.kind, b.thickness) for b in request.front_boards)
    assert specimen.rear_boards == tuple((b.kind, b.thickness) for b in request.rear_boards)
    assert specimen.test_height_mm == 2400.0


def test_api_returns_mismatch_fields() -> None:
  client = TestClient(create_app(REPO))
  payload = asdict(replace(BASE, spacing_mm=300.0))
  body = client.post("/api/check", json=payload).json()
  assert body["success"] is True
  assert body["data"]["tested_configuration_mismatch_fields"] == ["spacing"]
  assert body["data"]["intermediate"]["closest_specimen_no"] == 4.0


def test_sqlite_repository_lists_specimens_and_migrates(tmp_path: Path) -> None:
  import sqlite3

  from backend.engine.repository import SqliteRepository, initialize_sqlite_from_seed

  db = tmp_path / "materials.sqlite3"
  initialize_sqlite_from_seed(db, ROOT / "data/seed")
  assert len(SqliteRepository(db, ROOT / "data/seed").list_specimen_configurations()) == 11
  # schema 7 DB(시편 테이블 없음) → seed 경로가 있으면 이관 시 채운다
  with sqlite3.connect(db) as connection:
    connection.execute("DROP TABLE specimen_configuration")
  migrated = SqliteRepository(db, ROOT / "data/seed").list_specimen_configurations()
  assert migrated == REPO.list_specimen_configurations()


def test_sqlite_old_db_without_seed_dir_fails_explicitly(tmp_path: Path) -> None:
  import sqlite3

  from backend.engine.repository import RepositoryLookupError, SqliteRepository, initialize_sqlite_from_seed

  db = tmp_path / "materials.sqlite3"
  initialize_sqlite_from_seed(db, ROOT / "data/seed")
  with sqlite3.connect(db) as connection:
    connection.execute("DROP TABLE specimen_configuration")
    connection.execute("UPDATE metadata SET value = '7' WHERE key = 'schema_version'")
  with pytest.raises(RepositoryLookupError, match="시험 시편 구성"):
    SqliteRepository(db)
  with sqlite3.connect(db) as connection:
    # 롤백: schema 버전이 올라가지 않아야 한다
    assert connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0] == "7"


@pytest.mark.parametrize("method", [None, "", " 기본 "])
def test_c_stud_missing_method_means_basic(method: str | None) -> None:
  request = replace(BASE, stud=replace(BASE.stud, method=method))
  assert calculate_wall_check(request, REPO).intermediate["matched_specimen_no"] == 4.0


def test_central_joint_alias_matches_specimen_01() -> None:
  base = REQUESTS["requested_01_c_stud_central_joint"]
  request = replace(base, stud=replace(base.stud, method="중앙부연결"))
  assert calculate_wall_check(request, REPO).intermediate["matched_specimen_no"] == 1.0


# ---------------------------------------------------------------- D-2 설치높이비 z/h
def _seismic(request, z_over_h: float):
  return replace(request, design_case="seismic", seismic=replace(request.seismic, z_over_h=z_over_h))


def test_default_z_over_h_keeps_legacy_coefficient() -> None:
  result = calculate_wall_check(_seismic(BASE, 1.0), REPO)
  assert result.intermediate["seismic_fp_coefficient"] == pytest.approx(0.48)
  assert result.intermediate["seismic_fp_bound_applied"] == 0.0
  assert result.intermediate["seismic_z_over_h"] == 1.0


@pytest.mark.parametrize(
  ("z_over_h", "coefficient", "bound"),
  [(1.0, 0.48, 0.0), (0.5, 0.32, 0.0), (0.4375, 0.30, 0.0), (0.25, 0.30, 1.0), (0.0, 0.30, 1.0)],
)
def test_fp_coefficient_and_lower_bound(z_over_h: float, coefficient: float, bound: float) -> None:
  result = calculate_wall_check(_seismic(BASE, z_over_h), REPO)
  assert result.intermediate["seismic_fp_coefficient"] == pytest.approx(coefficient)
  assert result.intermediate["seismic_fp_bound_applied"] == bound


@pytest.mark.parametrize("z_over_h", [1.0, 0.5, 0.0])
def test_screw_tension_and_moment_paths_use_same_coefficient(z_over_h: float) -> None:
  result = calculate_wall_check(_seismic(BASE, z_over_h), REPO)
  inter = result.intermediate
  assert inter["screw_tension_fp_coefficient"] == inter["seismic_fp_coefficient"]
  sds_ip_w = inter["Sds"] * BASE.seismic.Ip * inter["seismic_weight_kN"]
  assert inter["Fp_kN"] == pytest.approx(inter["seismic_fp_coefficient"] * sds_ip_w)


def test_lower_z_over_h_reduces_fp_proportionally() -> None:
  top = calculate_wall_check(_seismic(BASE, 1.0), REPO).intermediate["Fp_kN"]
  middle = calculate_wall_check(_seismic(BASE, 0.5), REPO).intermediate["Fp_kN"]
  assert middle == pytest.approx(top * 0.32 / 0.48)


@pytest.mark.parametrize("z_over_h", [-0.1, 1.01])
def test_z_over_h_out_of_range_is_rejected(z_over_h: float) -> None:
  with pytest.raises(ValueError, match="z/h는 0.0~1.0"):
    calculate_wall_check(_seismic(BASE, z_over_h), REPO)


def test_api_accepts_z_over_h() -> None:
  client = TestClient(create_app(REPO))
  payload = asdict(_seismic(BASE, 0.5))
  body = client.post("/api/check", json=payload).json()
  assert body["success"] is True
  assert body["data"]["intermediate"]["seismic_fp_coefficient"] == pytest.approx(0.32)



def test_default_coefficient_is_bitwise_legacy_value() -> None:
  # 경계 판정(앵커 허용간격 등)이 바뀌지 않도록 z/h = 1.0 계수는 0.48과 정확히 같아야 한다
  result = calculate_wall_check(_seismic(BASE, 1.0), REPO)
  assert result.intermediate["seismic_fp_coefficient"] == 0.48
  assert result.intermediate["screw_tension_fp_coefficient"] == 0.48
