import type { CalculationReportData } from "@/components/calculation-report";
import { findForbiddenWording, normalizeReportText } from "./report-wording";

// PDF 출력 전 화면 경고: 유보 문구가 있는 필드 목록 (소유자 결정 2026-11-26, Curtainwall item 177 공통 방식)
// 사용자 자유입력·식별 필드(제품명·자재명·출처 등)는 산출 문서에 원문 그대로 인쇄한다. 지우거나 바꾸지 않는다.
// 대신 어떤 필드에 유보 문구가 있는지 화면에 알려 사용자가 출력 전에 고칠 수 있게 한다.
// - 필드는 원본 경로 단위로 따로 센다(출처·승인 등 별개 필드를 합치지 않음 — Codex 4차).
// - 실제로 인쇄되는 필드만 넣는다: 문서 종류별 렌더링 텍스트에 원문이 있는지로 판별한다(비내진 앵커 출처 등 제외 — Codex 4차).
// - 파생 표기(레이어 이름 = 보드 종류 + 두께)는 원본 보드 종류 항목에 합친다.
// 프로그램 문구(엔진·시드·고정 문자열)는 원천에서 사실 서술이므로 이 목록에 나오지 않는다(시험 고정).

export type ReportKind = "detail" | "summary";

export const reportKindLabels: Record<ReportKind, string> = {
  detail: "계산서",
  summary: "요약페이지",
};

export interface ReservationField {
  // 원본 필드 경로(식별자, 예: "frontBoards.0.kind")
  path: string;
  // 화면 표기 항목명(예: "전면 1번(내측) 보드 종류")
  label: string;
  // 원문 값
  value: string;
  // 검출된 유보 표현
  words: string[];
  // 원문이 인쇄되는 문서
  documents: ReportKind[];
}

// 문서 종류별 렌더링 텍스트(화면: 인쇄용 DOM의 textContent, 시험: SSR 텍스트)
export type PrintedTexts = Partial<Record<ReportKind, string>>;

// 프로그램 고정 열거값 키(검사 대상 아님)
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
]);

const fieldLabels: [RegExp, (match: RegExpMatchArray) => string][] = [
  [/^geometry\.anchorCapacitySource$/, () => "런너 고정못 허용내력 출처"],
  [/^anchorProduct\.label$/, () => "앵커 제품명"],
  [/^anchorProduct\.source$/, () => "앵커 제품 출처"],
  [/^anchorProduct\.approvals$/, () => "앵커 제품 승인"],
  [/^anchorProduct\.basisLabel$/, () => "앵커 제품 허용하중 기준"],
  [/^anchorProduct\.concreteCondition$/, () => "앵커 제품 콘크리트 조건"],
  [/^anchorProduct\.table\.(\d+)\.label$/, (match) => `앵커 허용하중 표 ${Number(match[1]) + 1}행 비고`],
  [/^(frontBoards|rearBoards)\.\d+\.kind$/, () => "보드 종류"],
  [/^(frontBoards|rearBoards)\.\d+\./, () => "보드 정보"],
  [/^stud\.group$/, () => "스터드 형식"],
  [/^stud\.spec$/, () => "스터드 규격"],
  [/^stud\.method$/, () => "스터드 시공방식"],
  [/^result\.layers\.(\d+)\.name$/, (match) => `레이어 ${Number(match[1]) + 1} 이름(자재명 포함)`],
  [/^result\.notices\.(\d+)$/, (match) => `입력 조건 안내 ${Number(match[1]) + 1}`],
  [/^loads\./, () => "하중·지진 입력 표기"],
];

function labelFor(path: string, data: CalculationReportData) {
  const base = fieldLabels.find(([pattern]) => pattern.test(path));
  const name = base ? base[1](path.match(base[0]) as RegExpMatchArray) : `기타 표기(${path})`;
  // 보드 위치명을 함께 보인다(예: "전면 1번(내측) 보드 종류")
  const boardMatch = path.match(/^(frontBoards|rearBoards)\.(\d+)\./);
  if (boardMatch) {
    const slot = data[boardMatch[1] as "frontBoards" | "rearBoards"][Number(boardMatch[2])];
    return slot ? `${slot.label} ${name}` : name;
  }
  return name;
}

