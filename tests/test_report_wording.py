"""산출 문서 내부 검토 문구 금지 시험 (APP_DEV item 182, 2026-11-26).

소유자 상시 지시: 계산서·요약페이지 등 프로그램이 만드는 문서에 「확인 필요」「미검증」「주의」「WARN」류 문구를 쓰지 않는다.
판정은 계산값 기준(O.K / N.G)이며, 안내 사유는 화면 메시지로 옮긴다.

시험 3단계
1. API 응답 중 계산서에 실리는 문자열(notices, 앵커 카탈로그 출력 필드, anchor_product_summary)
2. 계산서 컴포넌트 소스의 문자열 리터럴(주석 제외)
3. 표준 예제의 실제 렌더링 텍스트 — CalculationReport·SummaryReport 를 react-dom/server 로 렌더링
   (renderer/scripts/report-wording-check.mjs). renderer/node_modules 가 없으면 실패한다
   (환경변수 KCC_ALLOW_SKIP_RENDER=1 일 때만 건너뜀 — 병합 전 시험에서는 반드시 실행).
4. Codex 1차 반영 분기: 피스 체결층 없는 CH(검토 생략 표기), CH 일부 체결(범위 표기), 자유입력 출처 필터,
   엔진 입력 조건 안내(중립축·표준 외 피스 간격), DB 문자열 필터.

금지 문구 패턴 단일 출처: renderer/src/lib/report-wording.ts (reportForbiddenPatternSource, 대소문자 무관).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, cast

from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.engine.calculator import request_from_golden_case
from backend.engine.repository import JsonSeedRepository


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "renderer"
CHECK_SCRIPT = RENDERER / "scripts/report-wording-check.mjs"

WORDING_SOURCE = RENDERER / "src/lib/report-wording.ts"


def _load_forbidden_pattern() -> re.Pattern[str]:
  """renderer/src/lib/report-wording.ts 의 String.raw 패턴 원문을 읽는다(단일 출처)."""
  match = re.search(r"reportForbiddenPatternSource\s*=\s*String\.raw`([^`]+)`", WORDING_SOURCE.read_text(encoding="utf-8"))
  if match is None:
    raise AssertionError(f"{WORDING_SOURCE}: reportForbiddenPatternSource 를 찾을 수 없음")
  return re.compile(match.group(1), re.IGNORECASE)


FORBIDDEN_PATTERN = _load_forbidden_pattern()
FREE_INPUT_FORBIDDEN_SOURCE = "승인번호 확인 필요 / Warning"

# 계산서·요약페이지에 텍스트를 내보내는 렌더러 소스(화면 전용 input-workspace 등은 대상 아님)
REPORT_SOURCES = (
  "renderer/src/components/calculation-report.tsx",
  "renderer/src/components/summary-report.tsx",
  "renderer/src/components/result-notices.tsx",
  "renderer/src/lib/result-notice.ts",
  "renderer/src/components/limitations-dialog.tsx",
)

# 앵커 카탈로그 중 계산서에 출력되는 필드(calculation-report.tsx 부록·검토 조건, anchor.ts anchorSourceText)
ANCHOR_REPORT_FIELDS = ("maker", "product", "basis_label", "source", "approvals", "concrete_condition")

CUSTOM_ANCHOR_ID = "custom"


def _hits(text: str) -> list[str]:
  return FORBIDDEN_PATTERN.findall(text)


def _strip_comments(source: str) -> str:
  """// 줄 주석과 /* */ 블록 주석을 지운다(문자열 안의 // 는 URL 이 없으므로 그대로 둔다)."""
  source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
  source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.S)
  return "\n".join(re.sub(r"(^|\s)//.*$", "", line) for line in source.splitlines())


