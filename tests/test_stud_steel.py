"""스터드 강재 Fy·Fu 자재 DB 분리(심사의견 B-8) 테스트."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from typing import Any, Mapping, cast

from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.engine.calculator import _calculate_wall_check_once, request_from_golden_case
from backend.engine.repository import (
  SCHEMA_VERSION,
  JsonSeedRepository,
  RepositoryLookupError,
  SqliteRepository,
  initialize_sqlite_from_seed,
)


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data/seed"
LEGACY_GRADE = "legacy_stud_295_400"


def _golden_request():
  with (ROOT / "tests/golden/cases.json").open(encoding="utf-8") as file:
    data = cast(Mapping[str, object], json.load(file))
  return request_from_golden_case(dict(cast(list[Mapping[str, object]], data["cases"])[0]))


class _TempSeed:
  """data/seed 복사본을 만들어 JSON을 수정한다."""

  def __init__(self) -> None:
    self._dir = tempfile.TemporaryDirectory()
    self.path = Path(self._dir.name) / "seed"
    shutil.copytree(SEED, self.path)

  def edit(self, filename: str, change) -> None:
    file = self.path / filename
    data = cast(dict[str, Any], json.loads(file.read_text(encoding="utf-8")))
    change(data)
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

  def cleanup(self) -> None:
    self._dir.cleanup()


class StudSteelSeedTest(unittest.TestCase):
  def setUp(self) -> None:
    self.temp = _TempSeed()
    self.addCleanup(self.temp.cleanup)

  def test_default_steel_keeps_legacy_values_and_is_unconfirmed(self) -> None:
    steels = JsonSeedRepository(SEED).list_stud_steels()
    self.assertEqual(len(steels), 1)
    steel = steels[0]
    self.assertEqual((steel.steel_grade, steel.Fy, steel.Fu), (LEGACY_GRADE, 295.0, 400.0))
    self.assertEqual(steel.status, "미확정")
    self.assertTrue(steel.is_default)

  def test_every_stud_links_default_steel_with_matching_se_basis(self) -> None:
    studs = JsonSeedRepository(SEED).list_studs()
    self.assertEqual(len(studs), 69)
    for stud in studs:
      with self.subTest(stud=f"{stud.group} {stud.name}"):
        self.assertIsNotNone(stud.steel)
        self.assertEqual(stud.steel.steel_grade, LEGACY_GRADE)
        self.assertEqual(stud.Se_basis_Fy_MPa, 295.0)

  def _add_second_steel(self) -> None:
    def add(data: dict[str, Any]) -> None:
      data["items"].append({**data["items"][0], "steel_grade": "test_295_500", "Fu": 500, "is_default": False})

    self.temp.edit("stud_steel.json", add)

  def test_explicit_non_default_steel_is_used(self) -> None:
    self._add_second_steel()
    self.temp.edit("stud_section.json", lambda d: d["items"][0].update(steel_grade="test_295_500"))
    studs = JsonSeedRepository(self.temp.path).list_studs()
    first = json.loads((self.temp.path / "stud_section.json").read_text(encoding="utf-8"))["items"][0]

    for stud in studs:
      expected = "test_295_500" if (stud.group, stud.name) == (first["group"], first["name"]) else LEGACY_GRADE
      self.assertEqual(stud.steel.steel_grade if stud.steel else None, expected)

  def test_sqlite_keeps_stored_reference_when_default_changes(self) -> None:
    self._add_second_steel()
    db_path = self.temp.path.parent / "materials.sqlite3"
    initialize_sqlite_from_seed(db_path, self.temp.path)
    with closing(sqlite3.connect(db_path)) as connection:
      connection.execute("UPDATE stud_steel SET is_default = (steel_grade = 'test_295_500')")
      connection.commit()

    stud = SqliteRepository(db_path).get_stud("C-STUD", "50S-45-08")
    self.assertEqual(stud.steel.steel_grade if stud.steel else None, LEGACY_GRADE)

  def test_unknown_steel_reference_is_rejected(self) -> None:
    self.temp.edit("stud_section.json", lambda d: d["items"][0].update(steel_grade="SGMH999"))
    with self.assertRaisesRegex(RepositoryLookupError, "SGMH999"):
      JsonSeedRepository(self.temp.path)

  def test_default_steel_must_be_unique(self) -> None:
    def add_second_default(data: dict[str, Any]) -> None:
      data["items"].append({**data["items"][0], "steel_grade": "second"})

    self.temp.edit("stud_steel.json", add_second_default)
    with self.assertRaisesRegex(RepositoryLookupError, "정확히 1개"):
      JsonSeedRepository(self.temp.path)

  def test_se_basis_mismatch_blocks_calculation(self) -> None:
    self.temp.edit("stud_steel.json", lambda d: d["items"][0].update(Fy=300))
    with self.assertRaisesRegex(ValueError, "Se를 재산정"):
      _calculate_wall_check_once(_golden_request(), JsonSeedRepository(self.temp.path))

  def test_db_strengths_reach_calculation(self) -> None:
    # 가상 강재 Fy 350·Fu 500(Se 기준도 350으로 맞춤) — 상수가 아니라 DB 값이 계산에 쓰이는지 확인
    def set_steel(data: dict[str, Any]) -> None:
      data["items"][0].update(Fy=350, Fu=500)

    def set_basis(data: dict[str, Any]) -> None:
      for item in data["items"]:
        item["Se_basis_Fy_MPa"] = 350

    request = _golden_request()
    base = _calculate_wall_check_once(request, JsonSeedRepository(SEED))
    self.temp.edit("stud_steel.json", set_steel)
    self.temp.edit("stud_section.json", set_basis)
    virtual = _calculate_wall_check_once(request, JsonSeedRepository(self.temp.path))

    self.assertEqual(virtual.intermediate["stud_yield_strength_MPa"], 350.0)
    self.assertEqual(virtual.intermediate["stud_tensile_strength_MPa"], 500.0)
    self.assertAlmostEqual(
      virtual.intermediate["Mn_stud_only_kNm"], base.intermediate["Mn_stud_only_kNm"] * 350.0 / 295.0
    )
    self.assertAlmostEqual(
      virtual.intermediate["screw_stud_side_shear_N"], base.intermediate["screw_stud_side_shear_N"] * 500.0 / 400.0
    )
    self.assertAlmostEqual(
      virtual.intermediate["screw_pullout_nominal_N"], base.intermediate["screw_pullout_nominal_N"] * 500.0 / 400.0
    )


class StudSteelSqliteTest(unittest.TestCase):
  def setUp(self) -> None:
    self.temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_dir.cleanup)
    self.db_path = Path(self.temp_dir.name) / "materials.sqlite3"
    initialize_sqlite_from_seed(self.db_path, SEED)

  def _metadata_version(self) -> str:
    with closing(sqlite3.connect(self.db_path)) as connection:
      return str(connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0])

  def _downgrade_to_v6(self) -> None:
    """stud_steel 테이블과 신규 열이 없는 schema 6 DB를 재현한다."""
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.executescript(
        """
        DROP TABLE stud_steel;
        CREATE TABLE old_stud AS
          SELECT group_name, name, H, B, t, A, cx, cy, Ix, Iy, Sx, Sy, rx, ry, section_class, Se FROM stud_section;
        DROP TABLE stud_section;
        ALTER TABLE old_stud RENAME TO stud_section;
        UPDATE metadata SET value = '6' WHERE key = 'schema_version';
        """
      )

  def test_sqlite_matches_json_for_all_studs(self) -> None:
    json_studs = JsonSeedRepository(SEED).list_studs()
    sqlite_repository = SqliteRepository(self.db_path)
    self.assertEqual(sqlite_repository.list_studs(), json_studs)
    for stud in json_studs:
      with self.subTest(stud=f"{stud.group} {stud.name}"):
        self.assertEqual(sqlite_repository.get_stud(stud.group, stud.name), stud)
    self.assertEqual(sqlite_repository.list_stud_steels(), JsonSeedRepository(SEED).list_stud_steels())
    self.assertEqual(self._metadata_version(), SCHEMA_VERSION)

  def test_v6_database_is_migrated_and_requires_init_db_for_calculation(self) -> None:
    self._downgrade_to_v6()
    repository = SqliteRepository(self.db_path, SEED)

    self.assertEqual(self._metadata_version(), SCHEMA_VERSION)
    stud = repository.get_stud("C-STUD", "50S-45-08")
    self.assertEqual(stud.steel.steel_grade if stud.steel else None, LEGACY_GRADE)
    # 구 DB의 Se는 산정 기준 근거가 없으므로 인증하지 않는다
    self.assertIsNone(stud.Se_basis_Fy_MPa)
    with self.assertRaisesRegex(ValueError, "init_db"):
      _calculate_wall_check_once(_golden_request(), repository)

    # 재실행해도 값이 유지된다
    again = SqliteRepository(self.db_path, SEED)
    self.assertEqual(again.list_stud_steels(), repository.list_stud_steels())

  def test_v6_migration_without_seed_dir_fails_and_rolls_back(self) -> None:
    self._downgrade_to_v6()
    with self.assertRaisesRegex(RepositoryLookupError, "init_db"):
      SqliteRepository(self.db_path)
    self.assertEqual(self._metadata_version(), "6")
    with closing(sqlite3.connect(self.db_path)) as connection:
      columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(stud_section)").fetchall()}
    self.assertNotIn("steel_grade", columns)

  def test_no_reset_reinitialization_adds_new_columns(self) -> None:
    self._downgrade_to_v6()
    initialize_sqlite_from_seed(self.db_path, SEED, reset=False)
    repository = SqliteRepository(self.db_path)

    result = _calculate_wall_check_once(_golden_request(), repository)
    expected = _calculate_wall_check_once(_golden_request(), JsonSeedRepository(SEED))
    self.assertEqual(result.Mn_kNm, expected.Mn_kNm)

  def test_api_studs_expose_steel_fields(self) -> None:
    response = TestClient(create_app(JsonSeedRepository(SEED))).get("/api/db/studs")
    self.assertEqual(response.status_code, 200)
    stud = response.json()["data"][0]
    self.assertEqual(stud["steel_grade"], LEGACY_GRADE)
    self.assertEqual((stud["Fy"], stud["Fu"], stud["Se_basis_Fy_MPa"]), (295.0, 400.0, 295.0))
    self.assertEqual(stud["steel_status"], "미확정")


if __name__ == "__main__":
  unittest.main()
