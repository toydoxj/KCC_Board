"""앵커 제품 DB 도입(v0.9.0)·기본 매입깊이 확정(v0.9.3)의 판정 영향 고정 테스트.

v0.9.0에서 기본 제품(hilti_x_u)의 기본 매입깊이가 22 mm(300 N)여서 화면 기본 허용내력이 0.4 → 0.3 kN/개로 바뀌었다.
2026-11-09 사용자 확정(결정 1)으로 기본 매입깊이를 27 mm(400 N)로 두어 기본 경로의 허용내력이 v0.8.0 기본값 0.4 kN/개와
같아졌다. 11개 시편(requested_shape_cases.json)의 내진 anchor_max_height_mm를 두 경로(0.4 / 0.3 kN)로 고정해
의도하지 않은 추가 변동을 막는다. 엔진 자체는 변경이 없으므로 0.4 kN 열은 v0.8.0 결과와 같아야 한다.
표는 docs/anchor_product_db_changes.md §2와 일치한다.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from backend.engine.anchor import resolve_request_anchor
from backend.engine.calculator import bolt_values_from_ply_order, calculate_wall_check
from backend.engine.models import BoardLayer, BoltInput, SeismicInput, StudInput, WallCheckRequest
from backend.engine.repository import JsonSeedRepository

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data/seed"
CASES = ROOT / "tests/golden/requested_shape_cases.json"

# v0.8.0 기본값(0.4 kN 직접 입력) = 확정 기본 경로(hilti_x_u, hET 27 → 400 N)
LEGACY_DEFAULT_CAPACITY_KN = 0.4
# 기본 제품의 확정 기본 매입깊이(mm)와 종전(v0.9.0~0.9.2) 기본 매입깊이
CONFIRMED_DEFAULT_EMBEDMENT_MM = 27.0
PREVIOUS_DEFAULT_EMBEDMENT_MM = 22.0
PREVIOUS_DEFAULT_CAPACITY_KN = 0.3

# (시편 id, anchorH@0.4 kN(v0.8.0 기본 = hET 27 확정 기본), anchorH@0.3 kN(hET 22)) — 고정못 간격 450 mm
EXPECTED_ANCHOR_HEIGHT_MM = {
  "requested_01_c_stud_central_joint": (2600.0, 1950.0),
  "requested_02_c_stud_basic_front_only": (4100.0, 3050.0),
  "requested_03_c_stud_butt_joint": (2600.0, 1950.0),
  "requested_04_c_stud_basic": (2650.0, 2000.0),
  "requested_05_ch_stud_75": (2800.0, 2100.0),
  "requested_06_hr_stud_124": (2650.0, 1950.0),
  "requested_07_mp_stud_74": (2650.0, 2000.0),
  "requested_08_rv_stud_74": (2650.0, 2000.0),
  "requested_09_t_silent_stud_74": (2650.0, 2000.0),
  "requested_10_r_stud_75": (2650.0, 2000.0),
  "requested_11_i_stud_75": (2800.0, 2100.0),
}


def _boards(raw) -> tuple[BoardLayer, ...]:
  return tuple(
    BoardLayer(kind=str(b["kind"]), thickness=float(b["thickness"]), order=None if b.get("order") is None else int(b["order"]))
    for b in raw
  )


def _request(common, case) -> WallCheckRequest:
  inp = case["input"]
  bolt = common["bolt"]
  seismic = common["seismic"]
  return WallCheckRequest(
    rear_boards=_boards(inp["rear_boards"]),
    front_boards=_boards(inp["front_boards"]),
    stud=StudInput(stud_type=str(inp["stud_type"]), spec=str(inp["stud_spec"]), method=None if inp.get("method") is None else str(inp["method"])),
    horizontal_load_kg_m2=float(common["horizontal_load_kg_m2"]),
    live_load_kN_m2=float(common["live_load_kN_m2"]),
    vertical_load_kN_m=float(common["vertical_load_kN_m"]),
    spacing_mm=float(inp["spacing_mm"]),
    span_mm=float(common["span_for_ieff_mm"]),
    deflection_limit_denom=int(common["deflection_limit_denom"]),
    bolt=BoltInput(
      diameter=float(bolt["diameter"]),
      yield_strength=float(bolt["yield_strength"]),
      pitch=bolt_values_from_ply_order(tuple(float(v) for v in bolt["pitch"])),
      count=bolt_values_from_ply_order(tuple(float(v) for v in bolt["count"])),
    ),
    seismic=SeismicInput(S=float(seismic["S"]), Ip=float(seismic["Ip"]), Fa=float(seismic["Fa"])),
    design_case="seismic",
    strength_check_mode=str(common["strength_check_mode"]),
    omega=float(common["omega"]),
    anchor_capacity_kN=float(common["anchor_capacity_kN"]),
    anchor_spacing_mm=450.0,
  )


class AnchorHeightImpactTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.repo = JsonSeedRepository(SEED_DIR)
    cls.default_product = next(p for p in cls.repo.list_anchor_products() if p.is_default)
    data = json.loads(CASES.read_text(encoding="utf-8"))
    cls.requests = {case["id"]: _request(data["common"], case) for case in data["cases"]}

  def _with_default_product(self, case_id: str, embedment_mm: float) -> WallCheckRequest:
    return replace(
      self.requests[case_id],
      anchor_product_id=self.default_product.anchor_id,
      anchor_embedment_mm=embedment_mm,
      anchor_concrete_fc_MPa=None,
      anchor_apply_seismic_cap=True,
    )

  def test_all_specimens_are_covered(self) -> None:
    self.assertEqual(set(self.requests), set(EXPECTED_ANCHOR_HEIGHT_MM))

  def test_default_product_and_embedment_are_confirmed_values(self) -> None:
    # 결정 1(2026-11-09): 기본 제품 Hilti X-U P8, 기본 매입깊이 27 mm → 400 N
    self.assertEqual(self.default_product.anchor_id, "hilti_x_u")
    self.assertEqual(self.default_product.default_embedment_mm, CONFIRMED_DEFAULT_EMBEDMENT_MM)

  def test_legacy_default_0_4_kN_is_unchanged(self) -> None:
    for case_id, (before, _after) in EXPECTED_ANCHOR_HEIGHT_MM.items():
      with self.subTest(case=case_id):
        result = calculate_wall_check(replace(self.requests[case_id], anchor_capacity_kN=LEGACY_DEFAULT_CAPACITY_KN), self.repo)
        self.assertEqual(result.anchor_max_height_mm, before)

  def test_default_product_default_embedment_matches_legacy_0_4_kN(self) -> None:
    # 기본 제품·기본 매입(hET 27)에서 자동 입력 0.4 kN → anchorHeight가 v0.8.0 기본값(0.4 kN 직접 입력)과 동일
    for case_id, (legacy, _previous) in EXPECTED_ANCHOR_HEIGHT_MM.items():
      with self.subTest(case=case_id):
        resolved, anchor = resolve_request_anchor(
          self._with_default_product(case_id, float(self.default_product.default_embedment_mm or 0.0)), self.repo
        )
        self.assertIsNotNone(anchor)
        assert anchor is not None
        self.assertAlmostEqual(resolved.anchor_capacity_kN, LEGACY_DEFAULT_CAPACITY_KN)
        self.assertFalse(anchor.cap_applied)
        result = calculate_wall_check(resolved, self.repo)
        legacy_result = calculate_wall_check(replace(self.requests[case_id], anchor_capacity_kN=LEGACY_DEFAULT_CAPACITY_KN), self.repo)
        self.assertEqual(result.anchor_max_height_mm, legacy)
        self.assertEqual(result.anchor_max_height_mm, legacy_result.anchor_max_height_mm)
        self.assertEqual(result.intermediate["anchor_utilization"], legacy_result.intermediate["anchor_utilization"])

  def test_default_product_hET_22_resolves_to_0_3_kN_and_lowers_anchor_height(self) -> None:
    # 종전(v0.9.0~0.9.2) 기본 매입 22 mm 경로 보존: 300 N → anchorHeight 약 25% 감소
    for case_id, (before, after) in EXPECTED_ANCHOR_HEIGHT_MM.items():
      with self.subTest(case=case_id):
        resolved, anchor = resolve_request_anchor(self._with_default_product(case_id, PREVIOUS_DEFAULT_EMBEDMENT_MM), self.repo)
        self.assertIsNotNone(anchor)
        self.assertAlmostEqual(resolved.anchor_capacity_kN, PREVIOUS_DEFAULT_CAPACITY_KN)
        result = calculate_wall_check(resolved, self.repo)
        self.assertEqual(result.anchor_max_height_mm, after)
        self.assertLess(after, before)

  def test_other_verdict_paths_do_not_move_with_anchor_capacity(self) -> None:
    # 앵커 허용내력은 런너 고정못 경로에만 영향한다 — 응력·처짐·max_height는 동일해야 한다
    for case_id in EXPECTED_ANCHOR_HEIGHT_MM:
      with self.subTest(case=case_id):
        a = calculate_wall_check(replace(self.requests[case_id], anchor_capacity_kN=LEGACY_DEFAULT_CAPACITY_KN), self.repo)
        b = calculate_wall_check(replace(self.requests[case_id], anchor_capacity_kN=PREVIOUS_DEFAULT_CAPACITY_KN), self.repo)
        self.assertEqual(a.max_height_mm, b.max_height_mm)
        self.assertEqual(a.stress_ratio, b.stress_ratio)
        self.assertEqual(a.deflection_mm, b.deflection_mm)


if __name__ == "__main__":
  unittest.main()
