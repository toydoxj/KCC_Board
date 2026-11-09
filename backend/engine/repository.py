"""자재 Repository 구현체."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence, cast

from backend.engine.constants import BOARD_YIELD_RATIO_BY_BOARD, BOARD_YIELD_RATIO_FROM_FRACTURE
from backend.engine.models import AnchorLoadRow, AnchorProduct, AnchorSeismicCap


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
  # 2026-10-24: 휨시험 시트 1~4 두께 입력 15 → 12.5 mm 정정 후 5개 시험체 평균(종전 3.49)
  ("고강도일반", 12.5): 6.06,
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


SCHEMA_VERSION = "10"
STUD_STEEL_SEED_FILE = "stud_steel.json"
# 시험 시편 구성은 stud_method.json의 tested_configurations에 등재한다(2차 심사의견 A-1·F-2)
STUD_METHOD_SEED_FILE = "stud_method.json"
# 런너 고정 앵커 제품 허용하중 DB(schema 9). 최상위 seismic_shear_cap_N은 metadata 테이블에 저장한다
ANCHOR_PRODUCT_SEED_FILE = "anchor_product.json"
ANCHOR_CAP_METADATA_KEY = "anchor_seismic_shear_cap_N"
ANCHOR_CAP_NOTE_METADATA_KEY = "anchor_seismic_shear_cap_note"
# schema 10: 상한 적용 대상 제품군(JSON 배열 문자열, 예 '["dx", "gx"]'). 2026-11-09 결정 2
ANCHOR_CAP_FAMILIES_METADATA_KEY = "anchor_seismic_shear_cap_families"


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
class SpecimenConfiguration:
  """KCC 시험 시편 구성(시험 높이 test_height_mm). 보드는 (종류, 두께) 목록, 스터드측 → 바깥쪽."""

  specimen_no: int
  specimen_id: str
  stud_type: str
  stud_spec: str
  method: str | None
  spacing_mm: float
  front_boards: tuple[tuple[str, float], ...]
  rear_boards: tuple[tuple[str, float], ...]
  test_height_mm: float


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

  def list_specimen_configurations(self) -> tuple[SpecimenConfiguration, ...]:
    """KCC 시험 시편 구성 목록을 조회한다(시험 구성 대조용)."""

  def list_bolt_materials(self) -> tuple[BoltMaterial, ...]:
    """볼트 재질 목록을 조회한다."""

  def list_stud_steels(self) -> tuple[StudSteel, ...]:
    """스터드 강재 목록을 조회한다."""

  def list_anchor_products(self) -> tuple[AnchorProduct, ...]:
    """런너 고정 앵커 제품 목록(허용하중 표 포함)을 조회한다."""

  def get_anchor_product(self, anchor_id: str) -> AnchorProduct:
    """런너 고정 앵커 제품 1건을 조회한다. 미등재이면 RepositoryLookupError."""

  def get_anchor_seismic_cap(self) -> AnchorSeismicCap:
    """내진 시 앵커 허용 전단 상한(N/개)과 근거 문구를 조회한다."""


class JsonSeedRepository:
  def __init__(self, seed_dir: Path | str = Path("data/seed")) -> None:
    self.seed_dir = Path(seed_dir)
    self._board_catalog = self._load_board_catalog()
    self._boards = self._load_boards()
    self._steels = _stud_steels_from_items(self._read_items(STUD_STEEL_SEED_FILE))
    self._studs = self._load_studs()
    self._stud_methods = self._load_stud_methods()
    self._specimens = _specimen_configurations_from_seed(self.seed_dir)
    self._bolts = self._load_bolts()
    self._anchor_products, self._anchor_cap = _anchor_catalog_from_seed(self.seed_dir)

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

  def list_specimen_configurations(self) -> tuple[SpecimenConfiguration, ...]:
    return self._specimens

  def list_bolt_materials(self) -> tuple[BoltMaterial, ...]:
    return tuple(sorted(self._bolts.values(), key=lambda bolt: bolt.material))

  def list_stud_steels(self) -> tuple[StudSteel, ...]:
    return tuple(sorted(self._steels.values(), key=lambda steel: steel.steel_grade))

  def list_anchor_products(self) -> tuple[AnchorProduct, ...]:
    # 시드 등재 순서를 유지한다(UI 선택지 순서 = 시드 순서)
    return tuple(self._anchor_products.values())

  def get_anchor_product(self, anchor_id: str) -> AnchorProduct:
    try:
      return self._anchor_products[anchor_id]
    except KeyError as exc:
      raise RepositoryLookupError(f"등록되지 않은 런너 고정 앵커 제품입니다: {anchor_id}") from exc

  def get_anchor_seismic_cap(self) -> AnchorSeismicCap:
    return self._anchor_cap

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
    self._anchor_cache: dict[str, AnchorProduct] | None = None

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

  def list_specimen_configurations(self) -> tuple[SpecimenConfiguration, ...]:
    with closing(sqlite3.connect(self.db_path)) as connection:
      if not _table_columns(connection, "specimen_configuration"):
        rows: list[tuple[str]] = []
      else:
        rows = connection.execute("SELECT payload FROM specimen_configuration ORDER BY specimen_no").fetchall()
    if not rows:
      raise RepositoryLookupError("자재 DB에 시험 시편 구성이 없습니다. init_db를 다시 실행하십시오.")
    return tuple(_specimen_from_mapping(cast(Mapping[str, object], json.loads(row[0]))) for row in rows)

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

  def list_anchor_products(self) -> tuple[AnchorProduct, ...]:
    return tuple(self._anchor_products().values())

  def get_anchor_product(self, anchor_id: str) -> AnchorProduct:
    try:
      return self._anchor_products()[anchor_id]
    except KeyError as exc:
      raise RepositoryLookupError(f"등록되지 않은 런너 고정 앵커 제품입니다: {anchor_id}") from exc

  def get_anchor_seismic_cap(self) -> AnchorSeismicCap:
    with closing(sqlite3.connect(self.db_path)) as connection:
      rows = dict(
        connection.execute(
          "SELECT key, value FROM metadata WHERE key IN (?, ?, ?)",
          (ANCHOR_CAP_METADATA_KEY, ANCHOR_CAP_NOTE_METADATA_KEY, ANCHOR_CAP_FAMILIES_METADATA_KEY),
        ).fetchall()
      )
    if ANCHOR_CAP_METADATA_KEY not in rows:
      raise RepositoryLookupError("자재 DB에 앵커 내진 전단 상한(anchor_seismic_shear_cap_N)이 없습니다. init_db를 다시 실행하십시오.")
    if ANCHOR_CAP_FAMILIES_METADATA_KEY not in rows:
      raise RepositoryLookupError(
        "자재 DB에 앵커 내진 전단 상한 적용 대상(anchor_seismic_shear_cap_families)이 없습니다. init_db를 다시 실행하십시오."
      )
    return AnchorSeismicCap(
      cap_N=float(rows[ANCHOR_CAP_METADATA_KEY]),
      note=str(rows.get(ANCHOR_CAP_NOTE_METADATA_KEY, "")),
      families=_anchor_cap_families_from_json(str(rows[ANCHOR_CAP_FAMILIES_METADATA_KEY])),
    )

  def _anchor_products(self) -> dict[str, AnchorProduct]:
    if self._anchor_cache is not None:
      return self._anchor_cache
    with closing(sqlite3.connect(self.db_path)) as connection:
      if not _table_columns(connection, "anchor_product"):
        raise RepositoryLookupError("자재 DB에 런너 고정 앵커 제품(anchor_product)이 없습니다. init_db를 다시 실행하십시오.")
      products = _anchor_products_from_connection(connection)
    if not products:
      raise RepositoryLookupError("자재 DB의 런너 고정 앵커 제품 표가 비어 있습니다. init_db를 다시 실행하십시오.")
    self._anchor_cache = products
    return products

  def _fetch_one(self, query: str, params: tuple[object, ...]) -> sqlite3.Row | None:
    with closing(sqlite3.connect(self.db_path)) as connection:
      connection.row_factory = sqlite3.Row
      return connection.execute(query, params).fetchone()

  def _ensure_board_property_rules(self) -> None:
    """구 DB를 현재 규칙(schema 10)으로 이관한다. 한 트랜잭션으로 처리하며 실패하면 되돌린다."""
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
    _migrate_specimen_configuration(connection, self.seed_dir)
    _migrate_anchor_product(connection, self.seed_dir)
    _migrate_anchor_cap_families(connection, self.seed_dir)
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
  for table in [
    "anchor_load_row", "anchor_product",
    "specimen_configuration", "stud_method", "bolt_material", "stud_section", "stud_steel", "board_property", "metadata",
  ]:
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
    + _SPECIMEN_TABLE_SQL
    + ";"
    + _ANCHOR_TABLES_SQL
  )


def _insert_seed_data(connection: sqlite3.Connection, seed_dir: Path) -> None:
  connection.execute("DELETE FROM metadata")
  connection.execute("DELETE FROM board_property")
  connection.execute("DELETE FROM stud_section")
  connection.execute("DELETE FROM stud_steel")
  connection.execute("DELETE FROM bolt_material")
  connection.execute("DELETE FROM stud_method")
  connection.execute("DELETE FROM anchor_load_row")
  connection.execute("DELETE FROM anchor_product")

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

  connection.execute("DELETE FROM specimen_configuration")
  _insert_specimen_configurations(connection, _specimen_configurations_from_seed(seed_dir))

  anchor_products, anchor_cap = _anchor_catalog_from_seed(seed_dir)
  _insert_anchor_products(connection, anchor_products.values(), anchor_cap)

  connection.execute("INSERT INTO metadata (key, value) VALUES (?, ?)", ("schema_version", SCHEMA_VERSION))
  connection.commit()


# ---------------------------------------------------------------------------
# 런너 고정 앵커 제품 DB(schema 9, 상한 적용 대상 제품군은 schema 10)
# ---------------------------------------------------------------------------

_ANCHOR_TABLES_SQL = """
    CREATE TABLE IF NOT EXISTS anchor_product (
      anchor_id TEXT PRIMARY KEY,
      seq INTEGER NOT NULL,
      maker TEXT NOT NULL,
      product TEXT NOT NULL,
      family TEXT NOT NULL,
      family_label TEXT NOT NULL,
      shank_diameter_mm REAL,
      basis TEXT NOT NULL,
      basis_label TEXT NOT NULL,
      concrete_condition TEXT NOT NULL,
      min_concrete_thickness_mm REAL,
      min_edge_mm REAL,
      min_spacing_mm REAL,
      min_fasteners_per_unit REAL,
      approvals TEXT NOT NULL,
      source TEXT NOT NULL,
      is_default INTEGER NOT NULL,
      default_embedment_mm REAL
    );

    CREATE TABLE IF NOT EXISTS anchor_load_row (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      anchor_id TEXT NOT NULL REFERENCES anchor_product(anchor_id),
      embedment_mm REAL NOT NULL,
      concrete_fc_MPa REAL,
      allowable_shear_N REAL NOT NULL,
      allowable_tension_N REAL NOT NULL,
      label TEXT
    );
