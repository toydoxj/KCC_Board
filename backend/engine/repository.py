"""자재 Repository 구현체."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence, cast

from backend.engine.constants import BOARD_YIELD_RATIO_BY_BOARD, BOARD_YIELD_RATIO_FROM_FRACTURE


DEFAULT_BOARD_E_GPA = 1.9
BOARD_ELASTIC_MODULUS_GPA: dict[tuple[str, float], float] = {
  ("일반", 9.5): 3.20,
  ("일반", 12.5): 2.70,
  ("일반", 15.0): 2.60,
  ("방수", 9.5): 4.72,
  ("방수", 12.5): 3.56,
  ("방균", 9.5): 3.03,
  ("방균", 12.5): 2.74,
  ("방화", 12.5): 3.00,
  ("방화", 15.0): 4.20,
  ("방화", 19.0): 3.00,
  ("방화", 25.0): 2.50,
  ("방화방수", 12.5): 3.30,
  ("방화방수", 15.0): 3.22,
  ("방화방수", 19.0): 2.74,
  ("차음", 9.5): 3.63,
  ("차음", 12.5): 3.10,
  ("고강도일반", 12.5): 3.49,
  ("고강도일반", 15.0): 3.91,
  ("전방수", 12.5): 5.00,
  ("전방수", 15.0): 2.05,
  ("고강도전방수", 12.5): 4.06,
}


@dataclass(frozen=True)
class BoardProperty:
  kind: str
  thickness: float
  mass_kg_m2: float
  Fy: float
  Fu: float
  E_GPa: float
  # 항복비 Fy/Fu와 근거(시험/준용/기본값)
  yield_ratio: float = BOARD_YIELD_RATIO_FROM_FRACTURE
  yield_ratio_source: str = "기본값"


@dataclass(frozen=True)
class BoardCatalogItem:
  kind: str
  thickness: float
  mass_kg_m2: float | None
  Fy: float | None
  Fu: float | None
  E_GPa: float | None
  is_complete: bool
  missing_fields: tuple[str, ...]
  yield_ratio: float = BOARD_YIELD_RATIO_FROM_FRACTURE
  yield_ratio_source: str = "기본값"


SCHEMA_VERSION = "7"
STUD_STEEL_SEED_FILE = "stud_steel.json"


@dataclass(frozen=True)
class StudSteel:
  """스터드 강재(심사의견 B-8). status '확정'/'미확정'으로 강종 확인 여부를 표시한다."""

  steel_grade: str
  label: str
  Fy: float
  Fu: float
  status: str
  candidate_standard: str | None
  source: str
  is_default: bool


@dataclass(frozen=True)
class StudSection:
  group: str
  name: str
  H: float
  B: float
  t: float | None
  A: float
  cx: float
  cy: float
  Ix: float
  Iy: float
  Sx: float
  Sy: float
  rx: float
  ry: float
  section_class: str
  # 유효단면계수(AISI S100-16 부록 1, f = Fy). 미등록(None)이면 계산엔진이 명시적 오류를 발생시킨다.
  Se: float | None = None
  # Se 산정에 쓴 Fy(MPa). 연결 강재 Fy와 다르면 계산엔진이 오류를 발생시킨다(Se 재산정 필요).
  Se_basis_Fy_MPa: float | None = None
  # 연결 강재. 구 DB 등으로 연결되지 않으면 None — 계산엔진이 명시적 오류를 발생시킨다.
  steel: StudSteel | None = None


@dataclass(frozen=True)
class StudMethod:
  stud_type: str
  method: str | None


@dataclass(frozen=True)
class BoltMaterial:
  material: str
  Fu: float


class RepositoryLookupError(ValueError):
  """자재 DB 조회 실패 오류."""


class MaterialRepository(Protocol):
  def get_board(self, kind: str, thickness: float) -> BoardProperty:
    """석고보드 물성을 조회한다."""

  def get_stud(self, group: str, name: str) -> StudSection:
    """스터드 단면 제원을 조회한다."""

  def get_bolt_material(self, material: str) -> BoltMaterial:
    """볼트 재질 강도를 조회한다."""

  def list_boards(self) -> tuple[BoardProperty, ...]:
    """계산 가능한 석고보드 물성 목록을 조회한다."""

  def list_board_catalog(self) -> tuple[BoardCatalogItem, ...]:
    """Property_Gymsumboard 전체 보드 물성 목록을 조회한다."""

  def list_studs(self) -> tuple[StudSection, ...]:
    """스터드 단면 목록을 조회한다."""

  def list_stud_methods(self) -> tuple[StudMethod, ...]:
    """스터드별 시공방식 목록을 조회한다."""

  def list_bolt_materials(self) -> tuple[BoltMaterial, ...]:
    """볼트 재질 목록을 조회한다."""

  def list_stud_steels(self) -> tuple[StudSteel, ...]:
    """스터드 강재 목록을 조회한다."""


class JsonSeedRepository:
  def __init__(self, seed_dir: Path | str = Path("data/seed")) -> None:
    self.seed_dir = Path(seed_dir)
    self._board_catalog = self._load_board_catalog()
    self._boards = self._load_boards()
    self._steels = _stud_steels_from_items(self._read_items(STUD_STEEL_SEED_FILE))
    self._studs = self._load_studs()
    self._stud_methods = self._load_stud_methods()
    self._bolts = self._load_bolts()

  def get_board(self, kind: str, thickness: float) -> BoardProperty:
    key = (kind, float(thickness))
    try:
      return self._boards[key]
    except KeyError as exc:
      raise RepositoryLookupError(f"등록되지 않은 석고보드입니다: {kind} {thickness}") from exc

  def get_stud(self, group: str, name: str) -> StudSection:
    key = (group, name)
    try:
      return self._studs[key]
    except KeyError as exc:
      raise RepositoryLookupError(f"등록되지 않은 스터드입니다: {group} {name}") from exc

  def get_bolt_material(self, material: str) -> BoltMaterial:
    try:
      return self._bolts[material]
    except KeyError as exc:
      raise RepositoryLookupError(f"등록되지 않은 볼트 재질입니다: {material}") from exc

  def list_boards(self) -> tuple[BoardProperty, ...]:
    return tuple(sorted(self._boards.values(), key=lambda board: (board.kind, board.thickness)))

  def list_board_catalog(self) -> tuple[BoardCatalogItem, ...]:
    return self._board_catalog

  def list_studs(self) -> tuple[StudSection, ...]:
    return tuple(sorted(self._studs.values(), key=lambda stud: (stud.group, stud.name)))

  def list_stud_methods(self) -> tuple[StudMethod, ...]:
    return self._stud_methods

  def list_bolt_materials(self) -> tuple[BoltMaterial, ...]:
    return tuple(sorted(self._bolts.values(), key=lambda bolt: bolt.material))

  def list_stud_steels(self) -> tuple[StudSteel, ...]:
    return tuple(sorted(self._steels.values(), key=lambda steel: steel.steel_grade))

  def _read_items(self, filename: str) -> Sequence[Mapping[str, object]]:
    return _read_seed_items(self.seed_dir, filename)

  def _load_boards(self) -> dict[tuple[str, float], BoardProperty]:
    boards: dict[tuple[str, float], BoardProperty] = {}
    for item in self._board_catalog:
      if not item.is_complete:
        continue
      board = BoardProperty(
        kind=item.kind,
        thickness=item.thickness,
        mass_kg_m2=float(item.mass_kg_m2),
        Fy=float(item.Fy),
        Fu=float(item.Fu),
        E_GPa=float(item.E_GPa),
        yield_ratio=item.yield_ratio,
        yield_ratio_source=item.yield_ratio_source,
      )
      boards[(board.kind, board.thickness)] = board
    return boards

  def _load_board_catalog(self) -> tuple[BoardCatalogItem, ...]:
    return tuple(
      _board_catalog_item_from_mapping(item)
      for item in self._read_items("board_property.json")
    )

  def _load_studs(self) -> dict[tuple[str, str], StudSection]:
    studs: dict[tuple[str, str], StudSection] = {}
    for item in self._read_items("stud_section.json"):
      grade = _resolve_stud_steel_grade(item.get("steel_grade"), self._steels, f"{item['group']} {item['name']}")
      stud = _stud_from_mapping(item, self._steels[grade])
      studs[(stud.group, stud.name)] = stud
    return studs

  def _load_bolts(self) -> dict[str, BoltMaterial]:
    bolts: dict[str, BoltMaterial] = {}
    for item in self._read_items("bolt_material.json"):
      bolt = BoltMaterial(material=str(item["material"]), Fu=float(item["Fu"]))
      bolts[bolt.material] = bolt
    return bolts

  def _load_stud_methods(self) -> tuple[StudMethod, ...]:
    return tuple(
      StudMethod(
        stud_type=str(item["stud_type"]),
        method=None if item.get("method") is None else str(item["method"]),
      )
      for item in self._read_items("stud_method.json")
    )


class SqliteRepository:
  def __init__(self, db_path: Path | str, seed_dir: Path | str | None = None) -> None:
    """seed_dir는 구 DB(schema 6 이하) 이관 시 스터드 강재 seed를 읽는 데에만 쓴다."""
    self.db_path = Path(db_path)
    self.seed_dir = None if seed_dir is None else Path(seed_dir)
    self._ensure_board_property_rules()
    self._board_cache: dict[tuple[str, float], BoardProperty] = {}
    self._stud_cache: dict[tuple[str, str], StudSection] = {}
    self._bolt_cache: dict[str, BoltMaterial] = {}

  def get_board(self, kind: str, thickness: float) -> BoardProperty:
    key = (kind, float(thickness))
    if key in self._board_cache:
      return self._board_cache[key]
    query = """
      SELECT kind, thickness, mass_kg_m2, Fy, Fu, E_GPa
      FROM board_property
      WHERE kind = ? AND thickness = ?
    """
    row = self._fetch_one(query, key)
    if row is None or row["mass_kg_m2"] is None:
      raise RepositoryLookupError(f"등록되지 않은 석고보드입니다: {kind} {thickness}")
    board_key = (str(row["kind"]), float(row["thickness"]))
    fracture_strength = _board_fracture_strength(row["Fu"], row["Fy"], board_key)
    if fracture_strength is None:
      raise RepositoryLookupError(f"등록되지 않은 석고보드입니다: {kind} {thickness}")
    ratio, source = _board_yield_ratio(board_key)
    board = BoardProperty(
      kind=board_key[0],
      thickness=board_key[1],
      mass_kg_m2=float(row["mass_kg_m2"]),
      Fy=_board_yield_strength(fracture_strength, board_key),
      Fu=fracture_strength,
      E_GPa=_elastic_modulus_or_default(row["E_GPa"]),
      yield_ratio=ratio,
      yield_ratio_source=source,
    )
    self._board_cache[key] = board
    return board

  def get_stud(self, group: str, name: str) -> StudSection:
    key = (group, name)
    if key in self._stud_cache:
      return self._stud_cache[key]
    row = self._fetch_one(f"{_STUD_SELECT_SQL} WHERE s.group_name = ? AND s.name = ?", key)
    if row is None:
      raise RepositoryLookupError(f"등록되지 않은 스터드입니다: {group} {name}")
    stud = _stud_from_row(row)
    self._stud_cache[key] = stud
    return stud

  def get_bolt_material(self, material: str) -> BoltMaterial:
    if material in self._bolt_cache:
      return self._bolt_cache[material]
    row = self._fetch_one("SELECT material, Fu FROM bolt_material WHERE material = ?", (material,))
    if row is None:
      raise RepositoryLookupError(f"등록되지 않은 볼트 재질입니다: {material}")
    bolt = BoltMaterial(material=str(row["material"]), Fu=float(row["Fu"]))
    self._bolt_cache[material] = bolt
    return bolt

  def list_boards(self) -> tuple[BoardProperty, ...]:
    query = """
      SELECT kind, thickness, mass_kg_m2, Fy, Fu, E_GPa
      FROM board_property
      WHERE mass_kg_m2 IS NOT NULL AND (Fu IS NOT NULL OR Fy IS NOT NULL)
      ORDER BY kind, thickness
    """
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.row_factory = sqlite3.Row
      rows = connection.execute(query).fetchall()
    boards: list[BoardProperty] = []
    for row in rows:
      board_key = (str(row["kind"]), float(row["thickness"]))
      fracture_strength = _board_fracture_strength_required(row["Fu"], row["Fy"], board_key)
      ratio, source = _board_yield_ratio(board_key)
      boards.append(
        BoardProperty(
          kind=board_key[0],
          thickness=board_key[1],
          mass_kg_m2=float(row["mass_kg_m2"]),
          Fy=_board_yield_strength(fracture_strength, board_key),
          Fu=fracture_strength,
          E_GPa=_elastic_modulus_or_default(row["E_GPa"]),
          yield_ratio=ratio,
          yield_ratio_source=source,
        )
      )
    return tuple(boards)

  def list_board_catalog(self) -> tuple[BoardCatalogItem, ...]:
    query = """
      SELECT kind, thickness, mass_kg_m2, Fy, Fu, E_GPa
      FROM board_property
      ORDER BY kind, thickness
    """
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.row_factory = sqlite3.Row
      rows = connection.execute(query).fetchall()
    return tuple(_board_catalog_item_from_mapping(dict(row)) for row in rows)

  def list_studs(self) -> tuple[StudSection, ...]:
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.row_factory = sqlite3.Row
      rows = connection.execute(f"{_STUD_SELECT_SQL} ORDER BY s.group_name, s.name").fetchall()
    return tuple(_stud_from_row(row) for row in rows)

  def list_stud_methods(self) -> tuple[StudMethod, ...]:
    query = "SELECT stud_type, method FROM stud_method ORDER BY id"
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.row_factory = sqlite3.Row
      rows = connection.execute(query).fetchall()
    return tuple(
      StudMethod(
        stud_type=str(row["stud_type"]),
        method=None if row["method"] is None else str(row["method"]),
      )
      for row in rows
    )

  def list_bolt_materials(self) -> tuple[BoltMaterial, ...]:
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.row_factory = sqlite3.Row
      rows = connection.execute("SELECT material, Fu FROM bolt_material ORDER BY material").fetchall()
    return tuple(BoltMaterial(material=str(row["material"]), Fu=float(row["Fu"])) for row in rows)

  def list_stud_steels(self) -> tuple[StudSteel, ...]:
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.row_factory = sqlite3.Row
      rows = connection.execute("SELECT * FROM stud_steel ORDER BY steel_grade").fetchall()
    return tuple(_stud_steel_from_mapping(dict(row)) for row in rows)

  def _fetch_one(self, query: str, params: tuple[object, ...]) -> sqlite3.Row | None:
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.row_factory = sqlite3.Row
      return connection.execute(query, params).fetchone()

  def _ensure_board_property_rules(self) -> None:
    """구 DB를 현재 규칙(schema 7)으로 이관한다. 한 트랜잭션으로 처리하며 실패하면 되돌린다."""
    with closing(sqlite3.connect(self.db_path)) as connection:
      columns = _table_columns(connection, "board_property")
      if not columns:
        return
      connection.execute("BEGIN")
      try:
        self._migrate(connection, columns)
      except Exception:
        connection.rollback()
        raise
      connection.commit()

  def _migrate(self, connection: sqlite3.Connection, columns: set[str]) -> None:
    connection.execute(
      """
      CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      )
      """
    )
    if "Fu" not in columns:
      connection.execute("ALTER TABLE board_property ADD COLUMN Fu REAL")
    stud_columns = _table_columns(connection, "stud_section")
    if stud_columns and "Se" not in stud_columns:
      # 구 로컬 DB: Se 열만 추가(NULL). 단면성능이 구버전이므로 계산 시 명시적 오류로 init_db 재실행을 유도한다.
      connection.execute("ALTER TABLE stud_section ADD COLUMN Se REAL")
    # 기존 로컬 DB는 Fu가 없었으므로 저장된 Fy를 레거시 항복강도로 보고 Fu를 역산한다.
    connection.execute(
      "UPDATE board_property SET Fu = Fy / ? WHERE Fu IS NULL AND Fy IS NOT NULL",
      (BOARD_YIELD_RATIO_FROM_FRACTURE,),
    )
    connection.execute(
      "UPDATE board_property SET Fy = Fu * ? WHERE Fu IS NOT NULL",
      (BOARD_YIELD_RATIO_FROM_FRACTURE,),
    )
    # 종류·두께별 항복비(B-3) 적용
    connection.executemany(
      "UPDATE board_property SET Fy = Fu * ? WHERE Fu IS NOT NULL AND kind = ? AND thickness = ?",
      [(ratio, kind, thickness) for (kind, thickness), (ratio, _) in BOARD_YIELD_RATIO_BY_BOARD.items()],
    )
    connection.executemany(
      "UPDATE board_property SET E_GPa = ? WHERE kind = ? AND thickness = ?",
      [
        (elastic_modulus, kind, thickness)
        for (kind, thickness), elastic_modulus in BOARD_ELASTIC_MODULUS_GPA.items()
      ],
    )
    if stud_columns:
      _migrate_stud_steel(connection, self.seed_dir)
    connection.execute(
      "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
      ("schema_version", SCHEMA_VERSION),
    )


def initialize_sqlite_from_seed(
  db_path: Path | str,
  seed_dir: Path | str = Path("data/seed"),
  reset: bool = True,
) -> None:
  target = Path(db_path)
  target.parent.mkdir(parents=True, exist_ok=True)
  seed_root = Path(seed_dir)

  with closing(sqlite3.connect(target)) as connection:
    if reset:
      _drop_tables(connection)
    _create_tables(connection)
    # reset=False로 구 테이블을 유지하는 경우에도 신규 열을 갖추게 한다.
    _add_missing_stud_columns(connection)
    _insert_seed_data(connection, seed_root)
    connection.commit()


def _read_seed_items(seed_dir: Path, filename: str) -> Sequence[Mapping[str, object]]:
  path = seed_dir / filename
  with path.open(encoding="utf-8") as file:
    data = cast(Mapping[str, object], json.load(file))
  return cast(Sequence[Mapping[str, object]], data["items"])


def _drop_tables(connection: sqlite3.Connection) -> None:
  for table in ["stud_method", "bolt_material", "stud_section", "stud_steel", "board_property", "metadata"]:
    connection.execute(f"DROP TABLE IF EXISTS {table}")


def _create_tables(connection: sqlite3.Connection) -> None:
  connection.executescript(
    """
    CREATE TABLE IF NOT EXISTS metadata (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS board_property (
      kind TEXT NOT NULL,
      thickness REAL NOT NULL,
      mass_kg_m2 REAL,
      Fy REAL,
      Fu REAL,
      E_GPa REAL,
      PRIMARY KEY (kind, thickness)
    );

    CREATE TABLE IF NOT EXISTS stud_section (
      group_name TEXT NOT NULL,
      name TEXT NOT NULL,
      H REAL NOT NULL,
      B REAL NOT NULL,
      t REAL,
      A REAL NOT NULL,
      cx REAL NOT NULL,
      cy REAL NOT NULL,
      Ix REAL NOT NULL,
      Iy REAL NOT NULL,
      Sx REAL NOT NULL,
      Sy REAL NOT NULL,
      rx REAL NOT NULL,
      ry REAL NOT NULL,
      section_class TEXT NOT NULL,
      Se REAL,
      Se_basis_Fy_MPa REAL,
      steel_grade TEXT,
      PRIMARY KEY (group_name, name)
    );
"""
    + _STUD_STEEL_TABLE_SQL
    + """;

    CREATE TABLE IF NOT EXISTS bolt_material (
      material TEXT PRIMARY KEY,
      Fu REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS stud_method (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      stud_type TEXT NOT NULL,
      method TEXT
    );
    """
  )


def _insert_seed_data(connection: sqlite3.Connection, seed_dir: Path) -> None:
  connection.execute("DELETE FROM metadata")
  connection.execute("DELETE FROM board_property")
  connection.execute("DELETE FROM stud_section")
  connection.execute("DELETE FROM stud_steel")
  connection.execute("DELETE FROM bolt_material")
  connection.execute("DELETE FROM stud_method")

  board_items = _read_seed_items(seed_dir, "board_property.json")
  connection.executemany(
    """
    INSERT INTO board_property (kind, thickness, mass_kg_m2, Fy, Fu, E_GPa)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
    [_board_seed_row(item) for item in board_items],
  )

  steels = _stud_steels_from_items(_read_seed_items(seed_dir, STUD_STEEL_SEED_FILE))
  _insert_stud_steels(connection, steels.values())

  stud_items = _read_seed_items(seed_dir, "stud_section.json")
  connection.executemany(
    """
    INSERT INTO stud_section (
      group_name, name, H, B, t, A, cx, cy, Ix, Iy, Sx, Sy, rx, ry, section_class, Se, Se_basis_Fy_MPa, steel_grade
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    [
      (
        str(item["group"]),
        str(item["name"]),
        float(item["H"]),
        float(item["B"]),
        _nullable_float(item.get("t")),
        float(item["A"]),
        float(item["cx"]),
        float(item["cy"]),
        float(item["Ix"]),
        float(item["Iy"]),
        float(item["Sx"]),
        float(item["Sy"]),
        float(item["rx"]),
        float(item["ry"]),
        str(item["section_class"]),
        _nullable_float(item.get("Se")),
        _nullable_float(item.get("Se_basis_Fy_MPa")),
        # 실제 식별자를 저장해 이후 기본 강재가 바뀌어도 기존 규격의 강재가 조용히 바뀌지 않게 한다.
        _resolve_stud_steel_grade(item.get("steel_grade"), steels, f"{item['group']} {item['name']}"),
      )
      for item in stud_items
    ],
  )

  bolt_items = _read_seed_items(seed_dir, "bolt_material.json")
  connection.executemany(
    "INSERT INTO bolt_material (material, Fu) VALUES (?, ?)",
    [(str(item["material"]), float(item["Fu"])) for item in bolt_items],
  )

  method_items = _read_seed_items(seed_dir, "stud_method.json")
  connection.executemany(
    "INSERT INTO stud_method (stud_type, method) VALUES (?, ?)",
    [(str(item["stud_type"]), None if item.get("method") is None else str(item["method"])) for item in method_items],
  )

  connection.execute("INSERT INTO metadata (key, value) VALUES (?, ?)", ("schema_version", SCHEMA_VERSION))
  connection.commit()


_STUD_STEEL_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS stud_steel (
      steel_grade TEXT PRIMARY KEY,
      label TEXT NOT NULL,
      Fy REAL NOT NULL,
      Fu REAL NOT NULL,
      status TEXT NOT NULL,
      candidate_standard TEXT,
      source TEXT NOT NULL,
      is_default INTEGER NOT NULL
    )
"""

_STUD_SELECT_SQL = """
  SELECT s.group_name AS "group", s.name, s.H, s.B, s.t, s.A, s.cx, s.cy, s.Ix, s.Iy, s.Sx, s.Sy, s.rx, s.ry,
    s.section_class, s.Se, s.Se_basis_Fy_MPa, s.steel_grade AS ref_steel_grade,
    g.steel_grade, g.label, g.Fy, g.Fu, g.status, g.candidate_standard, g.source, g.is_default
  FROM stud_section AS s
  LEFT JOIN stud_steel AS g ON s.steel_grade = g.steel_grade
"""


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
  return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_missing_stud_columns(connection: sqlite3.Connection) -> None:
  columns = _table_columns(connection, "stud_section")
  for name, sql_type in (("Se", "REAL"), ("Se_basis_Fy_MPa", "REAL"), ("steel_grade", "TEXT")):
    if columns and name not in columns:
      connection.execute(f"ALTER TABLE stud_section ADD COLUMN {name} {sql_type}")


def _migrate_stud_steel(connection: sqlite3.Connection, seed_dir: Path | None) -> None:
  """schema 6 이하 DB에 스터드 강재 테이블·참조를 추가한다(B-8).

  Se_basis_Fy_MPa는 근거가 없으므로 NULL로 둔다 — 계산 시 명시적 오류로 init_db 재실행을 유도한다.
  """
  connection.execute(_STUD_STEEL_TABLE_SQL)
  _add_missing_stud_columns(connection)
  if connection.execute("SELECT COUNT(*) FROM stud_steel").fetchone()[0] == 0:
    if seed_dir is None:
      raise RepositoryLookupError(
        "구 자재 DB에 스터드 강재(stud_steel) 테이블이 없습니다. seed 경로를 지정하거나 init_db를 다시 실행하십시오."
      )
    _insert_stud_steels(connection, _stud_steels_from_items(_read_seed_items(seed_dir, STUD_STEEL_SEED_FILE)).values())
  connection.row_factory = sqlite3.Row
  steels = _stud_steels_from_items([dict(row) for row in connection.execute("SELECT * FROM stud_steel").fetchall()])
  connection.execute(
    "UPDATE stud_section SET steel_grade = ? WHERE steel_grade IS NULL",
    (_default_stud_steel_grade(steels),),
  )
  missing = [
    str(row[0])
    for row in connection.execute(
      "SELECT DISTINCT steel_grade FROM stud_section WHERE steel_grade NOT IN (SELECT steel_grade FROM stud_steel)"
    ).fetchall()
  ]
  if missing:
    raise RepositoryLookupError(f"등록되지 않은 스터드 강재를 참조합니다: {', '.join(missing)}")


def _insert_stud_steels(connection: sqlite3.Connection, steels: Iterable[StudSteel]) -> None:
  connection.executemany(
    """
    INSERT INTO stud_steel (steel_grade, label, Fy, Fu, status, candidate_standard, source, is_default)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
    [
      (s.steel_grade, s.label, s.Fy, s.Fu, s.status, s.candidate_standard, s.source, int(s.is_default))
      for s in steels
    ],
  )


def _stud_steel_from_mapping(item: Mapping[str, object]) -> StudSteel:
  steel = StudSteel(
    steel_grade=str(item["steel_grade"]),
    label=str(item["label"]),
    Fy=float(cast(float, item["Fy"])),
    Fu=float(cast(float, item["Fu"])),
    status=str(item["status"]),
    candidate_standard=None if item.get("candidate_standard") is None else str(item["candidate_standard"]),
    source=str(item["source"]),
    is_default=bool(item["is_default"]),
  )
  if not 0.0 < steel.Fy <= steel.Fu:
    raise RepositoryLookupError(f"스터드 강재 {steel.steel_grade}의 Fy·Fu가 잘못되었습니다: Fy {steel.Fy}, Fu {steel.Fu}")
  return steel


def _stud_steels_from_items(items: Sequence[Mapping[str, object]]) -> dict[str, StudSteel]:
  steels: dict[str, StudSteel] = {}
  for item in items:
    steel = _stud_steel_from_mapping(item)
    if steel.steel_grade in steels:
      raise RepositoryLookupError(f"스터드 강재 식별자가 중복되었습니다: {steel.steel_grade}")
    steels[steel.steel_grade] = steel
  _default_stud_steel_grade(steels)
  return steels


def _default_stud_steel_grade(steels: Mapping[str, StudSteel]) -> str:
  defaults = [steel.steel_grade for steel in steels.values() if steel.is_default]
  if len(defaults) != 1:
    raise RepositoryLookupError(f"기본 스터드 강재는 정확히 1개여야 합니다(현재 {len(defaults)}개).")
  return defaults[0]


def _resolve_stud_steel_grade(value: object, steels: Mapping[str, StudSteel], stud_label: str) -> str:
  """규격의 steel_grade를 확인한다. 생략하면 기본 강재, 미등록 식별자이면 오류."""
  if value is None:
    return _default_stud_steel_grade(steels)
  grade = str(value)
  if grade not in steels:
    raise RepositoryLookupError(f"스터드 {stud_label}가 등록되지 않은 강재를 참조합니다: {grade}")
  return grade


def _stud_from_mapping(item: Mapping[str, object], steel: StudSteel | None) -> StudSection:
  return StudSection(
    group=str(item["group"]),
    name=str(item["name"]),
    H=float(cast(float, item["H"])),
    B=float(cast(float, item["B"])),
    t=_nullable_float(item.get("t")),
    A=float(cast(float, item["A"])),
    cx=float(cast(float, item["cx"])),
    cy=float(cast(float, item["cy"])),
    Ix=float(cast(float, item["Ix"])),
    Iy=float(cast(float, item["Iy"])),
    Sx=float(cast(float, item["Sx"])),
    Sy=float(cast(float, item["Sy"])),
    rx=float(cast(float, item["rx"])),
    ry=float(cast(float, item["ry"])),
    section_class=str(item["section_class"]),
    Se=_nullable_float(item.get("Se")),
    Se_basis_Fy_MPa=_nullable_float(item.get("Se_basis_Fy_MPa")),
    steel=steel,
  )


def _stud_from_row(row: sqlite3.Row) -> StudSection:
  data = dict(row)
  if data["steel_grade"] is None:
    raise RepositoryLookupError(
      f"스터드 {data['group']} {data['name']}의 강재 참조({data['ref_steel_grade']})가 자재 DB에 없습니다. init_db를 다시 실행하십시오."
    )
  return _stud_from_mapping(data, _stud_steel_from_mapping(data))


def _nullable_float(value: object) -> float | None:
  if value is None:
    return None
  return float(value)


def _elastic_modulus_or_default(value: object) -> float:
  if value is None:
    return DEFAULT_BOARD_E_GPA
  return float(value)


def _board_yield_ratio(board_key: tuple[str, float] | None) -> tuple[float, str]:
  # 종류·두께별 항복비(B-3). 표에 없으면 기본값 0.6을 적용하고 근거를 '기본값'으로 표시한다.
  if board_key is not None and board_key in BOARD_YIELD_RATIO_BY_BOARD:
    return BOARD_YIELD_RATIO_BY_BOARD[board_key]
  return BOARD_YIELD_RATIO_FROM_FRACTURE, "기본값"


def _board_fracture_strength(
  fu_value: object,
  fy_value: object,
  board_key: tuple[str, float] | None = None,
) -> float | None:
  fu = _nullable_float(fu_value)
  if fu is not None:
    return fu
  # 구 DB(Fu 없음)의 Fy는 기본 항복비 0.6으로 등재된 레거시 값이다.
  legacy_yield_strength = _nullable_float(fy_value)
  if legacy_yield_strength is None:
    return None
  return legacy_yield_strength / BOARD_YIELD_RATIO_FROM_FRACTURE


def _board_fracture_strength_required(
  fu_value: object,
  fy_value: object,
  board_key: tuple[str, float] | None = None,
) -> float:
  fracture_strength = _board_fracture_strength(fu_value, fy_value, board_key)
  if fracture_strength is None:
    raise RepositoryLookupError("석고보드 Fu와 Fy가 모두 누락되었습니다.")
  return fracture_strength


def _board_yield_strength(fracture_strength: float, board_key: tuple[str, float] | None = None) -> float:
  ratio, _ = _board_yield_ratio(board_key)
  return fracture_strength * ratio


def _board_seed_row(item: Mapping[str, object]) -> tuple[object, ...]:
  board_key = (str(item["kind"]), float(cast(float, item["thickness"])))
  fu = _board_fracture_strength(item.get("Fu"), item.get("Fy"), board_key)
  fy = _board_yield_strength(fu, board_key) if fu is not None else None
  return (
    str(item["kind"]),
    float(item["thickness"]),
    _nullable_float(item.get("mass_kg_m2")),
    fy,
    fu,
    _elastic_modulus_or_default(item.get("E_GPa")),
  )


def _board_catalog_item_from_mapping(item: Mapping[str, object]) -> BoardCatalogItem:
  mass = _nullable_float(item.get("mass_kg_m2"))
  board_key = (str(item["kind"]), float(cast(float, item["thickness"])))
  fu = _board_fracture_strength(item.get("Fu"), item.get("Fy"), board_key)
  fy = _board_yield_strength(fu, board_key) if fu is not None else None
  ratio, source = _board_yield_ratio(board_key)
  elastic_modulus = _elastic_modulus_or_default(item.get("E_GPa"))
  missing_fields = tuple(
    field
    for field, value in [
      ("mass_kg_m2", mass),
      ("Fu", fu),
    ]
    if value is None
  )
  return BoardCatalogItem(
    kind=str(item["kind"]),
    thickness=float(item["thickness"]),
    mass_kg_m2=mass,
    Fy=fy,
    Fu=fu,
    E_GPa=elastic_modulus,
    is_complete=len(missing_fields) == 0,
    missing_fields=missing_fields,
    yield_ratio=ratio,
    yield_ratio_source=source,
  )
