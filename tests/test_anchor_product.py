"""런너 고정 앵커 제품 시드(data/seed/anchor_product.json) 무결성 테스트."""

from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence, cast


ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "data/seed/anchor_product.json"

REQUIRED_TOP_KEYS = ("_source", "_unit", "_note", "_status", "seismic_shear_cap_N", "seismic_shear_cap_note", "items")
REQUIRED_ITEM_KEYS = (
  "anchor_id", "maker", "product", "family", "family_label", "shank_diameter_mm", "basis", "basis_label",
  "concrete_condition", "min_concrete_thickness_mm", "min_edge_mm", "min_spacing_mm", "min_fasteners_per_unit",
  "approvals", "source", "is_default", "default_embedment_mm", "table",
)
REQUIRED_ROW_KEYS = ("embedment_mm", "concrete_fc_MPa", "allowable_shear_N", "allowable_tension_N")
FAMILIES = {"dx", "gx", "screw", "custom"}
BASES = {"rec", "asd", "user"}
CUSTOM_FAMILY = "custom"


class AnchorProductSeedTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    with SEED_PATH.open(encoding="utf-8") as file:
      cls.data = cast(Mapping[str, object], json.load(file))
    cls.items = cast(Sequence[Mapping[str, object]], cls.data["items"])

  def test_top_level_keys_and_cap(self) -> None:
    for key in REQUIRED_TOP_KEYS:
      self.assertIn(key, self.data, f"최상위 키 누락: {key}")
    cap = self.data["seismic_shear_cap_N"]
    self.assertIsInstance(cap, (int, float))
    self.assertGreater(cast(float, cap), 0)

  def test_item_keys_and_enums(self) -> None:
    self.assertGreater(len(self.items), 0)
    for item in self.items:
      for key in REQUIRED_ITEM_KEYS:
        self.assertIn(key, item, f"{item.get('anchor_id')}: 항목 키 누락 {key}")
      self.assertIn(item["family"], FAMILIES, f"{item['anchor_id']}: family 값 오류")
      self.assertIn(item["basis"], BASES, f"{item['anchor_id']}: basis 값 오류")
      self.assertIsInstance(item["is_default"], bool)

  def test_exactly_one_default(self) -> None:
    defaults = [str(item["anchor_id"]) for item in self.items if item["is_default"] is True]
    self.assertEqual(len(defaults), 1, f"기본 제품은 정확히 1개여야 한다(현재 {defaults})")
    default_item = next(item for item in self.items if item["is_default"] is True)
    self.assertNotEqual(default_item["family"], CUSTOM_FAMILY, "사용자 정의는 기본 제품이 될 수 없다")

  def test_anchor_id_unique(self) -> None:
    counts = Counter(str(item["anchor_id"]) for item in self.items)
    duplicated = sorted(anchor_id for anchor_id, count in counts.items() if count > 1)
    self.assertEqual(duplicated, [], f"anchor_id 중복: {duplicated}")
    self.assertIn(CUSTOM_FAMILY, counts, "사용자 정의 항목(anchor_id 'custom')이 있어야 한다")

  def test_tables_are_valid(self) -> None:
    for item in self.items:
      anchor_id = str(item["anchor_id"])
      table = cast(Sequence[Mapping[str, object]], item["table"])
      if item["family"] == CUSTOM_FAMILY:
        self.assertEqual(len(table), 0, f"{anchor_id}: 사용자 정의 항목은 표가 비어 있어야 한다")
        self.assertIsNone(item["default_embedment_mm"])
        continue
      self.assertGreaterEqual(len(table), 1, f"{anchor_id}: 허용하중 표가 비어 있다")
      keys = Counter()
      for row in table:
        for key in REQUIRED_ROW_KEYS:
          self.assertIn(key, row, f"{anchor_id}: 표 행 키 누락 {key}")
        self.assertGreater(cast(float, row["embedment_mm"]), 0, f"{anchor_id}: 매입깊이는 양수여야 한다")
        self.assertGreater(cast(float, row["allowable_shear_N"]), 0, f"{anchor_id}: 허용 전단은 양수여야 한다")
        self.assertGreater(cast(float, row["allowable_tension_N"]), 0, f"{anchor_id}: 허용 인장은 양수여야 한다")
        fc = row["concrete_fc_MPa"]
        if fc is not None:
          self.assertGreater(cast(float, fc), 0, f"{anchor_id}: 콘크리트 강도는 양수여야 한다")
        keys[(float(cast(float, row["embedment_mm"])), None if fc is None else float(cast(float, fc)))] += 1
      duplicated = sorted(key for key, count in keys.items() if count > 1)
      self.assertEqual(duplicated, [], f"{anchor_id}: 동일 (매입깊이, 강도) 행 중복 {duplicated}")

  def test_fc_column_consistency_per_product(self) -> None:
    """한 제품 안에서 fc 열은 전부 null(rec)이거나 전부 값(asd)이어야 조회 규칙이 단일해진다."""
    for item in self.items:
      if item["family"] == CUSTOM_FAMILY:
        continue
      table = cast(Sequence[Mapping[str, object]], item["table"])
      has_fc = {row["concrete_fc_MPa"] is not None for row in table}
      self.assertEqual(len(has_fc), 1, f"{item['anchor_id']}: fc 유무가 행마다 다르다")
      if item["basis"] == "rec":
        self.assertEqual(has_fc, {False}, f"{item['anchor_id']}: 권장하중(rec) 제품은 fc 열이 없어야 한다")
      if item["basis"] == "asd":
        self.assertEqual(has_fc, {True}, f"{item['anchor_id']}: ASD 제품은 fc 열이 있어야 한다")

  def test_default_embedment_exists_in_table(self) -> None:
    for item in self.items:
      if item["family"] == CUSTOM_FAMILY:
        continue
      table = cast(Sequence[Mapping[str, object]], item["table"])
      embedments = {float(cast(float, row["embedment_mm"])) for row in table}
      self.assertIsNotNone(item["default_embedment_mm"], f"{item['anchor_id']}: 기본 매입깊이 누락")
      self.assertIn(
        float(cast(float, item["default_embedment_mm"])),
        embedments,
        f"{item['anchor_id']}: 기본 매입깊이 {item['default_embedment_mm']}가 표에 없다",
      )


if __name__ == "__main__":
  unittest.main()
