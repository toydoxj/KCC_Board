import type { WallCheckResult } from "@/lib/api";

// 결과 화면·계산서 공통 안내 문구 (1차 D-2 → 2차 심사의견 F-2 개정)
export const resultScopeDisclaimer =
  "[주의] 본 결과는 이론 계산값임. 실험으로 검증된 범위는 KCC 11종 시험 시편의 구성(스터드 형식·규격, 보드 종류·두께·겹수, 스터드 간격 300·450·600 mm)과 시험 높이 2.4 m에 한정되며, 산정된 허용높이는 시험 높이를 초과하는 외삽값임. 시험 범위 외 구성(보드 종류·두께·겹수·간격·시공방식의 변경)은 실험으로 직접 검증되지 않았으므로 결과 적용 시 설계자(구조기술자)의 공학적 판단과 확인이 필요함. 합성률 η 및 보정계수 R의 수치 적정성은 기술인증 범위에 포함되지 않음.";

// 계산서(요약·상세) 전용 제품 적용 범위 문구
export const productScopeNotice =
  "본 프로그램의 검토 결과는 KCC 석고보드 및 KCC 스터드 제품에 한하여 적용함.";

// 시험 구성 대조 항목 키(엔진 TESTED_FIELD_*) → 한글 표기
const testedFieldLabels: Record<string, string> = {
  stud_type: "스터드 형식",
  stud_spec: "스터드 규격",
  stud_method: "시공방식",
  board_kind: "보드 종류",
  board_thickness: "보드 두께",
  board_layers: "보드 겹수",
  spacing: "스터드 간격",
};

export interface TestedConfigurationStatus {
  matched: boolean;
  text: string;
}

// 시험 시편 구성 대조 배지 문구 (2차 심사의견 A-1). 판정에는 영향하지 않는다
export function testedConfigurationStatus(result: WallCheckResult): TestedConfigurationStatus | null {
  const match = result.intermediate.tested_configuration_match;
  if (match === undefined) {
    return null;
  }
  const heightM = (result.intermediate.tested_height_mm ?? 2400) / 1000;
  if (match === 1) {
    const no = result.intermediate.matched_specimen_no;
    return { matched: true, text: `입력 구성은 시험 시편 No.${no}(높이 ${heightM} m)와 일치함` };
  }
  const fields = (result.tested_configuration_mismatch_fields ?? []).map((key) => testedFieldLabels[key] ?? key);
  return { matched: false, text: `입력 구성은 시험 시편과 일치하지 않음 — 이론 산정값 (차이: ${fields.join(", ")})` };
}
