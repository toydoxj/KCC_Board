"""SQLite Repository 및 시드 초기화 테스트."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from typing import Mapping, cast

from backend.engine.calculator import calculate_wall_check, request_from_golden_case
from backend.engine.constants import BOARD_YIELD_RATIO_BY_BOARD, BOARD_YIELD_RATIO_FROM_FRACTURE
from backend.engine.repository import (
  DEFAULT_BOARD_E_GPA,
  JsonSeedRepository,
  RepositoryLookupError,
  SqliteRepository,
  initialize_sqlite_from_seed,
)


ROOT = Path(__file__).resolve().parents[1]


class SqliteRepositoryTest(unittest.TestCase):
  def setUp(self) -> None:
    self.temp_dir = tempfile.TemporaryDirectory()
    self.db_path = Path(self.temp_dir.name) / "materials.sqlite3"
    initialize_sqlite_from_seed(self.db_path, ROOT / "data/seed")
    self.sqlite_repository = SqliteRepository(self.db_path)
    self.json_repository = JsonSeedRepository(ROOT / "data/seed")

  def tearDown(self) -> None:
    self.temp_dir.cleanup()

  def test_seed_counts(self) -> None:
    with closing(sqlite3.connect(self.db_path)) as connection:
      self.assertEqual(_count_rows(connection, "board_property"), 22)
      self.assertEqual(_count_rows(connection, "stud_section"), 69)
      self.assertEqual(_count_rows(connection, "bolt_material"), 9)
      self.assertEqual(_count_rows(connection, "stud_method"), 10)

  def test_lookup_matches_json_repository(self) -> None:
    json_board = self.json_repository.get_board("방화", 19.0)
    sqlite_board = self.sqlite_repository.get_board("방화", 19.0)
    self.assertEqual(sqlite_board, json_board)
    self.assertAlmostEqual(sqlite_board.Fu, json_board.Fu)

    json_stud = self.json_repository.get_stud("C-STUD", "50S-45-08")
    sqlite_stud = self.sqlite_repository.get_stud("C-STUD", "50S-45-08")
    self.assertEqual(sqlite_stud, json_stud)

    json_bolt = self.json_repository.get_bolt_material("STS304")
    sqlite_bolt = self.sqlite_repository.get_bolt_material("STS304")
    self.assertEqual(sqlite_bolt, json_bolt)

  def test_board_catalog_preserves_incomplete_excel_rows(self) -> None:
    catalog = self.sqlite_repository.list_board_catalog()
    self.assertEqual(len(catalog), 22)
    incomplete = [board for board in catalog if not board.is_complete]
    self.assertEqual(len(incomplete), 3)
    waterproof = next(board for board in catalog if board.kind == "방수" and board.thickness == 9.5)
    self.assertTrue(waterproof.is_complete)
    self.assertEqual(waterproof.missing_fields, ())
    self.assertAlmostEqual(waterproof.E_GPa or 0.0, 4.72)
    self.assertAlmostEqual(waterproof.Fy or 0.0, (waterproof.Fu or 0.0) * BOARD_YIELD_RATIO_BY_BOARD[("방수", 9.5)][0])
    self.assertEqual(waterproof.yield_ratio_source, "준용: 일반 9.5")
    unlisted = next(board for board in catalog if board.kind == "차음" and board.thickness == 15.0)
    self.assertAlmostEqual(unlisted.yield_ratio, BOARD_YIELD_RATIO_FROM_FRACTURE)
    self.assertEqual(unlisted.yield_ratio_source, "기본값")

  def test_board_yield_ratio_by_kind_and_thickness(self) -> None:
    # B-3: 시험 보드는 실측 Py/Pu, 미시험 보드는 유사 보드 준용값으로 Fy = Fu × 항복비
    for (kind, thickness), (ratio, source) in BOARD_YIELD_RATIO_BY_BOARD.items():
      with self.subTest(kind=kind, thickness=thickness):
        for repository in (self.json_repository, self.sqlite_repository):
          try:
            board = repository.get_board(kind, thickness)
          except RepositoryLookupError:
            continue  # 단위중량 미등재 보드(계산 불가)
          self.assertAlmostEqual(board.Fy, board.Fu * ratio)
          self.assertAlmostEqual(board.yield_ratio, ratio)
          self.assertEqual(board.yield_ratio_source, source)
    fire_19 = self.json_repository.get_board("방화", 19.0)
    self.assertAlmostEqual(fire_19.yield_ratio, 0.70)  # 이선형 근사 꺾임점(2026-10-24)
    self.assertEqual(fire_19.yield_ratio_source, "시험")

  def test_stud_method_catalog_preserves_seed_rows(self) -> None:
    methods = self.sqlite_repository.list_stud_methods()
    self.assertEqual(len(methods), 10)
    c_stud_methods = [item.method for item in methods if item.stud_type == "C-STUD"]
    self.assertNotIn("겹침", c_stud_methods)
    self.assertIn("맞댐이음", c_stud_methods)
    self.assertIn("중앙부 이음", c_stud_methods)
    self.assertIn("일면마감", c_stud_methods)
    self.assertIn(None, [item.method for item in methods if item.stud_type == "CH-STUD"])

  def test_missing_elastic_modulus_uses_default_value(self) -> None:
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.execute(
        "UPDATE board_property SET E_GPa = NULL WHERE kind = ? AND thickness = ?",
        ("방수", 9.5),
      )
      connection.commit()

    board = self.sqlite_repository.get_board("방수", 9.5)
    self.assertAlmostEqual(board.E_GPa, DEFAULT_BOARD_E_GPA)

  def test_existing_sqlite_board_properties_are_migrated_to_current_rules(self) -> None:
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.execute(
        "UPDATE board_property SET Fy = ?, E_GPa = ? WHERE kind = ? AND thickness = ?",
        (999.0, 1.9, "방수", 9.5),
      )
      connection.commit()

    migrated_repository = SqliteRepository(self.db_path)
    board = migrated_repository.get_board("방수", 9.5)

    self.assertAlmostEqual(board.Fy, board.Fu * BOARD_YIELD_RATIO_BY_BOARD[("방수", 9.5)][0])
    self.assertAlmostEqual(board.E_GPa, 4.72)

  def test_existing_sqlite_without_fu_column_is_migrated(self) -> None:
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.executescript(
        """
        CREATE TABLE old_board_property AS
        SELECT kind, thickness, mass_kg_m2, Fy, E_GPa FROM board_property;
        DROP TABLE board_property;
        ALTER TABLE old_board_property RENAME TO board_property;
        """
      )

    migrated_repository = SqliteRepository(self.db_path)
    board = migrated_repository.get_board("방화", 19.0)

    self.assertAlmostEqual(board.Fy, board.Fu * BOARD_YIELD_RATIO_BY_BOARD[("방화", 19.0)][0])
    with closing(sqlite3.connect(self.db_path)) as connection:
      columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(board_property)").fetchall()}
    self.assertIn("Fu", columns)

  def test_incomplete_board_property_is_lookup_error(self) -> None:
    with self.assertRaises(RepositoryLookupError):
      self.sqlite_repository.get_board("차음", 9.5)

  def test_golden_cases_with_sqlite_repository(self) -> None:
    with (ROOT / "tests/golden/cases.json").open(encoding="utf-8") as file:
      data = cast(Mapping[str, object], json.load(file))
    tolerance_rel = float(data["_tolerance_rel"])
    cases = cast(list[Mapping[str, object]], data["cases"])

    for case in cases:
      with self.subTest(case=case["id"]):
        request = request_from_golden_case(dict(case))
        result = calculate_wall_check(request, self.sqlite_repository)
        expected = cast(Mapping[str, object], case["expected"])
        for key, actual in {
          "neutral_axis_mm": result.neutral_axis_mm,
          "I_full_mm4": result.I_full_mm4,
          "eta": result.eta,
          "I_eff_mm4": result.I_eff_mm4,
          "Mn_kNm": result.Mn_kNm,
          "Mu_kNm": result.Mu_kNm,
          "stress_ratio": result.stress_ratio,
          "deflection_mm": result.deflection_mm,
          "deflection_limit_mm": result.deflection_limit_mm,
          "seismic_moment_kNm": result.seismic_moment_kNm,
        }.items():
          target = float(expected[key])
          relative_error = abs(actual - target) / max(abs(target), 1.0)
          self.assertLessEqual(
            relative_error,
            tolerance_rel,
            f"{key}: actual={actual}, expected={target}, rel={relative_error}",
          )


def _count_rows(connection: sqlite3.Connection, table_name: str) -> int:
  row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
  if row is None:
    raise AssertionError(f"{table_name} 행 수를 조회할 수 없습니다.")
  return int(row[0])


if __name__ == "__main__":
  unittest.main()
