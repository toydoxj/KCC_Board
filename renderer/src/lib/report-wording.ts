import type { WallCheckResult } from "./api";

// 산출 문서(상세 계산서·요약페이지) 금지 문구 (APP_DEV item 182, 소유자 상시 지시 — CODEX.md §11).
// 단일 출처: tests/test_report_wording.py 와 renderer/scripts/report-wording-check.mjs 가 이 패턴 원문을 그대로 읽는다.
// 검사는 normalizeReportText(NFKC·폭 없는 문자 제거·공백/줄바꿈 1칸) 후 원문형과 공백 제거형 두 가지로 한다.
// 영문은 대소문자 무관. 한국어는 조사·어미 변형(확인이/확인을/검토가 필요합니다, 확인해 주시기 바랍니다 등)을 받는다.
// 짧은 경고 명사(주의·경고·보류 등)와 영문 단어는 앞 글자가 한글/영문이 아닐 때만 잡는다 — '건축주의'(건축주+의)·'DEPENDING' 오탐 방지(Codex 3차).
export const reportForbiddenPatternSource = String.raw`(확인|검토|확정|검증)\s*(이|을|를|가)?\s*(필요|요망|요청|바람|바랍)|(확인|검토|검증|대조)\s*(해|하여|하고|해서)\s*(주|바|보)|확인하시기|확인\s*하십시오|확인\s*하세요|검증\s*(하지|되지|안\s*됨|전)|근거\s*(가|는|이)?\s*없|별도\s*(확인|검토)|판정\s*불가|결과\s*적용에|(?<![가-힣])(주의|유의\s*(할|하|바|요)|경고|보류|초안|잠정|추후|미검증|미확인|미확정)|(?<![A-Za-z])(WARN|CAUTION|ALERT|ATTENTION|DRAFT|TBD|TBC|TODO|FIXME|PENDING|PRELIMINARY|PROVISIONAL|UNVERIFIED|UNCONFIRMED|NOT\s*VERIFIED|TO\s*BE\s*(CONFIRMED|DETERMINED|VERIFIED|CHECKED|REVIEWED)|(REVIEW|CHECK|CONFIRMATION|VERIFICATION)\s*(IS\s*)?(REQUIRED|NEEDED|PENDING)|NEEDS?\s*(TO\s*BE\s*)?(REVIEW|CHECK|CONFIRM|VERIF)|PLEASE\s*(VERIFY|CONFIRM|CHECK|REVIEW)|(VERIFY|CONFIRM|CHECK|REVIEW)\s*(BEFORE|PRIOR\s*TO)\s*USE)`;

export function reportForbiddenPattern(global = false) {
  return new RegExp(reportForbiddenPatternSource, global ? "giu" : "iu");
}

// 검사 전 정규화: 호환 문자(전각 등)·폭 없는 문자·공백·줄바꿈 차이를 없앤다
export function normalizeReportText(text: string) {
  return text.normalize("NFKC").replace(/[\u200B-\u200D\u2060\uFEFF\u00AD]/g, "").replace(/\s+/g, " ").trim();
}

// 금지 문구 검출(정규화형 + 공백 제거형). 반환: 찾은 표현 목록
export function findForbiddenWording(text: string | null | undefined): string[] {
  const normalized = normalizeReportText(text ?? "");
  const compact = normalized.replace(/\s+/g, "");
  const found = new Set<string>();
  for (const candidate of [normalized, compact]) {
    for (const match of candidate.match(reportForbiddenPattern(true)) ?? []) found.add(match);
  }
  return [...found];
}

// 산출 문서에 그대로 실어도 되는 문자열인지. 빈 문자열은 안전으로 본다
export function isReportSafeText(text: string | null | undefined) {
  return findForbiddenWording(text).length === 0;
}

// 자유입력·DB 문자열을 인쇄 전에 거른다. 금지 문구가 있으면 null(문서에서 해당 표시 생략). 원문은 저장값 그대로 둔다
export function reportSafeText(text: string | null | undefined): string | null {
  const value = normalizeReportText(text ?? "");
  return isReportSafeText(value) ? value : null;
}

// 화면 안내: 문서에서 생략되는 자유입력 문구의 사유
export function reportOmittedTextNotice(fieldLabel: string) {
  return `${fieldLabel}에 산출 문서에 쓰지 않는 표현(예: "확인 필요", "주의", "Warning")이 있어 계산서·요약페이지에는 표시하지 않음. 입력값은 그대로 저장됨.`;
}

// 피스 인장 검토 범위. 엔진 판정(screw_tension_verdict)은 바꾸지 않고 문서 표기만 정한다
export interface ScrewTensionScope {
  // 피스 체결층이 있어 사용률을 계산했는지
  checked: boolean;
  // CH 끼움 후면 보드가 있어 피스 체결층 일부만 검토했는지
  partial: boolean;
  // 판정 카드 표기: "O.K" / "O.K (피스 인장 검토 생략)" 등
  verdictLabel: string;
  // 검토 조건·범위 설명
  scopeLabel: string;
}

// 피스 체결층은 실제 보드 구성으로 판별한다(Codex 2차): 전면 보드는 항상 피스 체결, 후면 보드는 CH-STUD(홈 끼움)만 피스 없음.
// 하중 0 등으로 엔진 지배 피치가 0이어도 체결층이 있으면 검토한 것으로 본다(수요 0 → 사용률 0)
export function screwTensionScope(result: WallCheckResult, frontBoardPresent: boolean, rearBoardPresent: boolean): ScrewTensionScope {
  const rearIsSlot = result.intermediate.ch_slot_rear_board === 1;
  const checked = frontBoardPresent || (rearBoardPresent && !rearIsSlot);
  const partial = checked && rearIsSlot && rearBoardPresent;
  const verdict = result.screw_tension_verdict;
  if (!checked) {
    return {
      checked,
      partial,
      verdictLabel: `${verdict} (피스 인장 검토 생략)`,
      scopeLabel: "피스 체결층 없음(CH 끼움 보드만 있음) — 피스 인장 검토 생략",
    };
  }
  return {
    checked,
    partial,
    verdictLabel: partial ? `${verdict} (전면 피스 체결층)` : verdict,
    scopeLabel: partial ? "전면 피스 체결층(후면 CH 끼움 보드는 피스 없음 — 검토 생략)" : "피스 체결 전 층",
  };
}
