"""산출 문서 내부 검토 문구 금지 시험 (APP_DEV item 182, 2026-11-26).

소유자 상시 지시: 계산서·요약페이지 등 프로그램이 만드는 문서에 「확인 필요」「미검증」「주의」「WARN」류 문구를 쓰지 않는다.
판정은 계산값 기준(O.K / N.G)이며, 안내 사유는 화면 메시지로 옮긴다.

시험 3단계
1. API 응답 중 계산서에 실리는 문자열(notices, 앵커 카탈로그 출력 필드, anchor_product_summary)
2. 계산서 컴포넌트 소스의 문자열 리터럴(주석 제외)
3. 표준 예제의 실제 렌더링 텍스트 — CalculationReport·SummaryReport 를 react-dom/server 로 렌더링
   (renderer/scripts/report-wording-check.mjs). renderer/node_modules 가 없으면 실패한다
   (환경변수 KCC_ALLOW_SKIP_RENDER=1 일 때만 건너뜀 — 병합 전 시험에서는 반드시 실행).
4. Codex 1차 반영 분기: 피스 체결층 없는 CH(검토 생략 표기), CH 일부 체결(범위 표기),
   엔진 입력 조건 안내(중립축·표준 외 피스 간격).
5. 소유자 결정(2026-11-26, Curtainwall item 177 공통 방식): 사용자 자유입력·식별 필드(출처·제품명·자재명 등)는
   유보 문구가 있어도 원문 그대로 인쇄한다. 대신 PDF 출력 전 화면에 「유보 문구가 있는 필드」 목록을 경고로 보인다.
   - 프로그램 문구 검사: renderer/scripts/report-wording-check.mjs 의 PROGRAM_TEXT_PATTERN(화면 경고 검출식과 독립).
     렌더링 텍스트에서 사용자 입력 원문을 뺀 나머지가 0곳이어야 한다.
   - 사용자 입력 반례: 원문이 문서에 그대로 있는지 + 화면 경고 목록에 해당 필드가 나오는지 검사한다.

화면 경고 검출식: renderer/src/lib/report-wording.ts (reportForbiddenPatternSource, 대소문자 무관).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
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


def _load_program_pattern() -> re.Pattern[str]:
  """renderer/scripts/report-wording-check.mjs 의 PROGRAM_TEXT_PATTERN 원문을 읽는다(화면 경고 검출식과 독립)."""
  match = re.search(r"PROGRAM_TEXT_PATTERN\s*=\s*/(.+)/giu;", CHECK_SCRIPT.read_text(encoding="utf-8"))
  if match is None:
    raise AssertionError(f"{CHECK_SCRIPT}: PROGRAM_TEXT_PATTERN 을 찾을 수 없음")
  return re.compile(match.group(1), re.IGNORECASE)


PROGRAM_PATTERN = _load_program_pattern()
FREE_INPUT_FORBIDDEN_SOURCE = "승인번호 확인 필요 / Warning"

# 소유자 금지어 각각과 동의·변형 표현의 독립 반례 목록(Codex 2차). 소유자 결정(2026-11-26)에 따라
# 문서에는 원문 그대로 인쇄되고, 화면 경고 목록에 출처 필드가 나와야 한다.
# 각 항목: (자유입력 원문, 원문의 고유 조각)
FORBIDDEN_EXAMPLES: tuple[tuple[str, str], ...] = (
  ("확인필요 자료", "확인필요"),
  ("시험성적서 확인 필요", "시험성적서"),
  ("승인번호는 확인이 필요함", "승인번호는"),
  ("값 확인을 요망", "요망"),
  ("근거 없음 값", "없음 값"),
  ("근거가 없는 값", "근거가 없는"),
  ("미검증 자료", "미검증"),
  ("검증하지 않은 값", "검증하지"),
  ("검증되지 않음", "검증되지"),
  ("초안 자료", "초안"),
  ("보류 항목", "보류"),
  ("확정 필요 값", "확정"),
  ("확정이 필요한 값", "확정이"),
  ("검토 필요", "검토 필요"),
  ("검토가 필요합니다", "검토가"),
  ("검토를 요청함", "요청함"),
  ("추후 확인", "추후"),
  ("별도 확인", "별도"),
  ("별도 검토", "별도"),
  ("확인하시기 바랍니다", "확인하시기"),
  ("주의 제품", "주의"),
  ("결과 적용에 유의할 것", "유의할"),
  ("경고 / DRAFT / 검토가 필요합니다", "DRAFT"),
  ("WARN 표기", "WARN"),
  ("Warning: 원문 대조", "원문 대조"),
  ("warning lowercase", "lowercase"),
  ("CAUTION tag", "tag"),
  ("Draft copy", "copy"),
  ("TBD value", "value"),
  ("TBC value", "value"),
  ("Pending approval", "approval"),
  ("To be confirmed", "confirmed"),
  ("Review required", "Review"),
  ("Needs check", "Needs"),
  ("Unverified data", "data"),
  ("Preliminary data", "data"),
  ("판정 불가", "판정 불가"),
  ("확 인 필 요", "확 인"),
  ("확인\n필요 (줄바꿈)", "줄바꿈"),
  ("W A R N spaced", "spaced"),
  ("ｗａｒｎｉｎｇ fullwidth", "fullwidth"),
  ("확인\u200b필요 zero-width", "zero-width"),
  ("현장 조건을 확인해 주시기 바랍니다", "현장 조건을"),
  ("Please verify before use", "Please"),
  ("사용 전 검토해 주십시오", "사용 전"),
  ("Confirm prior to use", "prior"),
  ("(주의) 현장 메모", "현장 메모"),
  # Codex 4차: 붙여 쓴 합성어·공백 변형
  ("취급주의", "취급주의"),
  ("성능미검증", "성능미검증"),
  ("취급 주 의 표기", "표기"),
  ("성능 미 검 증 자료", "자료"),
  ("사용보류 자재", "사용보류"),
  ("시험미확인 값", "시험미확인"),
  ("승인 확인 안 됨", "안 됨"),
)
# Codex 4차 대표 반례: 두 문서 모두에 원문 + 경고(documents = 계산서·요약페이지)
COMPOUND_EXAMPLES = ("취급주의", "성능미검증")
# 독립 단언용: 문서 본문에 나오면 안 되는 영문 경고 토큰(대소문자 무관 비교)
LITERAL_TOKENS = ("WARN", "CAUTION", "DRAFT", "TBD", "PENDING", "경고", "확인 필요", "확인필요", "검토가 필요")
BOARD_WARN_KIND = "방화 WARN"
BOARD_DRAFT_KIND = "방화 DRAFT"
# 정상값 반례(Codex 3차): 경고 대상이 아닌 출처·자재명(화면 경고 목록에 나오면 안 됨)
SAFE_SOURCE = "건축주의 승인도서 A-17"
SAFE_BOARD_KIND = "건축주의 지정 방화보드"
# 사용자 입력 반례 구성 — 그 밖의 구성(프로그램 문구만)은 화면 경고 목록이 비어야 함
USER_INPUT_CASE_PREFIXES = ("free-", "db-edited", "board-catalog-")

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


def _normalize(text: str) -> str:
  """report-wording.ts normalizeReportText 와 같은 정규화(NFKC·폭 없는 문자 제거·공백 1칸)."""
  text = unicodedata.normalize("NFKC", text)
  text = re.sub("[\u200b-\u200d\u2060\ufeff\u00ad]", "", text)
  return re.sub(r"\s+", " ", text).strip()


def _hits(text: str, pattern: re.Pattern[str] = FORBIDDEN_PATTERN) -> list[str]:
  """정규화형과 공백 제거형 모두에서 금지 표현을 찾는다(report-wording.ts findForbiddenWording 과 같은 규칙)."""
  normalized = _normalize(text)
  compact = re.sub(r"\s+", "", normalized)
  return [m.group(0) for candidate in (normalized, compact) for m in pattern.finditer(candidate)]


def _program_hits(text: str) -> list[str]:
  """프로그램 문구 검사식(PROGRAM_TEXT_PATTERN)으로 찾는다."""
  return _hits(text, PROGRAM_PATTERN)


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
    cases.append({"name": "free-input-source", "mode": "anchorHeight", "payload": free_input, "product": None,
                  "userInputs": [FREE_INPUT_FORBIDDEN_SOURCE]})
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
    # 로컬 DB에서 고친 카탈로그 문자열(유보 문구 포함): 원문 그대로 인쇄 + 화면 경고
    x_c = next(product for product in cls.anchors if product["anchor_id"] == "hilti_x_c")
    edited = {**x_c, "approvals": "승인번호 확인 필요", "concrete_condition": "Warning: 원문 대조", "source": x_c["source"]}
    embedment, fc = _anchor_input(x_c)
    cases.append({
      "name": "db-edited-strings", "mode": "anchorHeight", "product": edited,
      "userInputs": ["승인번호 확인 필요", "Warning: 원문 대조"],
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
    # 자유입력 반례(독립 목록)
    for index, (text, _) in enumerate(FORBIDDEN_EXAMPLES):
      cases.append({
        "name": f"free-example-{index:02d}", "mode": "anchorHeight", "product": None,
        "payload": {**custom, "anchor_capacity_source": text}, "userInputs": [text],
      })
    cases.append({
      "name": "free-safe-source", "mode": "anchorHeight", "product": None,
      "payload": {**custom, "anchor_capacity_source": SAFE_SOURCE}, "userInputs": [SAFE_SOURCE],
    })
    # Codex 4차: 비내진 문서에는 앵커 출처가 인쇄되지 않음 — 경고 목록에도 넣지 않는다
    cases.append({
      "name": "free-nonseismic-source", "mode": "maxHeight", "product": None, "userInputs": ["Warning: A-17"],
      "payload": {**cls.base_payload, "design_case": "non_seismic", "anchor_capacity_source": "Warning: A-17"},
    })
    # Codex 4차: 출처·승인 별개 필드에 같은 문구 — 경고 목록에서 따로 센다
    draft = {**x_c, "source": "DRAFT", "approvals": "DRAFT"}
    cases.append({
      "name": "db-edited-source-approvals", "mode": "anchorHeight", "product": draft, "userInputs": ["DRAFT"],
      "payload": {
        **cls.base_payload, "design_case": "seismic", "anchor_product_id": "hilti_x_c",
        "anchor_embedment_mm": embedment, "anchor_concrete_fc_MPa": fc, "anchor_apply_seismic_cap": True,
        "anchor_capacity_source": "Hilti X-C 카탈로그",
      },
    })
    # 하중 0(비내진·활하중 0): 피스 체결층이 있어도 엔진 지배 피치가 0 — 검토 생략으로 적으면 안 됨
    cases.append({
      "name": "zero-load-c-stud", "mode": "maxHeight", "product": None,
      "payload": {**cls.base_payload, "design_case": "non_seismic", "live_load_kN_m2": 0.0},
    })
    for case in cases:
      case["result"] = cls._check(case["payload"])
    # 로컬 보드 카탈로그 반례: 경고 표현이 든 이름 2개(서로 구분돼야 함) + 실제 '방화'
    cases.append(cls._local_board_case("board-catalog-warn", (BOARD_WARN_KIND, BOARD_DRAFT_KIND), (BOARD_WARN_KIND, BOARD_DRAFT_KIND), "방화"))
    # 정상 자재명(Codex 3차): '건축주의'(건축주+의)는 경고 '주의'가 아님 — 원문 그대로 인쇄
    cases.append(cls._local_board_case("board-catalog-safe", (SAFE_BOARD_KIND,), (SAFE_BOARD_KIND, SAFE_BOARD_KIND), "방화"))
    return cases

  @classmethod
  def _local_board_case(cls, name: str, extra_kinds: tuple[str, ...], front_kinds: tuple[str, ...], rear_kind: str) -> dict[str, Any]:
    """임시 seed에 '방화 19T'와 같은 물성의 보드 종류를 실제 등록하고, 카탈로그 API로 받은 항목으로 구성해 계산한다."""
    temp_dir = tempfile.mkdtemp(prefix="kcc-board-local-")
    cls._temp_dirs = [*getattr(cls, "_temp_dirs", []), temp_dir]
    seed = Path(temp_dir) / "seed"
    shutil.copytree(ROOT / "data/seed", seed)
    board_file = seed / "board_property.json"
    boards = json.loads(board_file.read_text(encoding="utf-8"))
    source = next(item for item in boards["items"] if item["kind"] == "방화" and float(item["thickness"]) == 19.0)
    boards["items"].extend({**source, "kind": kind} for kind in extra_kinds)
    board_file.write_text(json.dumps(boards, ensure_ascii=False), encoding="utf-8")
    client = TestClient(create_app(JsonSeedRepository(seed)))
    catalog = client.get("/api/db/boards").json()["data"]

    def layer(kind: str, order: int) -> dict[str, Any]:
      board = next(item for item in catalog if item["kind"] == kind and float(item["thickness"]) == 19.0)
      return {"kind": board["kind"], "thickness": board["thickness"], "order": order}

    payload = {
      **cls.base_payload,
      "rear_boards": [layer(rear_kind, 1)],
      "front_boards": [layer(kind, order) for order, kind in enumerate(front_kinds, start=1)],
    }
    response = client.post("/api/check", json=payload)
    if response.status_code != 200:
      raise AssertionError(f"{name} /api/check 실패: {response.status_code} {response.text}")
    return {"name": name, "mode": "maxHeight", "product": None, "payload": payload, "result": response.json()["data"], "boards": catalog,
            "userInputs": list(extra_kinds)}

  @classmethod
  def tearDownClass(cls) -> None:
    for temp_dir in getattr(cls, "_temp_dirs", []):
      shutil.rmtree(temp_dir, ignore_errors=True)

  # ── 1. API 응답·카탈로그 출력 필드 ──
  def test_api_report_strings_have_no_forbidden_wording(self) -> None:
    for case in self.cases:
      result = case["result"]
      with self.subTest(case=case["name"]):
        texts = [*cast(list[str], result.get("notices") or []), str(result.get("anchor_product_summary") or "")]
        for text in texts:
          self.assertEqual(_hits(text) + _program_hits(text), [], text)

  def test_anchor_catalog_report_fields_have_no_forbidden_wording(self) -> None:
    for product in self.anchors:
      for field in ANCHOR_REPORT_FIELDS:
        with self.subTest(anchor=product["anchor_id"], field=field):
          value = str(product.get(field) or "")
          self.assertEqual(_hits(value) + _program_hits(value), [], value)
      for row in product["table"]:
        self.assertEqual(_hits(str(row.get("label") or "")), [], row)

  # ── 2. 계산서 컴포넌트 소스 문자열 ──
  def test_report_component_sources_have_no_forbidden_wording(self) -> None:
    for relative in REPORT_SOURCES:
      source = _strip_comments((ROOT / relative).read_text(encoding="utf-8"))
      with self.subTest(file=relative):
        # 문자열 리터럴과 JSX 텍스트만 검사한다(식별자 AlertTriangle·ResultNotices 등은 출력 문구가 아님)
        texts = re.findall(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`', source)
        texts += re.findall(r">([^<>{}]+)<", source)
        self.assertEqual([text for text in texts if _program_hits(text) or _hits(text)], [])

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
    fixtures = [{"name": case["name"], "data": self._report_data(case), "userInputs": case.get("userInputs", [])} for case in self.cases]
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
    summary["printed"] = {(entry["name"], entry["kind"]): entry["userInputsPrinted"] for entry in summary["report"]}
    summary["screen_by_name"] = {entry["name"]: entry for entry in summary["screen"]}
    ReportWordingTest._render_cache = summary
    return summary

  def _text(self, name: str, kind: str) -> str:
    return cast(str, self._render()["texts"][(name, kind)])

  def _fields(self, name: str) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], self._render()["screen_by_name"][name]["reservationFields"])

  def _assert_printed_verbatim(self, name: str, kinds: tuple[str, ...] = ("detail", "summary")) -> None:
    for kind in kinds:
      printed = self._render()["printed"][(name, kind)]
      with self.subTest(case=name, kind=kind):
        self.assertTrue(printed, "반례 전제: userInputs 지정")
        self.assertEqual([item["input"] for item in printed if not item["printed"]], [], f"{kind}: 원문 그대로 인쇄되지 않음")

  def test_rendered_reports_have_no_program_wording(self) -> None:
    # 프로그램 문구(엔진·시드·고정 문자열) 0곳 — 사용자 입력 원문을 뺀 렌더링 텍스트를 독립 검색식으로 검사
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

  def test_free_input_source_is_printed_verbatim_and_warned_on_screen(self) -> None:
    self._assert_printed_verbatim("free-input-source")
    for kind in ("detail", "summary"):
      with self.subTest(kind=kind):
        self.assertIn(f"고정못 허용내력 출처 {FREE_INPUT_FORBIDDEN_SOURCE}", self._text("free-input-source", kind))
    fields = self._fields("free-input-source")
    self.assertIn(("런너 고정못 허용내력 출처", FREE_INPUT_FORBIDDEN_SOURCE), [(f["label"], f["value"]) for f in fields])
    self.assertIsNotNone(self._render()["screen_by_name"]["free-input-source"]["reservationTitle"])
    # 화면 경고는 출력 전(page.tsx)과 입력 화면(input-workspace.tsx) 두 곳
    page = (RENDERER / "src/app/page.tsx").read_text(encoding="utf-8")
    self.assertIn("findReservationFields(", page)
    self.assertIn('data-reservation-warning="before-print"', page)
    self.assertIn("window.confirm(message)", page)
    workspace = (RENDERER / "src/components/input-workspace.tsx").read_text(encoding="utf-8")
    self.assertIn('data-reservation-warning="anchor-source"', workspace)
    case = self.cases_by_name()["free-input-source"]
    self.assertEqual(case["payload"]["anchor_capacity_source"], FREE_INPUT_FORBIDDEN_SOURCE)

  def test_db_edited_strings_are_printed_verbatim_and_warned(self) -> None:
    self._assert_printed_verbatim("db-edited-strings", ("detail",))
    detail = self._text("db-edited-strings", "detail")
    self.assertIn("Hilti X-C", detail)
    values = [f["value"] for f in self._fields("db-edited-strings")]
    self.assertIn("승인번호 확인 필요", values)
    self.assertIn("Warning: 원문 대조", values)

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

  # ── 5. 사용자 입력 반례(소유자 결정 2026-11-26: 원문 인쇄 + 화면 경고) ──
  def test_free_input_examples_are_printed_verbatim_and_warned(self) -> None:
    for index, (text, fragment) in enumerate(FORBIDDEN_EXAMPLES):
      name = f"free-example-{index:02d}"
      with self.subTest(example=text):
        self._assert_printed_verbatim(name)
        for kind in ("detail", "summary"):
          self.assertIn(_normalize(fragment), _normalize(self._text(name, kind)), f"{kind}: {fragment}")
        labels = [f["label"] for f in self._fields(name)]
        self.assertIn("런너 고정못 허용내력 출처", labels, text)
        self.assertEqual(self.cases_by_name()[name]["payload"]["anchor_capacity_source"], text)

  def test_board_catalog_warn_name_is_printed_verbatim_and_warned(self) -> None:
    case = self.cases_by_name()["board-catalog-warn"]
    self.assertTrue(any("WARN" in layer["name"] for layer in case["result"]["layers"]), "반례 전제: 레이어 이름에 WARN")
    self._assert_printed_verbatim("board-catalog-warn")
    detail = self._text("board-catalog-warn", "detail")
    self.assertRegex(detail, r"전면 1번\(내측\)\s+방화 WARN\s+19T")
    self.assertRegex(detail, r"전면 2번\(중간\)\s+방화 DRAFT\s+19T")
    self.assertRegex(detail, r"후면 1번\(내측\)\s+방화\s+19T")
    fields = self._fields("board-catalog-warn")
    labels = [f["label"] for f in fields]
    self.assertIn("전면 1번(내측) 보드 종류", labels)
    self.assertIn("전면 2번(중간) 보드 종류", labels)
    self.assertFalse(any(label.startswith("후면") for label in labels), labels)

  def test_compound_reservation_words_are_warned_for_both_documents(self) -> None:
    # Codex 4차 높음: '취급주의'·'성능미검증'은 두 PDF에 원문 인쇄 + 저장 전 경고·확인 창
    for text in COMPOUND_EXAMPLES:
      name = f"free-example-{[t for t, _ in FORBIDDEN_EXAMPLES].index(text):02d}"
      with self.subTest(example=text):
        self._assert_printed_verbatim(name)
        fields = self._fields(name)
        source = [f for f in fields if f["path"] == "geometry.anchorCapacitySource"]
        self.assertEqual(len(source), 1, fields)
        self.assertEqual(source[0]["documents"], ["detail", "summary"])
        screen = self._render()["screen_by_name"][name]
        self.assertIsNotNone(screen["reservationTitle"])
        for kind in ("detail", "summary"):
          self.assertEqual(screen["output"][kind]["cancel"], {**screen["output"][kind]["cancel"], "status": "canceled", "saves": 0, "prompts": 1})
          self.assertIn(text, screen["output"][kind]["cancel"]["message"])
          self.assertEqual(screen["output"][kind]["approve"]["saves"], 1)

  def test_negative_controls_stay_unwarned(self) -> None:
    # 넓힌 검출식도 정상 명사는 경고하지 않는다
    for text in (SAFE_SOURCE, SAFE_BOARD_KIND, "기초안정", "DEPENDING ON LOAD", "Hilti X-U P8"):
      with self.subTest(text=text):
        self.assertEqual(_hits(text), [])

  def test_separate_fields_are_listed_separately(self) -> None:
    # Codex 4차 중간: 출처·승인에 같은 문구가 있어도 원본 경로별로 따로 센다
    fields = self._fields("db-edited-source-approvals")
    by_path = {f["path"]: f for f in fields}
    self.assertIn("anchorProduct.source", by_path, fields)
    self.assertIn("anchorProduct.approvals", by_path, fields)
    self.assertNotEqual(by_path["anchorProduct.source"]["label"], by_path["anchorProduct.approvals"]["label"])
    self.assertEqual(len(fields), len(by_path))
    # 출력 종류별 인쇄 여부: 콘크리트 조건은 계산서 부록에만 인쇄됨
    edited = {f["path"]: f["documents"] for f in self._fields("db-edited-strings")}
    self.assertEqual(edited["anchorProduct.concreteCondition"], ["detail"])
    self.assertEqual(edited["anchorProduct.approvals"], ["detail", "summary"])

  def test_unprinted_fields_are_not_warned(self) -> None:
    # Codex 4차 중간: 비내진 문서는 앵커 출처를 인쇄하지 않으므로 경고·확인 창 없음
    for kind in ("detail", "summary"):
      with self.subTest(kind=kind):
        printed = self._render()["printed"][("free-nonseismic-source", kind)]
        self.assertEqual([item["printed"] for item in printed], [False])
    self.assertEqual(self._fields("free-nonseismic-source"), [])
    screen = self._render()["screen_by_name"]["free-nonseismic-source"]
    self.assertIsNone(screen["reservationTitle"])
    self.assertEqual(screen["output"]["detail"]["cancel"]["saves"], 1)
    self.assertEqual(screen["output"]["detail"]["cancel"]["prompts"], 0)

  def test_output_procedure_without_warning_saves_directly(self) -> None:
    # Codex 4차 낮음: 경고 0건이면 확인 없이 저장 1회, 경고가 있으면 취소 시 0회·승인 시 1회
    for case in self.cases:
      screen = self._render()["screen_by_name"][case["name"]]
      for kind in ("detail", "summary"):
        targets = [f for f in screen["reservationFields"] if kind in f["documents"]]
        cancel, approve = screen["output"][kind]["cancel"], screen["output"][kind]["approve"]
        with self.subTest(case=case["name"], kind=kind):
          if targets:
            self.assertEqual((cancel["status"], cancel["saves"], cancel["prompts"]), ("canceled", 0, 1))
            self.assertEqual((approve["status"], approve["saves"], approve["prompts"]), ("saved", 1, 1))
          else:
            self.assertEqual((cancel["status"], cancel["saves"], cancel["prompts"]), ("saved", 1, 0))

  def test_direct_browser_print_does_not_print_documents(self) -> None:
    # Codex 4차 중간: 브라우저 인쇄 명령은 앱 확인 절차를 거치지 않으므로 data-print-kind 가 없으면 문서 DOM을 인쇄하지 않는다
    css = (RENDERER / "src/app/globals.css").read_text(encoding="utf-8")
    print_block = css[css.index("@media print"):]
    self.assertRegex(print_block, r"main > \*\s*\{\s*display:\s*none !important;")
    self.assertIn("html[data-print-kind=detail] main > .print-report { display:block !important; }", print_block)
    self.assertIn("html[data-print-kind=summary] main > .print-summary { display:block !important; }", print_block)
    self.assertIn("html:not([data-print-kind]) main > .print-guard { display:block !important; }", print_block)
    self.assertIsNone(re.search(r"(^|\n)\s*\.print-report\s*\{\s*display:\s*block", print_block), "조건 없는 문서 표시 규칙")
    page = (RENDERER / "src/app/page.tsx").read_text(encoding="utf-8")
    handler = page[page.index("async function handlePrintReport"):page.index("async function saveReportPdf")]
    saver = page[page.index("async function saveReportPdf"):page.index("function clearCalculationResult")]
    self.assertIn("runGuardedReportOutput(", handler)
    self.assertIn("save: () => saveReportPdf(reportData, kind)", handler)
    self.assertNotIn("printKind", handler)
    self.assertIn("document.documentElement.dataset.printKind = kind", saver)
    self.assertEqual(page.count("saveReportPdf(reportData, "), 1, "확인 절차를 거치지 않는 저장 호출")
    self.assertEqual(page.count("window.print()"), 1)
    self.assertIn("window.print()", saver)
    self.assertNotIn("dataset.printKind =", page.replace(saver, ""))
    # 앱 메뉴·단축키에 인쇄 항목 없음(문서 인쇄는 저장 버튼 경로만)
    main_js = (RENDERER / "electron/main.cjs").read_text(encoding="utf-8")
    self.assertIsNone(re.search(r"role:\s*\"print\"|CmdOrCtrl\+P|webContents\.print\(", main_js))

  def test_reverted_alias_is_absent(self) -> None:
    # '등록명 n' 대체 표기·문서 범례는 되돌림(소유자 결정 2026-11-26)
    for case in self.cases:
      for kind in ("detail", "summary"):
        with self.subTest(case=case["name"], kind=kind):
          self.assertNotIn("등록명", self._text(case["name"], kind))
          self.assertNotIn("표기 대체", self._text(case["name"], kind))
    self.assertFalse((RENDERER / "src/lib/report-sanitize.ts").exists())

  def test_safe_board_name_is_printed_verbatim(self) -> None:
    self._assert_printed_verbatim("board-catalog-safe")
    self.assertEqual(self._fields("board-catalog-safe"), [])
    for kind in ("detail", "summary"):
      with self.subTest(kind=kind):
        self.assertIn(SAFE_BOARD_KIND, self._text("board-catalog-safe", kind))

  def test_safe_source_is_printed_verbatim(self) -> None:
    self._assert_printed_verbatim("free-safe-source")
    self.assertEqual(self._fields("free-safe-source"), [])
    self.assertIsNone(self._render()["screen_by_name"]["free-safe-source"]["reservationTitle"])
    for kind in ("detail", "summary"):
      with self.subTest(kind=kind):
        self.assertIn(f"고정못 허용내력 출처 {SAFE_SOURCE}", self._text("free-safe-source", kind))

  def test_program_only_cases_have_no_screen_warning(self) -> None:
    # 프로그램 문구(엔진·시드·고정 문자열)는 원천에서 사실 서술 — 경고 목록이 비어야 한다
    for case in self.cases:
      if case["name"].startswith(USER_INPUT_CASE_PREFIXES):
        continue
      with self.subTest(case=case["name"]):
        self.assertEqual(self._fields(case["name"]), [])

  def test_zero_load_with_screw_layers_is_not_marked_skipped(self) -> None:
    case = self.cases_by_name()["zero-load-c-stud"]
    self.assertEqual(case["result"]["intermediate"]["screw_tension_spacing_mm"], 0.0)  # 반례 전제: 엔진 지배 피치 0
    for kind in ("detail", "summary"):
      body = self._text("zero-load-c-stud", kind)
      with self.subTest(kind=kind):
        self.assertNotIn("검토 생략", body)
        self.assertNotIn("CH 끼움 보드만", body)
        self.assertRegex(body, r"피스 인장\s+O\.K(?!\s*\()")

  def test_standard_reports_have_no_literal_tokens(self) -> None:
    for name in ("seismic-hilti_x_u", "seismic-simpson_titen_14", "non_seismic-maxHeight", "ch-slot-only"):
      for kind in ("detail", "summary"):
        body = self._text(name, kind).lower()
        for token in LITERAL_TOKENS:
          with self.subTest(case=name, kind=kind, token=token):
            self.assertNotIn(token.lower(), body)

  def cases_by_name(self) -> dict[str, dict[str, Any]]:
    return {case["name"]: case for case in self.cases}

  def test_program_pattern_catches_owner_terms(self) -> None:
    # 독립 검색식도 소유자 금지어 기본형을 잡는다(대소문자 무관)
    for text in ("확인 필요", "확인필요", "미검증", "주의", "WARN", "warning", "Caution", "DRAFT", "TBD", "검토가 필요"):
      with self.subTest(text=text):
        self.assertTrue(_program_hits(text))
    self.assertIsNot(PROGRAM_PATTERN, FORBIDDEN_PATTERN)

  def test_forbidden_pattern_is_case_insensitive(self) -> None:
    for text in ("Warning", "WARNING", "warn", "Caution", "tbd", "확인필요", "결과 적용에 유의할 것"):
      with self.subTest(text=text):
        self.assertTrue(_hits(text))
    for text in ("(주의) 시공", "주의사항", "Please verify before use", "확인해 주시기 바랍니다", "Confirm prior to use"):
      with self.subTest(text=text):
        self.assertTrue(_hits(text))
    for text in ("O.K", "N.G", "적합", "부적합", "O.K (피스 인장 검토 생략)", "안전율 원문 미기재", SAFE_SOURCE, SAFE_BOARD_KIND,
                 "DEPENDING ON LOAD", "Hardware", "Hilti X-U P8", "검토 조건", "실험으로 검증된 범위"):
      with self.subTest(text=text):
        self.assertEqual(_hits(text), [])

  # ── 계산서 데이터 구성(page.tsx createReportData 의 텍스트 관련 필드와 같은 규칙) ──
  def _board_slot(self, label: str, board: Mapping[str, Any] | None, catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if board is None:
      return {"label": label, "kind": "없음", "thickness": None, "mass_kg_m2": None, "Fy": None, "Fu": None,
              "E_GPa": None, "yieldRatio": None, "yieldRatioSource": None}
    found = next(b for b in (catalog or self.boards) if b["kind"] == board["kind"] and b["thickness"] == board["thickness"])
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
        self._board_slot("후면 3번(외측)", rear3[2], case.get("boards")),
        self._board_slot("후면 2번(중간)", rear3[1], case.get("boards")),
        self._board_slot("후면 1번(내측)", rear3[0], case.get("boards")),
      ],
      "frontBoards": [
        self._board_slot("전면 1번(내측)", front3[0], case.get("boards")),
        self._board_slot("전면 2번(중간)", front3[1], case.get("boards")),
        self._board_slot("전면 3번(외측)", front3[2], case.get("boards")),
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