function printedIn(value: string, printed: PrintedTexts): ReportKind[] {
  const needle = normalizeReportText(value);
  if (!needle) return [];
  return (Object.keys(reportKindLabels) as ReportKind[]).filter((kind) => {
    const text = printed[kind];
    return text !== undefined && normalizeReportText(text).includes(needle);
  });
}

export function findReservationFields(data: CalculationReportData, printed: PrintedTexts): ReservationField[] {
  const candidates: ReservationField[] = [];
  const walk = (value: unknown, path: string[]) => {
    const key = path[path.length - 1] ?? "";
    if (ENUM_KEYS.has(key)) return;
    if (typeof value === "string") {
      const words = findForbiddenWording(value);
      if (words.length === 0) return;
      const joined = path.join(".");
      candidates.push({ path: joined, label: labelFor(joined, data), value, words, documents: printedIn(value, printed) });
    } else if (Array.isArray(value)) {
      value.forEach((item, index) => walk(item, [...path, String(index)]));
    } else if (value !== null && typeof value === "object") {
      for (const [childKey, child] of Object.entries(value)) walk(child, [...path, childKey]);
    }
  };
  walk(data, []);
  // 파생 표기: 레이어 이름이 경고된 보드 종류를 담으면 원본 보드 종류 항목으로 대신한다
  const boardKinds = candidates.filter((field) => /^(frontBoards|rearBoards)\.\d+\.kind$/.test(field.path));
  const isDerivedLayer = (field: ReservationField) =>
    /^result\.layers\.\d+\.name$/.test(field.path) &&
    boardKinds.some((board) => normalizeReportText(field.value).includes(normalizeReportText(board.value)));
  return candidates.filter((field) => field.documents.length > 0 && !isDerivedLayer(field));
}

// 한 문서 종류에 인쇄되는 항목만
export function reservationFieldsFor(fields: ReservationField[], kind: ReportKind) {
  return fields.filter((field) => field.documents.includes(kind));
}

// 화면 경고 제목. 목록이 비면 null
export function reservationWarningTitle(fields: ReservationField[]): string | null {
  if (fields.length === 0) return null;
  return `유보 문구가 있는 필드 ${fields.length}곳 — 계산서·요약페이지에는 입력·자재 DB 원문 그대로 인쇄됨. 출력 전에 해당 필드를 확인할 것.`;
}

export function reservationFieldText(field: ReservationField) {
  return `${field.label}: “${field.value}” (${field.words.join(", ")}) — ${field.documents.map((kind) => reportKindLabels[kind]).join("·")}`;
}

export function reservationConfirmMessage(fields: ReservationField[], kind: ReportKind) {
  return `${reservationWarningTitle(fields)}\n\n${fields.map((field) => `· ${reservationFieldText(field)}`).join("\n")}\n\n그대로 ${reportKindLabels[kind]} PDF로 저장할까요?`;
}

// 출력 절차(앱 저장 버튼 경로): 해당 문서에 인쇄되는 경고 항목이 있으면 확인을 받고, 승인했을 때만 저장한다.
// 반환: "saved"(저장 함수 호출) / "canceled"(확인 거절 — 저장 함수 호출 안 함)
export async function runGuardedReportOutput(options: {
  kind: ReportKind;
  fields: ReservationField[];
  confirm: (message: string) => boolean;
  save: () => Promise<void> | void;
}): Promise<"saved" | "canceled"> {
  const targets = reservationFieldsFor(options.fields, options.kind);
  if (targets.length > 0 && !options.confirm(reservationConfirmMessage(targets, options.kind))) {
    return "canceled";
  }
  await options.save();
  return "saved";
}
