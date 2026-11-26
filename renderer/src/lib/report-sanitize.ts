import type { CalculationReportData } from "@/components/calculation-report";
import { isReportSafeText, reportSafeText } from "./report-wording";

// 산출 문서 인쇄 전 일괄 정화 (APP_DEV item 182, Codex 2·3차).
// 대상은 사용자·로컬 DB가 넣은 문자열(자유입력·로컬 자재 DB)이다. 프로그램이 만든 문구(엔진·시드·고정 문자열)는
// 원천에서 사실 서술로 고쳐 두었으므로 표준 구성에서는 바뀌는 항목이 없어야 한다(tests/test_report_wording.py 가 고정).
// 원본 데이터(화면·저장값)는 바꾸지 않고 사본을 만든다.
// - 서술형(출처·조건·안내): 금지 표현이 있으면 문자열 전체를 생략("")
// - 식별 필드(자재 종류·스터드 규격·제품명 등): 부분 삭제로 훼손하지 않는다. 금지 표현이 있으면 이름 전체를
//   고유 대체 표기("등록명 1", "등록명 2" …)로 바꾸고, 같은 원 명칭이 들어간 파생 문자열(레이어 이름 등)도 같은 대체 표기로 맞춘다.
//   서로 다른 원 명칭은 서로 다른 대체 표기를 받으므로 문서에서 구분된다. 대체 표기 범례는 문서에 사실로 적는다.
// - 열거형 키(모드·판정·레이어 종류 등): 프로그램 고정값이므로 그대로 둠

// 문자열 전체를 생략하는 서술형 키
const OMIT_KEYS = new Set(["anchorCapacitySource", "source", "approvals", "concreteCondition", "anchor_product_summary", "notices"]);
// 식별 필드 키(원 명칭 그대로 쓰거나, 금지 표현이 있으면 이름 전체를 대체 표기로)
const IDENTIFIER_KEYS = new Set(["kind", "group", "spec", "method", "label", "basisLabel", "yieldRatioSource", "designCaseLabel", "seismicSiteClass"]);
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

export const REPORT_ALIAS_PREFIX = "등록명";

export interface ReportSanitizeChange {
  // 데이터 경로(예: "frontBoards.0.kind")
  path: string;
  action: "omit" | "alias";
}

export interface ReportAlias {
  alias: string;
  // 원 명칭이 있던 첫 경로(범례의 항목 구분용)
  path: string;
}

export interface SanitizedReport {
  data: CalculationReportData;
  changes: ReportSanitizeChange[];
  aliases: ReportAlias[];
}

type Json = string | number | boolean | null | Json[] | { [key: string]: Json };

function collectStrings(value: Json, path: string[], out: { path: string[]; value: string }[]) {
  if (typeof value === "string") {
    out.push({ path, value });
  } else if (Array.isArray(value)) {
    value.forEach((item, index) => collectStrings(item, [...path, String(index)], out));
  } else if (value !== null && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) collectStrings(child, [...path, key], out);
  }
}

export function sanitizeReportData(data: CalculationReportData): SanitizedReport {
  const source = data as unknown as Json;
  const strings: { path: string[]; value: string }[] = [];
  collectStrings(source, [], strings);
  const existing = new Set(strings.map((item) => item.value));

  // 1) 금지 표현이 있는 식별 값에 고유 대체 표기를 정한다(첫 등장 순서, 기존 문자열과 겹치지 않게)
  const aliasByOriginal = new Map<string, string>();
  const aliases: ReportAlias[] = [];
  let counter = 0;
  for (const item of strings) {
    const key = item.path[item.path.length - 1] ?? "";
    if (!IDENTIFIER_KEYS.has(key) || isReportSafeText(item.value) || aliasByOriginal.has(item.value)) continue;
    let alias = "";
    do {
      counter += 1;
      alias = `${REPORT_ALIAS_PREFIX} ${counter}`;
    } while (existing.has(alias));
    aliasByOriginal.set(item.value, alias);
    aliases.push({ alias, path: item.path.join(".") });
  }
  // 긴 원 명칭부터 바꿔 부분 겹침을 피한다
  const replacements = [...aliasByOriginal.entries()].sort((a, b) => b[0].length - a[0].length);
  const applyAliases = (text: string) => replacements.reduce((acc, [original, alias]) => acc.split(original).join(alias), text);

  const changes: ReportSanitizeChange[] = [];
  const walk = (value: Json, path: string[], omitParent: boolean): Json => {
    const key = path[path.length - 1] ?? "";
    if (typeof value === "string") {
      if (ENUM_KEYS.has(key)) return value;
      if (omitParent || OMIT_KEYS.has(key)) {
        if (reportSafeText(value) !== null) return value;
        changes.push({ path: path.join("."), action: "omit" });
        return "";
      }
      if (isReportSafeText(value)) return value;
      const replaced = applyAliases(value);
      changes.push({ path: path.join("."), action: "alias" });
      if (isReportSafeText(replaced)) return replaced;
      // 파생 문자열에 대체 대상 밖의 금지 표현이 남으면 표시 생략
      return "—";
    }
    if (Array.isArray(value)) {
      if (ENUM_KEYS.has(key)) return value;
      const omit = omitParent || OMIT_KEYS.has(key);
      const items = value.map((item, index) => walk(item, [...path, String(index)], omit));
      return omit ? items.filter((item) => item !== "") : items;
    }
    if (value !== null && typeof value === "object") {
      const output: { [key: string]: Json } = {};
      for (const [childKey, childValue] of Object.entries(value)) output[childKey] = walk(childValue, [...path, childKey], omitParent);
      return output;
    }
    return value;
  };
  const cleaned = walk(source, [], false) as unknown as CalculationReportData;
  return { data: cleaned, changes, aliases };
}

// 문서에 싣는 대체 표기 범례(사실 서술). 대체 표기가 없으면 null
export function reportAliasLegend(aliases: ReportAlias[]): string | null {
  if (aliases.length === 0) return null;
  return `표기 대체: ${aliases.map((item) => item.alias).join(", ")} — 자재 DB·입력에 등록된 명칭을 문서 표기 규칙에 따라 고유 번호로 표기함(원 명칭은 프로그램 자재 DB·입력값에 보존).`;
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
  return `계산서·요약페이지에 쓰지 않는 표현(예: "확인 필요", "경고", "Warning", "Draft")이 있어 다음 항목은 문서에서 생략하거나 고유 번호(${REPORT_ALIAS_PREFIX} n)로 표기함: ${[...labels].join(", ")}. 입력값·자재 DB 원문은 그대로 저장됨.`;
}
