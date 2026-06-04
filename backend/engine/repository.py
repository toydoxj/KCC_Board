"""자재 Repository 구현체."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence, cast


@dataclass(frozen=True)
class BoardProperty:
  kind: str
  thickness: float
  mass_kg_m2: float
  Fy: float
  E_GPa: float


@dataclass(frozen=True)
class BoardCatalogItem:
  kind: str
  thickness: float
  mass_kg_m2: float | None
  Fy: float | None
  E_GPa: float | None
  is_complete: bool
  missing_fields: tuple[str, ...]


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


class JsonSeedRepository:
  def __init__(self, seed_dir: Path | str = Path("data/seed")) -> None:
    self.seed_dir = Path(seed_dir)
    self._board_catalog = self._load_board_catalog()
    self._boards = self._load_boards()
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
        E_GPa=float(item.E_GPa),
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
      stud = StudSection(
        group=str(item["group"]),
        name=str(item["name"]),
        H=float(item["H"]),
        B=float(item["B"]),
        t=None if item.get("t") is None else float(item["t"]),
        A=float(item["A"]),
        cx=float(item["cx"]),
        cy=float(item["cy"]),
        Ix=float(item["Ix"]),
        Iy=float(item["Iy"]),
        Sx=float(item["Sx"]),
        Sy=float(item["Sy"]),
        rx=float(item["rx"]),
        ry=float(item["ry"]),
        section_class=str(item["section_class"]),
      )
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
  def __init__(self, db_path: Path | str) -> None:
    self.db_path = Path(db_path)
    self._board_cache: dict[tuple[str, float], BoardProperty] = {}
    self._stud_cache: dict[tuple[str, str], StudSection] = {}
    self._bolt_cache: dict[str, BoltMaterial] = {}

  def get_board(self, kind: str, thickness: float) -> BoardProperty:
    key = (kind, float(thickness))
    if key in self._board_cache:
      return self._board_cache[key]
    query = """
      SELECT kind, thickness, mass_kg_m2, Fy, E_GPa
      FROM board_property
      WHERE kind = ? AND thickness = ?
    """
    row = self._fetch_one(query, key)
    if row is None or row["mass_kg_m2"] is None or row["Fy"] is None or row["E_GPa"] is None:
      raise RepositoryLookupError(f"등록되지 않은 석고보드입니다: {kind} {thickness}")
    board = BoardProperty(
      kind=str(row["kind"]),
      thickness=float(row["thickness"]),
      mass_kg_m2=float(row["mass_kg_m2"]),
      Fy=float(row["Fy"]),
      E_GPa=float(row["E_GPa"]),
    )
    self._board_cache[key] = board
    return board

  def get_stud(self, group: str, name: str) -> StudSection:
    key = (group, name)
    if key in self._stud_cache:
      return self._stud_cache[key]
    query = """
      SELECT group_name, name, H, B, t, A, cx, cy, Ix, Iy, Sx, Sy, rx, ry, section_class
      FROM stud_section
      WHERE group_name = ? AND name = ?
    """
    row = self._fetch_one(query, key)
    if row is None:
      raise RepositoryLookupError(f"등록되지 않은 스터드입니다: {group} {name}")
    stud = StudSection(
      group=str(row["group_name"]),
      name=str(row["name"]),
      H=float(row["H"]),
      B=float(row["B"]),
      t=None if row["t"] is None else float(row["t"]),
      A=float(row["A"]),
      cx=float(row["cx"]),
      cy=float(row["cy"]),
      Ix=float(row["Ix"]),
      Iy=float(row["Iy"]),
      Sx=float(row["Sx"]),
      Sy=float(row["Sy"]),
      rx=float(row["rx"]),
      ry=float(row["ry"]),
      section_class=str(row["section_class"]),
    )
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
      SELECT kind, thickness, mass_kg_m2, Fy, E_GPa
      FROM board_property
      WHERE mass_kg_m2 IS NOT NULL AND Fy IS NOT NULL AND E_GPa IS NOT NULL
      ORDER BY kind, thickness
    """
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.row_factory = sqlite3.Row
      rows = connection.execute(query).fetchall()
    return tuple(
      BoardProperty(
        kind=str(row["kind"]),
        thickness=float(row["thickness"]),
        mass_kg_m2=float(row["mass_kg_m2"]),
        Fy=float(row["Fy"]),
        E_GPa=float(row["E_GPa"]),
      )
      for row in rows
    )

  def list_board_catalog(self) -> tuple[BoardCatalogItem, ...]:
    query = """
      SELECT kind, thickness, mass_kg_m2, Fy, E_GPa
      FROM board_property
      ORDER BY kind, thickness
    """
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.row_factory = sqlite3.Row
      rows = connection.execute(query).fetchall()
    return tuple(_board_catalog_item_from_mapping(dict(row)) for row in rows)

  def list_studs(self) -> tuple[StudSection, ...]:
    query = """
      SELECT group_name, name, H, B, t, A, cx, cy, Ix, Iy, Sx, Sy, rx, ry, section_class
      FROM stud_section
      ORDER BY group_name, name
    """
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.row_factory = sqlite3.Row
      rows = connection.execute(query).fetchall()
    return tuple(
      StudSection(
        group=str(row["group_name"]),
        name=str(row["name"]),
        H=float(row["H"]),
        B=float(row["B"]),
        t=None if row["t"] is None else float(row["t"]),
        A=float(row["A"]),
        cx=float(row["cx"]),
        cy=float(row["cy"]),
        Ix=float(row["Ix"]),
        Iy=float(row["Iy"]),
        Sx=float(row["Sx"]),
        Sy=float(row["Sy"]),
        rx=float(row["rx"]),
        ry=float(row["ry"]),
        section_class=str(row["section_class"]),
      )
      for row in rows
    )

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

  def _fetch_one(self, query: str, params: tuple[object, ...]) -> sqlite3.Row | None:
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.row_factory = sqlite3.Row
      return connection.execute(query, params).fetchone()


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
    _insert_seed_data(connection, seed_root)
    connection.commit()


