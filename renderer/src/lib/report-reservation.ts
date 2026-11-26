import type { CalculationReportData } from "@/components/calculation-report";
import { findForbiddenWording } from "./report-wording";

// PDF 출력 전 화면 경고: 유보 문구가 있는 필드 목록 (소유자 결정 2026-11-26, Curtainwall item 177 공통 방식)
// 사용자 자유입력·식별 필드(제품명·자재명·출처 등)는 산출 문서에 원문 그대로 인쇄한다. 지우거나 바꾸지 않는다.
// 대신 어떤 필드에 유보 문구가 있는지 화면에 알려 사용자가 출력 전에 고칠 수 있게 한다.
// 프로그램 문구(엔진·시드·고정 문자열)는 원천에서 사실 서술이므로 이 목록에 나오지 않는다(시험 고정).

export interface ReservationField {
  // 화면 표기 항목명(예: "전면 1번(내측) 보드 종류")
  label: string;
  // 원문 값
  value: string;
  // 검출된 유보 표현
  words: string[];
}

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
  [/^anchorProduct\.(source|approvals)$/, () => "앵커 제품 출처·승인"],
  [/^anchorProduct\.basisLabel$/, () => "앵커 제품 허용하중 기준"],
  [/^anchorProduct\.concreteCondition$/, () => "앵커 제품 콘크리트 조건"],
  [/^anchorProduct\.table\.\d+\.label$/, () => "앵커 허용하중 표 비고"],
  [/^(frontBoards|rearBoards)\.(\d+)\.kind$/, () => "보드 종류"],
  [/^(frontBoards|rearBoards)\.(\d+)\./, () => "보드 정보"],
  [/^stud\.(group|spec|method)$/, () => "스터드 형식·규격·시공방식"],
  [/^result\.layers\.\d+\.name$/, () => "레이어 이름(자재명 포함)"],
  [/^result\.notices/, () => "입력 조건 안내"],
  [/^loads\./, () => "하중·지진 입력 표기"],
];

function labelFor(path: string[], data: CalculationReportData) {
  const joined = path.join(".");
  // 보드 위치명을 함께 보인다(예: "전면 1번(내측) 보드 종류")
  const boardMatch = joined.match(/^(frontBoards|rearBoards)\.(\d+)\./);
  const base = fieldLabels.find(([pattern]) => pattern.test(joined));
  const name = base ? base[1](joined.match(base[0]) as RegExpMatchArray) : "기타 표기";
  if (boardMatch) {
    const slot = data[boardMatch[1] as "frontBoards" | "rearBoards"][Number(boardMatch[2])];
    return slot ? `${slot.label} ${name}` : name;
  }
  return name;
}

export function findReservationFields(data: CalculationReportData): ReservationField[] {
  const fields: ReservationField[] = [];
  const seen = new Set<string>();
  const walk = (value: unknown, path: string[]) => {
    const key = path[path.length - 1] ?? "";
    if (ENUM_KEYS.has(key)) return;
    if (typeof value === "string") {
      const words = findForbiddenWording(value);
      if (words.length === 0) return;
      const label = labelFor(path, data);
      const id = `${label}\u0000${value}`;
      if (seen.has(id)) return;
      seen.add(id);
      fields.push({ label, value, words });
    } else if (Array.isArray(value)) {
      value.forEach((item, index) => walk(item, [...path, String(index)]));
    } else if (value !== null && typeof value === "object") {
      for (const [childKey, child] of Object.entries(value)) walk(child, [...path, childKey]);
    }
  };
  walk(data, []);
  return fields;
}

// 화면 경고 제목. 목록이 비면 null
export function reservationWarningTitle(fields: ReservationField[]): string | null {
  if (fields.length === 0) return null;
  return `유보 문구가 있는 필드 ${fields.length}곳 — 계산서·요약페이지에는 입력·자재 DB 원문 그대로 인쇄됨. 출력 전에 해당 필드를 확인할 것.`;
}
