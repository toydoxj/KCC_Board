import type { WallCheckResult } from "./api";

// 유보 문구(확인 필요·주의·WARN 등) 검출식 (APP_DEV item 182, CODEX.md §11).
// 용도: 사용자 자유입력·식별 필드(제품명·자재명·출처 등)에 유보 문구가 있으면 PDF 출력 전 화면에 경고 목록을 보인다.
// 산출 문서는 이 필드를 원문 그대로 인쇄한다(소유자 결정 2026-11-26 — 지우거나 바꾸지 않음).
// 프로그램 문구 검사(시험)는 이 검출식과 독립된 검색식을 쓴다(renderer/scripts/report-wording-check.mjs, tests/test_report_wording.py).
// 검사는 normalizeReportText(NFKC·폭 없는 문자 제거·공백/줄바꿈 1칸) 후 원문형과 공백 제거형 두 가지로 한다.
// 영문은 대소문자 무관. 한국어는 조사·어미 변형(확인이/확인을/검토가 필요합니다, 확인해 주시기 바랍니다 등)을 받는다.
// 화면 경고는 과탐이 무해하므로 넓게 잡는다(Codex 4차): 붙여 쓴 합성어('취급주의'·'성능미검증'·'사용보류')도 경고한다.
// 예외는 '건축주의'·'발주의'처럼 '…주(사람)+의' 조사 결합과 '기초안'(기초+안)뿐이다. 영문 단어는 앞 글자가 영문이 아닐 때만 잡는다('DEPENDING' 제외).
export const reportForbiddenPatternSource = String.raw`(확인|검토|확정|검증)\s*(이|을|를|가)?\s*(필요|요망|요청|바람|바랍)|(확인|검토|검증|대조)\s*(해|하여|하고|해서)\s*(주|바|보)|확인하시기|확인\s*하십시오|확인\s*하세요|검증\s*(하지|되지|안\s*됨|전)|근거\s*(가|는|이)?\s*없|별도\s*(확인|검토)|판정\s*불가|결과\s*적용에|(?<![발업점화선차집민])(?<!건축|사업|시행|소유|고용|건물|임대|가맹|시공|공사|자본|사회|공산|민족|국가|개인)주의|유의\s*(할|하|바|요)|경고|보류|(?<!기)초안|잠정|추후|미검증|미검토|미확인|미확정|미승인|(확인|검증|검토)\s*(안\s*됨|안\s*된|되지\s*않)|(?<![A-Za-z])(WARN|CAUTION|ALERT|ATTENTION|DRAFT|TBD|TBC|TODO|FIXME|PENDING|PRELIMINARY|PROVISIONAL|UNVERIFIED|UNCONFIRMED|NOT\s*VERIFIED|TO\s*BE\s*(CONFIRMED|DETERMINED|VERIFIED|CHECKED|REVIEWED)|(REVIEW|CHECK|CONFIRMATION|VERIFICATION)\s*(IS\s*)?(REQUIRED|NEEDED|PENDING)|NEEDS?\s*(TO\s*BE\s*)?(REVIEW|CHECK|CONFIRM|VERIF)|PLEASE\s*(VERIFY|CONFIRM|CHECK|REVIEW)|(VERIFY|CONFIRM|CHECK|REVIEW)\s*(BEFORE|PRIOR\s*TO)\s*USE)`;

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

// 유보 문구가 없는 문자열인지. 빈 문자열은 해당 없음으로 본다
export function isReportSafeText(text: string | null | undefined) {
  return findForbiddenWording(text).length === 0;
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
