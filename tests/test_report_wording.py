"""산출 문서 내부 검토 문구 금지 시험 (APP_DEV item 182, 2026-11-26).

소유자 상시 지시: 계산서·요약페이지 등 프로그램이 만드는 문서에 「확인 필요」「미검증」「주의」「WARN」류 문구를 쓰지 않는다.
판정은 계산값 기준(O.K / N.G)이며, 안내 사유는 화면 메시지로 옮긴다.

시험 3단계
1. API 응답 중 계산서에 실리는 문자열(notices, 앵커 카탈로그 출력 필드, anchor_product_summary)
2. 계산서 컴포넌트 소스의 문자열 리터럴(주석 제외)
3. 표준 예제의 실제 렌더링 텍스트 — CalculationReport·SummaryReport 를 react-dom/server 로 렌더링
   (renderer/scripts/report-wording-check.mjs). renderer/node_modules 가 없으면 명시적으로 건너뛴다.
"""

from __future__ import annotations

import json
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

# renderer/scripts/report-wording-check.mjs FORBIDDEN_PATTERN 과 같은 목록을 유지한다
FORBIDDEN_PATTERN = re.compile(
  r"확인\s*필요|확인이\s*필요|근거\s*없음|미검증|검증하지\s*않|검증되지\s*않|초안|보류|확정\s*필요|검토\s*필요"
  r"|추후\s*확인|별도\s*확인|확인하시기|주의|WARN|판정\s*불가"
)

# 계산서·요약페이지에 텍스트를 내보내는 렌더러 소스(화면 전용 input-workspace 등은 대상 아님)
REPORT_SOURCES = (
  "renderer/src/components/calculation-report.tsx",
  "renderer/src/components/summary-report.tsx",
  "renderer/src/components/result-notices.tsx",
  "renderer/src/lib/result-notice.ts",
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
  def test_rendered_reports_have_no_forbidden_wording(self) -> None:
    node = shutil.which("node")
    if node is None or not (RENDERER / "node_modules/react-dom").is_dir() or not (RENDERER / "node_modules/typescript").is_dir():
      self.skipTest("node 또는 renderer/node_modules 없음 — `cd renderer; npm ci` 후 다시 실행할 것")
    fixtures = [{"name": case["name"], "data": self._report_data(case)} for case in self.cases]
    with tempfile.TemporaryDirectory() as temp_dir:
      fixture_path = Path(temp_dir) / "fixtures.json"
      fixture_path.write_text(json.dumps(fixtures, ensure_ascii=False), encoding="utf-8")
      completed = subprocess.run(
        [node, str(CHECK_SCRIPT), str(fixture_path)],
        cwd=RENDERER,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
      )
    if completed.returncode == 2 or not completed.stdout.strip():
      self.fail(f"렌더링 실패(exit {completed.returncode}): {completed.stderr[-2000:]}")
    summary = json.loads(completed.stdout)
    self.assertEqual(len(summary["report"]), 2 * len(fixtures))
    hits = [entry for entry in summary["report"] if entry["hits"]]
    self.assertEqual(hits, [], json.dumps(hits, ensure_ascii=False, indent=1))
    self.assertEqual(completed.returncode, 0, completed.stderr)

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
