export type CalculationMode = "heightCheck" | "maxHeight";

export const calculationModeLabels = {
  heightCheck: "높이 검토",
  maxHeight: "최대높이 산정",
} satisfies Record<CalculationMode, string>;
