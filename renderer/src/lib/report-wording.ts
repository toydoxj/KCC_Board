import type { WallCheckResult } from "./api";

// 산출 문서(상세 계산서·요약페이지) 금지 문구 (APP_DEV item 182, 소유자 상시 지시 — CODEX.md §11).
// 단일 출처: tests/test_report_wording.py 와 renderer/scripts/report-wording-check.mjs 가 이 패턴 원문을 그대로 읽는다.
// 영문(WARN/Warning/warning 등)은 대소문자 무관하게 잡는다.
export const reportForbiddenPatternSource = String.raw`확인\s*필요|확인이\s*필요|근거\s*없음|미검증|검증하지\s*않|검증되지\s*않|초안|보류|확정\s*필요|검토\s*필요|추후\s*확인|별도\s*확인|확인하시기|주의|유의|WARN|CAUTION|TBD|판정\s*불가`;

export function reportForbiddenPattern(global = false) {
  return new RegExp(reportForbiddenPatternSource, global ? "giu" : "iu");
}

// 산출 문서에 그대로 실어도 되는 문자열인지. 빈 문자열은 안전으로 본다
export function isReportSafeText(text: string | null | undefined) {
  return !reportForbiddenPattern().test(text ?? "");
}

// 자유입력·DB 문자열을 인쇄 전에 거른다. 금지 문구가 있으면 null(문서에서 해당 표시 생략). 원문은 저장값 그대로 둔다
export function reportSafeText(text: string | null | undefined): string | null {
  const value = (text ?? "").trim();
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

// rearBoardPresent: 후면 보드가 1겹 이상 있는지(CH-STUD 후면 보드는 홈 끼움 — 피스 없음)
export function screwTensionScope(result: WallCheckResult, rearBoardPresent: boolean): ScrewTensionScope {
  const i = result.intermediate;
  // 간격 0 = 피스 체결층 없음(엔진: 수요 0). 값이 없으면 종전 응답이므로 검토한 것으로 본다
  const checked = i.screw_tension_spacing_mm === undefined || i.screw_tension_spacing_mm > 0;
  const partial = checked && i.ch_slot_rear_board === 1 && rearBoardPresent;
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
