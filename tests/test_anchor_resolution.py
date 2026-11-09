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
  SUMMARY_CAP_APPLIED_SUFFIX,
  SUMMARY_CAP_NOT_ELIGIBLE_SUFFIX,
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
    return resolve_anchor_capacity(
      self.repo.get_anchor_product(anchor_id), embedment, fc, case, apply_cap, self.cap.cap_N, self.cap.families
    )

  def test_seismic_cap_from_seed(self) -> None:
    self.assertEqual(self.cap.cap_N, 400.0)
    self.assertIn("400 N", self.cap.note)
    # 결정 2(2026-11-09): 상한은 타정못·가스핀(ICC-ES PAF 평가서 §4.1 Item 2) 전용
    self.assertEqual(self.cap.families, ("dx", "gx"))
    self.assertIn("ACI 318", self.cap.note)

  def test_screw_family_is_not_capped_in_seismic(self) -> None:
    # 콘크리트 스크류(screw)는 상한 적용 대상이 아니다 — 내진·상한 체크여도 표 값 그대로, 별도 확인 문구
    titen = self.resolve("simpson_titen_14", 38, 27.6)
    self.assertEqual(titen.table_shear_N, 1779.0)
    self.assertEqual(titen.allowable_shear_N, 1779.0)
    self.assertEqual(titen.anchor_capacity_kN, 1.779)
    self.assertFalse(titen.cap_applied)
    self.assertFalse(titen.cap_eligible)
    self.assertTrue(titen.summary.endswith(SUMMARY_CAP_NOT_ELIGIBLE_SUFFIX), titen.summary)
    # 비내진이면 비적용 문구도 붙지 않는다
    titen_static = self.resolve("simpson_titen_14", 38, 27.6, case=NON_SEISMIC)
    self.assertFalse(titen_static.cap_eligible)
    self.assertNotIn("내진 상한", titen_static.summary)

  def test_dx_gx_families_are_cap_eligible(self) -> None:
    capped = self.resolve("hilti_x_u_esr", 25, 27.6)
    self.assertTrue(capped.cap_eligible)
    self.assertTrue(capped.cap_applied)
    self.assertTrue(capped.summary.endswith(SUMMARY_CAP_APPLIED_SUFFIX.format(cap_N=400.0)), capped.summary)
    # 표 값 400 = cap: 초과가 아니므로 cap_applied False(적용 대상이긴 함), 문구 없음
    gx3 = self.resolve("hilti_gx3_esr", 19, 17.2)
    self.assertEqual(gx3.allowable_shear_N, 400.0)
    self.assertEqual(gx3.anchor_capacity_kN, 0.4)
    self.assertTrue(gx3.cap_eligible)
    self.assertFalse(gx3.cap_applied)
    self.assertNotIn("내진 상한", gx3.summary)
    # 권장하중(rec) 제품 hET 27 → 400 N: cap 미도달
    rec = self.resolve("hilti_x_u", 27, None)
    self.assertEqual(rec.allowable_shear_N, 400.0)
    self.assertTrue(rec.cap_eligible)
    self.assertFalse(rec.cap_applied)
    self.assertNotIn("내진 상한", rec.summary)

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

  def test_schema_version_is_10(self) -> None:
    self.assertEqual(SCHEMA_VERSION, "10")
    with closing(sqlite3.connect(self.db_path)) as connection:
      version = connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0]
      self.assertEqual(version, "10")
      families = connection.execute("SELECT value FROM metadata WHERE key = 'anchor_seismic_shear_cap_families'").fetchone()[0]
      self.assertEqual(json.loads(families), ["dx", "gx"])
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
    self.assertEqual(migrated.get_anchor_seismic_cap().families, ("dx", "gx"))
    with closing(sqlite3.connect(self.db_path)) as connection:
      self.assertEqual(connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0], "10")

  def test_schema_9_db_is_migrated_with_seed_dir(self) -> None:
    # schema 9(v0.9.0~0.9.2) DB: 앵커 표는 있으나 상한 적용 대상(families)이 없다
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.execute("DELETE FROM metadata WHERE key = 'anchor_seismic_shear_cap_families'")
      connection.execute("UPDATE metadata SET value = '9' WHERE key = 'schema_version'")
      connection.commit()
    migrated = SqliteRepository(self.db_path, ROOT / "data/seed")
    cap = migrated.get_anchor_seismic_cap()
    self.assertEqual(cap.families, ("dx", "gx"))
    self.assertEqual(cap, self.json_repo.get_anchor_seismic_cap())
    with closing(sqlite3.connect(self.db_path)) as connection:
      self.assertEqual(connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0], "10")

  def test_schema_9_db_without_seed_dir_rolls_back(self) -> None:
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.execute("DELETE FROM metadata WHERE key = 'anchor_seismic_shear_cap_families'")
      connection.execute("UPDATE metadata SET value = '9' WHERE key = 'schema_version'")
      connection.commit()
    with self.assertRaises(RepositoryLookupError):
      SqliteRepository(self.db_path)
    with closing(sqlite3.connect(self.db_path)) as connection:
      self.assertEqual(connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0], "9")
      self.assertIsNone(connection.execute("SELECT value FROM metadata WHERE key = 'anchor_seismic_shear_cap_families'").fetchone())

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
      # executescript 암묵 커밋 회귀 방지: 실패한 이관은 테이블 생성까지 롤백되어야 한다
      tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
      self.assertNotIn("anchor_product", tables)
      self.assertNotIn("anchor_load_row", tables)

  def test_capacity_rounding_matches_client_rule(self) -> None:
    # 1000.5 N → 1.001 kN (0.5 올림). 파이썬 round()의 짝수 반올림(1.000)과 달라야 한다
    from backend.engine.anchor import _newton_to_kn

    self.assertEqual(_newton_to_kn(1000.5), 1.001)
    self.assertEqual(_newton_to_kn(300.0), 0.3)
    self.assertEqual(_newton_to_kn(1001.4), 1.001)


if __name__ == "__main__":
  unittest.main()
