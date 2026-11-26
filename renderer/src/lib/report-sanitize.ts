import type { CalculationReportData } from "@/components/calculation-report";
import { isReportSafeText, reportSafeName, reportSafeText } from "./report-wording";

// 산출 문서 인쇄 전 일괄 정화 (APP_DEV item 182, Codex 2차).
// 계산서 데이터의 모든 문자열(DB·시드·자유입력·엔진 문자열)을 한 번에 거른다. 원본 데이터(화면·저장값)는 바꾸지 않고 사본을 만든다.
// - 서술형 자유입력·출처·안내: 금지 표현이 있으면 문자열 전체를 생략("")
// - 명칭(자재 종류·스터드 규격·레이어 이름 등): 금지 표현만 지우고 나머지를 남김(reportSafeName)
// - 열거형 키(모드·판정·레이어 종류 등): 프로그램 고정값이므로 그대로 둠

// 문자열 전체를 생략하는 서술형 키
const OMIT_KEYS = new Set(["anchorCapacitySource", "source", "approvals", "concreteCondition", "anchor_product_summary", "notices"]);
// 프로그램 고정 열거값 키(변환하면 표시 로직이 깨진다)
const ENUM_KEYS = new Set([
  "generatedAt",
  "calculationMode",
  "design_case",
  "strength_check_mode",
  "stress_verdict",
  "deflection_verdict",
  "screw_tension_verdict",
  "layer_type",
  "basis",
  "anchorId",
  "tested_configuration_mismatch_fields",
]);

export interface ReportSanitizeChange {
  // 데이터 경로(예: "frontBoards.0.kind")
  path: string;
  action: "omit" | "rename";
}

export interface SanitizedReport {
  data: CalculationReportData;
  changes: ReportSanitizeChange[];
}

type Json = string | number | boolean | null | Json[] | { [key: string]: Json };

function walk(value: Json, path: string[], omitParent: boolean, changes: ReportSanitizeChange[]): Json {
  const key = path[path.length - 1] ?? "";
  if (typeof value === "string") {
    if (ENUM_KEYS.has(key)) return value;
    if (omitParent || OMIT_KEYS.has(key)) {
      if (reportSafeText(value) !== null) return value;
      changes.push({ path: path.join("."), action: "omit" });
      return "";
    }
    if (isReportSafeText(value)) return value;
    changes.push({ path: path.join("."), action: "rename" });
    return reportSafeName(value);
  }
  if (Array.isArray(value)) {
    if (ENUM_KEYS.has(key)) return value;
    const omit = omitParent || OMIT_KEYS.has(key);
    const items = value.map((item, index) => walk(item, [...path, String(index)], omit, changes));
    // 생략된 안내 문장은 목록에서 뺀다
    return omit ? items.filter((item) => item !== "") : items;
  }
  if (value !== null && typeof value === "object") {
    const output: { [key: string]: Json } = {};
    for (const [childKey, childValue] of Object.entries(value)) {
      output[childKey] = walk(childValue, [...path, childKey], omitParent, changes);
    }
    return output;
  }
  return value;
}

export function sanitizeReportData(data: CalculationReportData): SanitizedReport {
  const changes: ReportSanitizeChange[] = [];
  const cleaned = walk(data as unknown as Json, [], false, changes) as unknown as CalculationReportData;
  return { data: cleaned, changes };
}

// 화면 안내용 경로 → 한글 항목명
const changeLabels: [RegExp, string][] = [
  [/^geometry\.anchorCapacitySource$/, "허용내력 출처"],
  [/^anchorProduct\./, "앵커 제품 정보"],
  [/^(frontBoards|rearBoards)\.\d+\.kind$/, "보드 종류명"],
  [/^(frontBoards|rearBoards)\./, "보드 정보"],
  [/^stud\./, "스터드 정보"],
  [/^result\.layers\./, "레이어 이름"],
  [/^result\.notices/, "입력 조건 안내"],
  [/^loads\./, "하중·지진 입력 표기"],
];

// 화면 안내 문구. 바뀐 항목이 없으면 null
export function reportSanitizeNotice(changes: ReportSanitizeChange[]): string | null {
  if (changes.length === 0) return null;
  const labels = new Set<string>();
  for (const change of changes) {
    const label = changeLabels.find(([pattern]) => pattern.test(change.path))?.[1] ?? "기타 표기";
    labels.add(label);
  }
  return `계산서·요약페이지에 쓰지 않는 표현(예: "확인 필요", "경고", "Warning", "Draft")이 있어 다음 항목은 문서에서 생략하거나 해당 표현을 빼고 표시함: ${[...labels].join(", ")}. 입력값·자재 DB 원문은 그대로 저장됨.`;
}
