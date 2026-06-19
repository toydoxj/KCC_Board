export type CalculationMode = "heightCheck" | "maxHeight";
export type StrengthCheckMode = "composite" | "stud_only";

export const calculationModeLabels = {
  heightCheck: "높이 검토",
  maxHeight: "최대높이 산정",
} satisfies Record<CalculationMode, string>;

export const strengthCheckModeLabels = {
  composite: "부분합성",
  stud_only: "STUD만",
} satisfies Record<StrengthCheckMode, string>;
