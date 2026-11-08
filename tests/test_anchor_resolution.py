"""런너 고정 앵커 제품 허용내력 조회(backend/engine/anchor.py)·Repository 테스트."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Mapping, Sequence, cast

from backend.engine.anchor import (
  ANCHOR_CUSTOM_ID,
  AnchorLookupError,
  concrete_strength_options,
  embedment_options,
  is_custom_anchor,
  resolve_anchor_capacity,
  resolve_request_anchor,
)
from backend.engine.calculator import request_from_golden_case
from backend.engine.repository import (
  SCHEMA_VERSION,
  JsonSeedRepository,
  RepositoryLookupError,
  SqliteRepository,
  initialize_sqlite_from_seed,
)


ROOT = Path(__file__).resolve().parents[1]
SEISMIC = "seismic"
NON_SEISMIC = "non_seismic"


class AnchorResolutionTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.repo = JsonSeedRepository(ROOT / "data/seed")
    cls.cap = cls.repo.get_anchor_seismic_cap()

  def resolve(self, anchor_id: str, embedment: float | None, fc: float | None, case: str = SEISMIC, apply_cap: bool = True):
    return resolve_anchor_capacity(self.repo.get_anchor_product(anchor_id), embedment, fc, case, apply_cap, self.cap.cap_N)

  def test_seismic_cap_from_seed(self) -> None:
    self.assertEqual(self.cap.cap_N, 400.0)
    self.assertIn("400 N", self.cap.note)

  def test_rec_product_uses_embedment_floor(self) -> None:
    self.assertEqual(self.resolve("hilti_x_u", 22, None).allowable_shear_N, 300.0)
    self.assertEqual(self.resolve("hilti_x_u", 22, None).anchor_capacity_kN, 0.3)
    self.assertEqual(self.resolve("hilti_x_u", 27, None).allowable_shear_N, 400.0)
    # 20 mm는 표에 없음 → 이하 최대 행(18 mm) 200 N
    resolution = self.resolve("hilti_x_u", 20, None)
    self.assertEqual(resolution.allowable_shear_N, 200.0)
    self.assertEqual(resolution.matched_row.embedment_mm, 18.0)
    self.assertFalse(resolution.cap_applied)

  def test_rec_product_below_minimum_is_error(self) -> None:
    with self.assertRaises(AnchorLookupError):
      self.resolve("hilti_x_u", 10, None)

  def test_asd_product_exact_match_and_seismic_cap(self) -> None:
    capped = self.resolve("hilti_x_u_esr", 25, 27.6)
    self.assertEqual(capped.table_shear_N, 1001.0)
    self.assertEqual(capped.allowable_shear_N, 400.0)
    self.assertEqual(capped.anchor_capacity_kN, 0.4)
    self.assertTrue(capped.cap_applied)
    self.assertEqual(capped.allowable_tension_kN, 0.756)

    uncapped = self.resolve("hilti_x_u_esr", 25, 27.6, apply_cap=False)
    self.assertEqual(uncapped.allowable_shear_N, 1001.0)
    self.assertEqual(uncapped.anchor_capacity_kN, 1.001)
    self.assertFalse(uncapped.cap_applied)

  def test_non_seismic_does_not_apply_cap(self) -> None:
    resolution = self.resolve("hilti_x_u_esr", 25, 27.6, case=NON_SEISMIC)
    self.assertEqual(resolution.allowable_shear_N, 1001.0)
    self.assertFalse(resolution.cap_applied)

  def test_asd_product_requires_exact_row(self) -> None:
    self.assertEqual(self.resolve("simpson_titen_14", 38, 27.6, apply_cap=False).allowable_shear_N, 1779.0)
    with self.assertRaises(AnchorLookupError):
      self.resolve("simpson_titen_14", 30, 27.6)  # 보간 금지
    with self.assertRaises(AnchorLookupError):
      self.resolve("simpson_titen_14", 38, 20.7)  # 해당 fc 행 없음
    with self.assertRaises(AnchorLookupError):
      self.resolve("simpson_titen_14", 38, None)  # fc 미지정

  def test_custom_is_not_resolved(self) -> None:
    self.assertTrue(is_custom_anchor(None))
    self.assertTrue(is_custom_anchor(ANCHOR_CUSTOM_ID))
    self.assertFalse(is_custom_anchor("hilti_x_u"))
    with self.assertRaises(AnchorLookupError):
      self.resolve(ANCHOR_CUSTOM_ID, 22, None)

  def test_options_helpers(self) -> None:
    esr = self.repo.get_anchor_product("hilti_x_u_esr")
    self.assertEqual(embedment_options(esr), (19.0, 25.0, 32.0, 38.0))
    self.assertEqual(concrete_strength_options(esr, 38.0), (17.2, 27.6))
    rec = self.repo.get_anchor_product("hilti_x_u")
    self.assertEqual(concrete_strength_options(rec, 22.0), ())

  def test_summary_and_condition_text(self) -> None:
    resolution = self.resolve("hilti_x_u", 22, None)
    self.assertEqual(resolution.condition_text, "hET 22 mm / f'c 강도 무관")
    self.assertTrue(resolution.summary.startswith("Hilti X-U P8 / hET 22 mm"))
    self.assertIn(resolution.basis_label, resolution.summary)

  def test_resolve_request_anchor_overrides_capacity(self) -> None:
    base = request_from_golden_case(dict(_first_golden_case()))
    custom_request, custom_resolution = resolve_request_anchor(base, self.repo)
    self.assertIs(custom_request, base)
    self.assertIsNone(custom_resolution)

    product_request = replace(base, anchor_capacity_kN=0.4, anchor_product_id="hilti_x_u", anchor_embedment_mm=22.0)
    resolved, resolution = resolve_request_anchor(product_request, self.repo)
    self.assertIsNotNone(resolution)
    self.assertEqual(resolved.anchor_capacity_kN, 0.3)
    self.assertEqual(resolved.anchor_product_id, "hilti_x_u")
    with self.assertRaises(RepositoryLookupError):
      resolve_request_anchor(replace(base, anchor_product_id="no_such_anchor", anchor_embedment_mm=22.0), self.repo)


def _first_golden_case() -> Mapping[str, object]:
  with (ROOT / "tests/golden/cases.json").open(encoding="utf-8") as file:
    data = cast(Mapping[str, object], json.load(file))
  return cast(Sequence[Mapping[str, object]], data["cases"])[0]


class AnchorRepositoryTest(unittest.TestCase):
  def setUp(self) -> None:
    self.temp_dir = tempfile.TemporaryDirectory()
    self.db_path = Path(self.temp_dir.name) / "materials.sqlite3"
    initialize_sqlite_from_seed(self.db_path, ROOT / "data/seed")
    self.json_repo = JsonSeedRepository(ROOT / "data/seed")
    self.sqlite_repo = SqliteRepository(self.db_path)

  def tearDown(self) -> None:
    self.temp_dir.cleanup()

  def test_schema_version_is_9(self) -> None:
    self.assertEqual(SCHEMA_VERSION, "9")
    with closing(sqlite3.connect(self.db_path)) as connection:
      version = connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0]
      self.assertEqual(version, "9")
      self.assertEqual(connection.execute("SELECT COUNT(*) FROM anchor_product").fetchone()[0], 13)
      self.assertEqual(connection.execute("SELECT COUNT(*) FROM anchor_load_row").fetchone()[0], 74)

  def test_sqlite_matches_json(self) -> None:
    self.assertEqual(self.sqlite_repo.list_anchor_products(), self.json_repo.list_anchor_products())
    self.assertEqual(self.sqlite_repo.get_anchor_product("hilti_x_u"), self.json_repo.get_anchor_product("hilti_x_u"))
    self.assertEqual(self.sqlite_repo.get_anchor_seismic_cap(), self.json_repo.get_anchor_seismic_cap())
    default = [p for p in self.sqlite_repo.list_anchor_products() if p.is_default]
    self.assertEqual([p.anchor_id for p in default], ["hilti_x_u"])

  def test_unknown_anchor_is_lookup_error(self) -> None:
    with self.assertRaises(RepositoryLookupError):
      self.json_repo.get_anchor_product("no_such_anchor")
    with self.assertRaises(RepositoryLookupError):
      self.sqlite_repo.get_anchor_product("no_such_anchor")

  def test_schema_8_db_is_migrated_with_seed_dir(self) -> None:
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.execute("DROP TABLE anchor_load_row")
      connection.execute("DROP TABLE anchor_product")
      connection.execute("DELETE FROM metadata WHERE key LIKE 'anchor_%'")
      connection.execute("UPDATE metadata SET value = '8' WHERE key = 'schema_version'")
      connection.commit()
    migrated = SqliteRepository(self.db_path, ROOT / "data/seed")
    self.assertEqual(len(migrated.list_anchor_products()), 13)
    self.assertEqual(migrated.get_anchor_seismic_cap().cap_N, 400.0)
    with closing(sqlite3.connect(self.db_path)) as connection:
      self.assertEqual(connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0], "9")

  def test_schema_8_db_without_seed_dir_rolls_back(self) -> None:
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.execute("DROP TABLE anchor_load_row")
      connection.execute("DROP TABLE anchor_product")
      connection.execute("UPDATE metadata SET value = '8' WHERE key = 'schema_version'")
      connection.commit()
    with self.assertRaises(RepositoryLookupError):
      SqliteRepository(self.db_path)
    with closing(sqlite3.connect(self.db_path)) as connection:
      self.assertEqual(connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0], "8")


if __name__ == "__main__":
  unittest.main()