def _read_seed_items(seed_dir: Path, filename: str) -> Sequence[Mapping[str, object]]:
  path = seed_dir / filename
  with path.open(encoding="utf-8") as file:
    data = cast(Mapping[str, object], json.load(file))
  return cast(Sequence[Mapping[str, object]], data["items"])


def _drop_tables(connection: sqlite3.Connection) -> None:
  for table in ["stud_method", "bolt_material", "stud_section", "board_property", "metadata"]:
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
      PRIMARY KEY (group_name, name)
    );

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
  connection.execute("DELETE FROM bolt_material")
  connection.execute("DELETE FROM stud_method")

  board_items = _read_seed_items(seed_dir, "board_property.json")
  connection.executemany(
    """
    INSERT INTO board_property (kind, thickness, mass_kg_m2, Fy, E_GPa)
    VALUES (?, ?, ?, ?, ?)
    """,
    [
      (
        str(item["kind"]),
        float(item["thickness"]),
        _nullable_float(item.get("mass_kg_m2")),
        _nullable_float(item.get("Fy")),
        _nullable_float(item.get("E_GPa")),
      )
      for item in board_items
    ],
  )

  stud_items = _read_seed_items(seed_dir, "stud_section.json")
  connection.executemany(
    """
    INSERT INTO stud_section (
      group_name, name, H, B, t, A, cx, cy, Ix, Iy, Sx, Sy, rx, ry, section_class
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

  connection.execute("INSERT INTO metadata (key, value) VALUES (?, ?)", ("schema_version", "1"))
  connection.commit()


def _nullable_float(value: object) -> float | None:
  if value is None:
    return None
  return float(value)


def _board_catalog_item_from_mapping(item: Mapping[str, object]) -> BoardCatalogItem:
  mass = _nullable_float(item.get("mass_kg_m2"))
  fy = _nullable_float(item.get("Fy"))
  elastic_modulus = _nullable_float(item.get("E_GPa"))
  missing_fields = tuple(
    field
    for field, value in [
      ("mass_kg_m2", mass),
      ("Fy", fy),
      ("E_GPa", elastic_modulus),
    ]
    if value is None
  )
  return BoardCatalogItem(
    kind=str(item["kind"]),
    thickness=float(item["thickness"]),
    mass_kg_m2=mass,
    Fy=fy,
    E_GPa=elastic_modulus,
    is_complete=len(missing_fields) == 0,
    missing_fields=missing_fields,
  )