"""


def _anchor_catalog_from_seed(seed_dir: Path) -> tuple[dict[str, AnchorProduct], AnchorSeismicCap]:
  path = seed_dir / ANCHOR_PRODUCT_SEED_FILE
  with path.open(encoding="utf-8") as file:
    data = cast(Mapping[str, object], json.load(file))
  cap_value = data.get("seismic_shear_cap_N")
  if cap_value is None:
    raise RepositoryLookupError(f"{ANCHOR_PRODUCT_SEED_FILE}에 seismic_shear_cap_N이 없습니다.")
  cap = AnchorSeismicCap(
    cap_N=float(cast(float, cap_value)),
    note=str(data.get("seismic_shear_cap_note", "")),
    families=_anchor_cap_families_from_seed(data),
  )
  items = cast(Sequence[Mapping[str, object]], data["items"])
  return _anchor_products_from_items(items), cap


def _anchor_cap_families_from_seed(data: Mapping[str, object]) -> tuple[str, ...]:
  """최상위 seismic_shear_cap_families(비어 있지 않은 문자열 배열). 없거나 비면 명시적 오류(silent 전체 적용 금지)."""
  raw = data.get("seismic_shear_cap_families")
  if not isinstance(raw, list) or not raw or not all(isinstance(item, str) and item for item in raw):
    raise RepositoryLookupError(f"{ANCHOR_PRODUCT_SEED_FILE}에 seismic_shear_cap_families(비어 있지 않은 문자열 배열)가 없습니다.")
  return tuple(cast(list[str], raw))


def _anchor_cap_families_from_json(value: str) -> tuple[str, ...]:
  try:
    parsed = json.loads(value)
  except json.JSONDecodeError as exc:
    raise RepositoryLookupError(f"자재 DB의 anchor_seismic_shear_cap_families 값이 JSON 배열이 아닙니다: {value!r}") from exc
  if not isinstance(parsed, list) or not parsed or not all(isinstance(item, str) and item for item in parsed):
    raise RepositoryLookupError(f"자재 DB의 anchor_seismic_shear_cap_families 값이 올바르지 않습니다: {value!r}")
  return tuple(cast(list[str], parsed))


def _anchor_products_from_items(items: Sequence[Mapping[str, object]]) -> dict[str, AnchorProduct]:
  products: dict[str, AnchorProduct] = {}
  for item in items:
    product = _anchor_product_from_mapping(item)
    if product.anchor_id in products:
      raise RepositoryLookupError(f"런너 고정 앵커 제품 식별자가 중복되었습니다: {product.anchor_id}")
    products[product.anchor_id] = product
  _default_anchor_id(products)
  return products


def _default_anchor_id(products: Mapping[str, AnchorProduct]) -> str:
  defaults = [product.anchor_id for product in products.values() if product.is_default]
  if len(defaults) != 1:
    raise RepositoryLookupError(f"기본 런너 고정 앵커 제품은 정확히 1개여야 합니다(현재 {len(defaults)}개).")
  return defaults[0]


def _anchor_product_from_mapping(item: Mapping[str, object]) -> AnchorProduct:
  rows = tuple(_anchor_row_from_mapping(row) for row in cast(Sequence[Mapping[str, object]], item.get("table", ())))
  seen: set[tuple[float, float | None]] = set()
  for row in rows:
    key = (row.embedment_mm, row.concrete_fc_MPa)
    if key in seen:
      raise RepositoryLookupError(f"런너 고정 앵커 제품 {item['anchor_id']}의 허용하중 표에 동일 (hET, f'c) 행이 중복됩니다: {key}")
    seen.add(key)
  return AnchorProduct(
    anchor_id=str(item["anchor_id"]),
    maker=str(item["maker"]),
    product=str(item["product"]),
    family=str(item["family"]),
    family_label=str(item["family_label"]),
    shank_diameter_mm=_nullable_float(item.get("shank_diameter_mm")),
    basis=str(item["basis"]),
    basis_label=str(item["basis_label"]),
    concrete_condition=str(item["concrete_condition"]),
    min_concrete_thickness_mm=_nullable_float(item.get("min_concrete_thickness_mm")),
    min_edge_mm=_nullable_float(item.get("min_edge_mm")),
    min_spacing_mm=_nullable_float(item.get("min_spacing_mm")),
    min_fasteners_per_unit=_nullable_float(item.get("min_fasteners_per_unit")),
    approvals=str(item["approvals"]),
    source=str(item["source"]),
    is_default=bool(item["is_default"]),
    default_embedment_mm=_nullable_float(item.get("default_embedment_mm")),
    table=rows,
  )


def _anchor_row_from_mapping(row: Mapping[str, object]) -> AnchorLoadRow:
  shear = float(cast(float, row["allowable_shear_N"]))
  tension = float(cast(float, row["allowable_tension_N"]))
  if shear <= 0.0 or tension <= 0.0:
    raise RepositoryLookupError(f"앵커 허용하중은 양수여야 합니다: 전단 {shear}, 인장 {tension}")
  return AnchorLoadRow(
    embedment_mm=float(cast(float, row["embedment_mm"])),
    concrete_fc_MPa=_nullable_float(row.get("concrete_fc_MPa")),
    allowable_shear_N=shear,
    allowable_tension_N=tension,
    label=None if row.get("label") is None else str(row["label"]),
  )


def _insert_anchor_products(
  connection: sqlite3.Connection,
  products: Iterable[AnchorProduct],
  cap: AnchorSeismicCap,
) -> None:
  product_list = list(products)
  connection.executemany(
    """
    INSERT INTO anchor_product (
      anchor_id, seq, maker, product, family, family_label, shank_diameter_mm, basis, basis_label, concrete_condition,
      min_concrete_thickness_mm, min_edge_mm, min_spacing_mm, min_fasteners_per_unit, approvals, source, is_default,
      default_embedment_mm
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    [
      (
        p.anchor_id, seq, p.maker, p.product, p.family, p.family_label, p.shank_diameter_mm, p.basis, p.basis_label,
        p.concrete_condition, p.min_concrete_thickness_mm, p.min_edge_mm, p.min_spacing_mm, p.min_fasteners_per_unit,
        p.approvals, p.source, int(p.is_default), p.default_embedment_mm,
      )
      for seq, p in enumerate(product_list)
    ],
  )
  connection.executemany(
    """
    INSERT INTO anchor_load_row (anchor_id, embedment_mm, concrete_fc_MPa, allowable_shear_N, allowable_tension_N, label)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
    [
      (p.anchor_id, row.embedment_mm, row.concrete_fc_MPa, row.allowable_shear_N, row.allowable_tension_N, row.label)
      for p in product_list
      for row in p.table
    ],
  )
  connection.executemany(
    "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
    [
      (ANCHOR_CAP_METADATA_KEY, repr(cap.cap_N)),
      (ANCHOR_CAP_NOTE_METADATA_KEY, cap.note),
      (ANCHOR_CAP_FAMILIES_METADATA_KEY, json.dumps(list(cap.families))),
    ],
  )


def _anchor_products_from_connection(connection: sqlite3.Connection) -> dict[str, AnchorProduct]:
  connection.row_factory = sqlite3.Row
  product_rows = connection.execute("SELECT * FROM anchor_product ORDER BY seq").fetchall()
  load_rows = connection.execute(
    "SELECT anchor_id, embedment_mm, concrete_fc_MPa, allowable_shear_N, allowable_tension_N, label "
    "FROM anchor_load_row ORDER BY id"
  ).fetchall()
  rows_by_id: dict[str, list[dict[str, object]]] = {}
  for row in load_rows:
    rows_by_id.setdefault(str(row["anchor_id"]), []).append(dict(row))
  items = [{**dict(row), "is_default": bool(row["is_default"]), "table": rows_by_id.get(str(row["anchor_id"]), [])} for row in product_rows]
  return _anchor_products_from_items(items)


def _migrate_anchor_product(connection: sqlite3.Connection, seed_dir: Path | None) -> None:
  """schema 8 이하 DB에 런너 고정 앵커 제품 테이블을 추가한다.

  seed 경로가 없으면 채울 수 없으므로 명시적 오류로 중단한다(트랜잭션 롤백, schema 버전 유지).
  executescript()는 진행 중인 트랜잭션을 먼저 커밋하므로 쓰지 않는다 — DDL을 문장별 execute()로 실행해
  실패 시 테이블 생성까지 함께 롤백되게 한다.
  """
  for statement in _sql_statements(_ANCHOR_TABLES_SQL):
    connection.execute(statement)
  if connection.execute("SELECT COUNT(*) FROM anchor_product").fetchone()[0] > 0:
    return
  if seed_dir is None:
    raise RepositoryLookupError(
      "구 자재 DB에 런너 고정 앵커 제품(anchor_product)이 없습니다. seed 경로를 지정하거나 init_db를 다시 실행하십시오."
    )
  products, cap = _anchor_catalog_from_seed(seed_dir)
  _insert_anchor_products(connection, products.values(), cap)


def _migrate_anchor_cap_families(connection: sqlite3.Connection, seed_dir: Path | None) -> None:
  """schema 9 DB에 내진 상한 적용 대상 제품군(metadata anchor_seismic_shear_cap_families)과 갱신된 상한 note를 채운다(schema 10).

  seed 경로가 없으면 채울 수 없으므로 명시적 오류로 중단한다(트랜잭션 롤백, schema 버전 유지).
  """
  exists = connection.execute(
    "SELECT COUNT(*) FROM metadata WHERE key = ?", (ANCHOR_CAP_FAMILIES_METADATA_KEY,)
  ).fetchone()[0]
  if exists:
    return
  if seed_dir is None:
    raise RepositoryLookupError(
      "구 자재 DB에 앵커 내진 전단 상한 적용 대상(anchor_seismic_shear_cap_families)이 없습니다. "
      "seed 경로를 지정하거나 init_db를 다시 실행하십시오."
    )
  _, cap = _anchor_catalog_from_seed(seed_dir)
  connection.executemany(
    "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
    [
      (ANCHOR_CAP_NOTE_METADATA_KEY, cap.note),
      (ANCHOR_CAP_FAMILIES_METADATA_KEY, json.dumps(list(cap.families))),
    ],
  )


def _sql_statements(script: str) -> list[str]:
  """세미콜론으로 구분된 DDL 스크립트를 개별 문장으로 나눈다(문자열 리터럴 없는 스키마 DDL 전용)."""
  return [statement.strip() for statement in script.split(";") if statement.strip()]


_SPECIMEN_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS specimen_configuration (
      specimen_no INTEGER PRIMARY KEY,
      payload TEXT NOT NULL
    )
"""


def _specimen_configurations_from_seed(seed_dir: Path) -> tuple[SpecimenConfiguration, ...]:
  path = seed_dir / STUD_METHOD_SEED_FILE
  with path.open(encoding="utf-8") as file:
    data = cast(Mapping[str, object], json.load(file))
  raw = data.get("tested_configurations")
  if not isinstance(raw, list) or not raw:
    raise RepositoryLookupError(f"{STUD_METHOD_SEED_FILE}에 시험 시편 구성(tested_configurations)이 없습니다.")
  height = float(cast(float, data["tested_height_mm"]))
  return tuple(
    _specimen_from_mapping({**cast(Mapping[str, object], item), "test_height_mm": height}) for item in raw
  )


def _specimen_from_mapping(item: Mapping[str, object]) -> SpecimenConfiguration:
  def boards(key: str) -> tuple[tuple[str, float], ...]:
    return tuple(
      (str(board["kind"]), float(cast(float, board["thickness"])))
      for board in cast(Sequence[Mapping[str, object]], item[key])
    )

  return SpecimenConfiguration(
    specimen_no=int(cast(int, item["specimen_no"])),
    specimen_id=str(item["specimen_id"]),
    stud_type=str(item["stud_type"]),
    stud_spec=str(item["stud_spec"]),
    method=None if item.get("method") is None else str(item["method"]),
    spacing_mm=float(cast(float, item["spacing_mm"])),
    front_boards=boards("front_boards"),
    rear_boards=boards("rear_boards"),
    test_height_mm=float(cast(float, item["test_height_mm"])),
  )


def _specimen_to_mapping(specimen: SpecimenConfiguration) -> dict[str, object]:
  return {
    "specimen_no": specimen.specimen_no,
    "specimen_id": specimen.specimen_id,
    "stud_type": specimen.stud_type,
    "stud_spec": specimen.stud_spec,
    "method": specimen.method,
    "spacing_mm": specimen.spacing_mm,
    "front_boards": [{"kind": kind, "thickness": thickness} for kind, thickness in specimen.front_boards],
    "rear_boards": [{"kind": kind, "thickness": thickness} for kind, thickness in specimen.rear_boards],
    "test_height_mm": specimen.test_height_mm,
  }


def _insert_specimen_configurations(
  connection: sqlite3.Connection,
  specimens: Iterable[SpecimenConfiguration],
) -> None:
  connection.executemany(
    "INSERT INTO specimen_configuration (specimen_no, payload) VALUES (?, ?)",
    [(specimen.specimen_no, json.dumps(_specimen_to_mapping(specimen), ensure_ascii=False)) for specimen in specimens],
  )


def _migrate_specimen_configuration(connection: sqlite3.Connection, seed_dir: Path | None) -> None:
  """schema 7 이하 DB에 시험 시편 구성 테이블을 추가한다(2차 심사의견 A-1).

  seed 경로가 없으면 채울 수 없으므로 명시적 오류로 중단한다(트랜잭션 롤백, schema 버전 유지).
  """
  connection.execute(_SPECIMEN_TABLE_SQL)
  if connection.execute("SELECT COUNT(*) FROM specimen_configuration").fetchone()[0] > 0:
    return
  if seed_dir is None:
    raise RepositoryLookupError(
      "구 자재 DB에 시험 시편 구성(specimen_configuration)이 없습니다. seed 경로를 지정하거나 init_db를 다시 실행하십시오."
    )
  _insert_specimen_configurations(connection, _specimen_configurations_from_seed(seed_dir))


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