def _anchor_input(product: Mapping[str, Any]) -> tuple[float, float | None]:
  """제품의 기본 매입깊이 행(없으면 표 첫 행)으로 hET·f'c 를 정한다 — 화면 기본 선택과 같은 규칙."""
  table = cast(list[Mapping[str, Any]], product["table"])
  default = product.get("default_embedment_mm")
  row = next((r for r in table if r["embedment_mm"] == default), table[0])
  return float(row["embedment_mm"]), (None if row["concrete_fc_MPa"] is None else float(row["concrete_fc_MPa"]))


class ReportWordingTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.client = TestClient(create_app(JsonSeedRepository(ROOT / "data/seed")))
    with (ROOT / "tests/golden/cases.json").open(encoding="utf-8") as file:
      data = cast(Mapping[str, object], json.load(file))
    cls.base_payload = asdict(request_from_golden_case(dict(cast(list[Mapping[str, object]], data["cases"])[0])))
    cls.boards = cls._get("/api/db/boards")
    cls.studs = cls._get("/api/db/studs")
    cls.anchors = cast(list[dict[str, Any]], cls._get("/api/db/anchor-products")["items"])
    cls.cases = cls._standard_cases()

  @classmethod
  def _get(cls, path: str) -> Any:
    response = cls.client.get(path)
    if response.status_code != 200:
      raise AssertionError(f"{path}: {response.status_code} {response.text}")
    return response.json()["data"]

  @classmethod
  def _check(cls, payload: Mapping[str, object]) -> dict[str, Any]:
    response = cls.client.post("/api/check", json=dict(payload))
    if response.status_code != 200:
      raise AssertionError(f"/api/check 실패: {response.status_code} {response.text}")
    return cast(dict[str, Any], response.json()["data"])

  @classmethod
  def _standard_cases(cls) -> list[dict[str, Any]]:
    """표준 예제: 내진 × 카탈로그 전 제품, 내진 × 사용자 정의, 비내진(모드 3종)."""
    cases: list[dict[str, Any]] = []
    for product in cls.anchors:
      if product["anchor_id"] == CUSTOM_ANCHOR_ID:
        continue
      embedment, fc = _anchor_input(product)
      payload = {
        **cls.base_payload,
        "design_case": "seismic",
        "anchor_product_id": product["anchor_id"],
        "anchor_embedment_mm": embedment,
        "anchor_concrete_fc_MPa": fc,
        "anchor_apply_seismic_cap": True,
        "anchor_capacity_source": f"{product['source']} ({product['approvals']})"[:200],
      }
      cases.append({"name": f"seismic-{product['anchor_id']}", "mode": "anchorHeight", "payload": payload, "product": product})
    custom = {**cls.base_payload, "design_case": "seismic", "anchor_capacity_kN": 0.4}
    cases.append({"name": "seismic-custom", "mode": "anchorHeight", "payload": custom, "product": None})
    # Codex 1차 반영 분기
    free_input = {**custom, "anchor_capacity_source": FREE_INPUT_FORBIDDEN_SOURCE}
    cases.append({"name": "free-input-source", "mode": "anchorHeight", "payload": free_input, "product": None})
    ch_stud = {"stud_type": "CH-STUD", "spec": "102CHS-08", "method": "기본"}
    rear_slot = [{"kind": "방화", "thickness": 25.0, "order": 1}]
    cases.append({
      "name": "ch-slot-only", "mode": "maxHeight", "product": None,
      "payload": {**cls.base_payload, "stud": ch_stud, "rear_boards": rear_slot, "front_boards": []},
    })
    cases.append({
      "name": "ch-partial", "mode": "maxHeight", "product": None,
      "payload": {**cls.base_payload, "stud": ch_stud, "rear_boards": rear_slot},
    })
    # 로컬 DB에서 고친 카탈로그 문자열(금지 문구 포함)도 인쇄 전에 걸러져야 한다
    x_c = next(product for product in cls.anchors if product["anchor_id"] == "hilti_x_c")
    edited = {**x_c, "approvals": "승인번호 확인 필요", "concrete_condition": "Warning: 원문 대조", "source": x_c["source"]}
    embedment, fc = _anchor_input(x_c)
    cases.append({
      "name": "db-edited-strings", "mode": "anchorHeight", "product": edited,
      "payload": {
        **cls.base_payload, "design_case": "seismic", "anchor_product_id": "hilti_x_c",
        "anchor_embedment_mm": embedment, "anchor_concrete_fc_MPa": fc, "anchor_apply_seismic_cap": True,
        "anchor_capacity_source": f"{edited['source']} ({edited['approvals']})",
      },
    })
    c50_front = {
      **cls.base_payload,
      "stud": {"stud_type": "C-STUD", "spec": "50S-45-08", "method": "기본"},
      "rear_boards": [],
      "front_boards": [{"kind": "방화", "thickness": 19.0, "order": 1}, {"kind": "방화", "thickness": 19.0, "order": 2}],
    }
    bolt = dict(cast(Mapping[str, Any], cls.base_payload["bolt"]))
    pitch = list(cast(list[float], bolt["pitch"]))
    pitch[2] = 450.0
    cases.append({
      "name": "notice-neutral-axis-and-pitch", "mode": "maxHeight", "product": None,
      "payload": {**c50_front, "bolt": {**bolt, "pitch": pitch}},
    })
    for mode in ("maxHeight", "anchorHeight", "heightCheck"):
      payload = {**cls.base_payload, "design_case": "non_seismic"}
      cases.append({"name": f"non_seismic-{mode}", "mode": mode, "payload": payload, "product": None})
    for case in cases:
      case["result"] = cls._check(case["payload"])
    return cases

  # ── 1. API 응답·카탈로그 출력 필드 ──
  def test_api_report_strings_have_no_forbidden_wording(self) -> None:
    for case in self.cases:
      result = case["result"]
      with self.subTest(case=case["name"]):
        texts = [*cast(list[str], result.get("notices") or []), str(result.get("anchor_product_summary") or "")]
        for text in texts:
          self.assertEqual(_hits(text), [], text)

  def test_anchor_catalog_report_fields_have_no_forbidden_wording(self) -> None:
    for product in self.anchors:
      for field in ANCHOR_REPORT_FIELDS:
        with self.subTest(anchor=product["anchor_id"], field=field):
          value = str(product.get(field) or "")
          self.assertEqual(_hits(value), [], value)
      for row in product["table"]:
        self.assertEqual(_hits(str(row.get("label") or "")), [], row)

  # ── 2. 계산서 컴포넌트 소스 문자열 ──
  def test_report_component_sources_have_no_forbidden_wording(self) -> None:
    for relative in REPORT_SOURCES:
      source = _strip_comments((ROOT / relative).read_text(encoding="utf-8"))
      with self.subTest(file=relative):
        lines = [line.strip() for line in source.splitlines() if _hits(line)]
        self.assertEqual(lines, [])

  # ── 3. 실제 렌더링 텍스트 ──
  _render_cache: dict[str, Any] | None = None

  def _render(self) -> dict[str, Any]:
    """전 예제를 한 번 렌더링하고 결과(JSON)를 캐시한다."""
    if ReportWordingTest._render_cache is not None:
      return ReportWordingTest._render_cache
    node = shutil.which("node")
    if node is None or not (RENDERER / "node_modules/react-dom").is_dir() or not (RENDERER / "node_modules/typescript").is_dir():
      message = "node 또는 renderer/node_modules 없음 — `cd renderer; npm ci` 후 다시 실행할 것"
      if os.environ.get("KCC_ALLOW_SKIP_RENDER") == "1":
        self.skipTest(message)
      self.fail(message + " (렌더링 시험은 건너뛰지 않음. 의도적으로 건너뛰려면 KCC_ALLOW_SKIP_RENDER=1)")
    fixtures = [{"name": case["name"], "data": self._report_data(case)} for case in self.cases]
    with tempfile.TemporaryDirectory() as temp_dir:
      fixture_path = Path(temp_dir) / "fixtures.json"
      fixture_path.write_text(json.dumps(fixtures, ensure_ascii=False), encoding="utf-8")
      completed = subprocess.run(
        [node, str(CHECK_SCRIPT), str(fixture_path), "--dump-text"],
        cwd=RENDERER,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
      )
    if completed.returncode == 2 or not completed.stdout.strip():
      self.fail(f"렌더링 실패(exit {completed.returncode}): {completed.stderr[-2000:]}")
    summary = cast(dict[str, Any], json.loads(completed.stdout))
    summary["returncode"] = completed.returncode
    summary["texts"] = {(entry["name"], entry["kind"]): entry["text"] for entry in summary["report"]}
    summary["screen_by_name"] = {entry["name"]: entry for entry in summary["screen"]}
    ReportWordingTest._render_cache = summary
    return summary

  def _text(self, name: str, kind: str) -> str:
    return cast(str, self._render()["texts"][(name, kind)])

  def test_rendered_reports_have_no_forbidden_wording(self) -> None:
    summary = self._render()
    self.assertEqual(len(summary["report"]), 2 * len(self.cases))
    hits = [{k: v for k, v in entry.items() if k != "text"} for entry in summary["report"] if entry["hits"]]
    self.assertEqual(hits, [], json.dumps(hits, ensure_ascii=False, indent=1))
    self.assertEqual(summary["returncode"], 0)

  # ── 4. Codex 1차 반영 분기 ──
  def test_ch_slot_only_screw_tension_is_marked_skipped(self) -> None:
    case = next(c for c in self.cases if c["name"] == "ch-slot-only")
    # 엔진 판정은 그대로(O.K, 수요 0) — 문서 표기만 범위를 붙인다
    self.assertEqual(case["result"]["screw_tension_verdict"], "O.K")
    self.assertEqual(case["result"]["intermediate"]["screw_tension_spacing_mm"], 0.0)
    for kind in ("detail", "summary"):
      text = self._text("ch-slot-only", kind)
      with self.subTest(kind=kind):
        self.assertIn("O.K (피스 인장 검토 생략)", text)
        self.assertIsNone(re.search(r"피스 인장\s+(O\.K|N\.G)(?!\s*\()", text), "범위 표기 없는 피스 인장 판정")
    self.assertNotIn("피스 인장 조건 만족값", self._text("ch-slot-only", "summary"))
    self.assertIn("응력·처짐·런너 고정못 조건 만족값 (피스 인장 검토 생략)", self._text("ch-slot-only", "summary"))

  def test_ch_partial_screw_tension_shows_checked_layers(self) -> None:
    case = next(c for c in self.cases if c["name"] == "ch-partial")
    self.assertGreater(case["result"]["intermediate"]["screw_tension_spacing_mm"], 0.0)
    verdict = case["result"]["screw_tension_verdict"]
    for kind in ("detail", "summary"):
      with self.subTest(kind=kind):
        self.assertIn(f"{verdict} (전면 피스 체결층)", self._text("ch-partial", kind))
    self.assertIn("전면 피스 체결층(후면 CH 끼움 보드는 피스 없음 — 검토 생략)", self._text("ch-partial", "detail"))

  def test_free_input_source_is_filtered_from_documents_and_flagged_on_screen(self) -> None:
    for kind in ("detail", "summary"):
      with self.subTest(kind=kind):
        text = self._text("free-input-source", kind)
        self.assertNotIn("승인번호", text)
        self.assertNotIn("Warning", text)
    # 화면 안내 조건: 같은 함수(isReportSafeText)가 거짓이면 입력 화면에 생략 안내를 띄운다
    self.assertFalse(self._render()["screen_by_name"]["free-input-source"]["anchorSourceReportSafe"])
    self.assertTrue(self._render()["screen_by_name"]["seismic-hilti_x_u"]["anchorSourceReportSafe"])
    screen_source = (RENDERER / "src/components/input-workspace.tsx").read_text(encoding="utf-8")
    self.assertIn("isReportSafeText(values.anchorCapacitySource)", screen_source)
    self.assertIn('reportOmittedTextNotice("허용내력 출처")', screen_source)
    # 원문 보존: API 요청·계산은 입력값 그대로 받는다
    case = next(c for c in self.cases if c["name"] == "free-input-source")
    self.assertEqual(case["payload"]["anchor_capacity_source"], FREE_INPUT_FORBIDDEN_SOURCE)

  def test_db_edited_strings_are_filtered(self) -> None:
    for kind in ("detail", "summary"):
      text = self._text("db-edited-strings", kind)
      with self.subTest(kind=kind):
        self.assertNotIn("승인번호", text)
        self.assertNotIn("원문 대조", text)
        self.assertIn("Hilti X-C", text)

  def test_input_condition_notices_print_facts_only(self) -> None:
    case = next(c for c in self.cases if c["name"] == "notice-neutral-axis-and-pitch")
    notices = cast(list[str], case["result"]["notices"])
    self.assertEqual(len(notices), 2, notices)
    for kind in ("detail", "summary"):
      text = self._text("notice-neutral-axis-and-pitch", kind)
      with self.subTest(kind=kind):
        self.assertIn("중립축", text)
        self.assertIn("피스 간격 450 mm는 표준 간격 600 mm와 다름", text)
        self.assertNotIn("결과 적용 시 설계자가 공학적으로 판단할 것", text)
    # 조치 안내는 결과 화면 전용(result-panel.tsx → ResultNotices screenGuidance)
    panel = (RENDERER / "src/components/result-panel.tsx").read_text(encoding="utf-8")
    self.assertIn("screenGuidance={inputConditionGuidance}", panel)
    report = (RENDERER / "src/components/calculation-report.tsx").read_text(encoding="utf-8")
    self.assertIn('variant="report"', report)
    self.assertNotIn("screenGuidance", report)

  def test_forbidden_pattern_is_case_insensitive(self) -> None:
    for text in ("Warning", "WARNING", "warn", "Caution", "tbd", "확인필요", "결과 적용에 유의할 것"):
      with self.subTest(text=text):
        self.assertTrue(_hits(text))
    for text in ("O.K", "N.G", "적합", "부적합", "O.K (피스 인장 검토 생략)", "안전율 원문 미기재"):
      with self.subTest(text=text):
        self.assertEqual(_hits(text), [])

  # ── 계산서 데이터 구성(page.tsx createReportData 의 텍스트 관련 필드와 같은 규칙) ──
  def _board_slot(self, label: str, board: Mapping[str, Any] | None) -> dict[str, Any]:
    if board is None:
      return {"label": label, "kind": "없음", "thickness": None, "mass_kg_m2": None, "Fy": None, "Fu": None,
              "E_GPa": None, "yieldRatio": None, "yieldRatioSource": None}
    found = next(b for b in self.boards if b["kind"] == board["kind"] and b["thickness"] == board["thickness"])
    return {"label": label, "kind": found["kind"], "thickness": found["thickness"], "mass_kg_m2": found["mass_kg_m2"],
            "Fy": found["Fy"], "Fu": found["Fu"], "E_GPa": found["E_GPa"], "yieldRatio": found["yield_ratio"],
            "yieldRatioSource": found["yield_ratio_source"]}

  def _report_data(self, case: Mapping[str, Any]) -> dict[str, Any]:
    payload = cast(Mapping[str, Any], case["payload"])
    product = cast(Mapping[str, Any] | None, case["product"])
    stud_input = cast(Mapping[str, Any], payload["stud"])
    group = str(stud_input["stud_type"]).split("(")[0]
    method = "맞댐" if "맞댐" in str(stud_input["stud_type"]) else "기본"
    stud = next(s for s in self.studs if s["group"] == group and s["name"] == stud_input["spec"])
    multiplier = 2.0 if method == "맞댐" else 1.0
    rear = sorted(cast(list[Mapping[str, Any]], payload["rear_boards"]), key=lambda b: b["order"])
    front = sorted(cast(list[Mapping[str, Any]], payload["front_boards"]), key=lambda b: b["order"])
    pad = lambda boards, n: [*boards, *[None] * (n - len(boards))]  # noqa: E731
    rear3, front3 = pad(rear, 3), pad(front, 3)
    bolt = cast(Mapping[str, list[float]], payload["bolt"])
    seismic = cast(Mapping[str, Any], payload["seismic"])
    anchor_product = None
    if product is not None:
      anchor_product = {
        "anchorId": product["anchor_id"],
        "label": f"{product['maker']} {product['product']}".strip(),
        "basis": product["basis"],
        "basisLabel": product["basis_label"],
        "source": product["source"],
        "approvals": product["approvals"],
        "concreteCondition": product["concrete_condition"],
        "embedmentMm": payload["anchor_embedment_mm"],
        "concreteFcMPa": payload["anchor_concrete_fc_MPa"],
        "applySeismicCap": payload["anchor_apply_seismic_cap"],
        "minConcreteThicknessMm": product["min_concrete_thickness_mm"],
        "minEdgeMm": product["min_edge_mm"],
        "minSpacingMm": product["min_spacing_mm"],
        "table": product["table"],
      }
    return {
      "generatedAt": "2026-11-26T00:00:00.000Z",
      "calculationMode": case["mode"],
      "rearBoards": [
        self._board_slot("후면 3번(외측)", rear3[2]),
        self._board_slot("후면 2번(중간)", rear3[1]),
        self._board_slot("후면 1번(내측)", rear3[0]),
      ],
      "frontBoards": [
        self._board_slot("전면 1번(내측)", front3[0]),
        self._board_slot("전면 2번(중간)", front3[1]),
        self._board_slot("전면 3번(외측)", front3[2]),
      ],
      "stud": {
        "group": group, "method": method, "spec": stud["name"], "multiplier": multiplier, "H": stud["H"],
        "totalH": stud["H"], "gapMm": None, "connectionInertiaFactor": None, "sectionModulusDepth": stud["H"],
        "B": stud["B"], "t": stud["t"], "A": stud["A"] * multiplier, "IxRaw": stud["Ix"], "SxRaw": stud["Sx"],
        "Ix": stud["Ix"] * multiplier, "Sx": stud["Sx"] * multiplier,
      },
      "geometry": {
        "spacingMm": payload["spacing_mm"], "spanMm": payload["span_mm"],
        "deflectionLimitDenom": payload["deflection_limit_denom"], "anchorSpacingMm": payload["anchor_spacing_mm"],
        "anchorCapacityKn": case["result"]["intermediate"].get("anchor_capacity_kN", payload["anchor_capacity_kN"]),
        "anchorCapacitySource": str(payload.get("anchor_capacity_source") or ""),
      },
      "anchorProduct": anchor_product,
      "loads": {
        "designCaseLabel": "내진" if payload["design_case"] == "seismic" else "비내진",
        "liveLoadKnM2": payload["live_load_kN_m2"], "verticalLoadKnM": payload["vertical_load_kN_m"],
        "seismicS": seismic["S"], "seismicSiteClass": seismic["site_class"],
        "s5BedrockDepthUnknown": seismic["s5_bedrock_depth_unknown"], "seismicIp": seismic["Ip"],
        "seismicZOverH": seismic["z_over_h"],
      },
      "bolts": {
        "outerCount": bolt["count"][0], "middleCount": bolt["count"][1], "innerCount": bolt["count"][2],
        "outerPitch": bolt["pitch"][0], "middlePitch": bolt["pitch"][1], "innerPitch": bolt["pitch"][2],
      },
      "result": case["result"],
    }


if __name__ == "__main__":
  unittest.main()
