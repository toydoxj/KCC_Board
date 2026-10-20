import { CheckCircle2, Ruler, XCircle } from "lucide-react";

import type { WallCheckResult } from "@/lib/api";
import { strengthCheckModeLabels, type CalculationMode } from "@/lib/calculation-mode";
import { ResultNotices } from "@/components/result-notices";

interface ResultPanelProps {
  result: WallCheckResult | null;
  mode: CalculationMode;
}

const numberFormat = new Intl.NumberFormat("ko-KR", {
  maximumFractionDigits: 3,
});

export function ResultPanel({ result, mode }: ResultPanelProps) {
  if (!result) {
    return (
      <div className="rounded-md border border-dashed border-border bg-white p-5 text-sm text-muted-foreground">
        계산 결과가 여기에 표시됩니다.
      </div>
    );
  }

  const stressOk = result.stress_verdict === "O.K";
  const deflectionOk = result.deflection_verdict === "O.K";
  const screwTensionOk = result.screw_tension_verdict === "O.K";
  const designCaseLabel = result.design_case === "non_seismic" ? "비내진" : "내진";
  const strengthCheckModeLabel = strengthCheckModeLabels[result.strength_check_mode] ?? result.strength_check_mode;
  const isSeismic = result.design_case !== "non_seismic";
  const isHeightSearchMode = mode === "maxHeight" || mode === "anchorHeight";
  const heightSearchLabel = mode === "anchorHeight" ? "앵커 기준 최대높이" : "최대 가능 높이";
  const heightSearchValue = mode === "anchorHeight" ? result.anchor_max_height_mm : result.max_height_mm;

  if (isHeightSearchMode) {
    return (
      <div className="grid gap-4">
        <div className="rounded-md border border-primary/40 bg-cyan-50 p-4">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-semibold text-primary">{heightSearchLabel}</span>
            <Ruler className="h-5 w-5 text-primary" aria-hidden="true" />
          </div>
          <div className="mt-3 text-3xl font-bold text-foreground">
            {numberFormat.format(heightSearchValue)}
            <span className="ml-1 text-base font-semibold text-muted-foreground">mm</span>
          </div>
          <div className="mt-1 text-xs font-medium text-muted-foreground">
            {numberFormat.format(result.max_height_increment_mm)}mm 단위
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <VerdictBadge label="산정 응력" ok={stressOk} value={result.stress_verdict} />
          <VerdictBadge label="산정 처짐" ok={deflectionOk} value={result.deflection_verdict} />
          <VerdictBadge label="피스 인장" ok={screwTensionOk} value={result.screw_tension_verdict} />
        </div>
        <ResultNotices notices={result.notices ?? []} />
        <div className="grid gap-2 rounded-md border border-border bg-white p-4 shadow-panel">
          <CaseMetric label="검토 CASE" value={designCaseLabel} />
          <CaseMetric label="강도 기준" value={strengthCheckModeLabel} />
          <Metric label="응력비" value={result.stress_ratio} suffix="" />
          <Metric label="Mu" value={result.Mu_kNm} suffix="kN·m" />
          <Metric label="Mn(적용)" value={result.Mn_kNm} suffix="kN·m" />
          <Metric label="Mn(부분합성)" value={intermediateValue(result, "Mn_composite_kNm")} suffix="kN·m" />
          <Metric label="Mn(STUD)" value={intermediateValue(result, "Mn_stud_only_kNm")} suffix="kN·m" />
          <Metric label="처짐" value={result.deflection_mm} suffix="mm" />
          <Metric label="처짐한계" value={result.deflection_limit_mm} suffix="mm" />
        </div>
        <LoadCombinationMetrics result={result} isSeismic={isSeismic} />
        <ReactionMetrics result={result} />
        <ScrewTensionMetrics result={result} />
        <div className="grid gap-2 rounded-md border border-border bg-white p-4 shadow-panel">
          <Metric label="중립축" value={result.neutral_axis_mm} suffix="mm" />
          <Metric label="I_full" value={result.I_full_mm4} suffix="mm⁴" />
          <Metric label="η" value={result.eta} suffix="" />
          <Metric label="I_eff(raw)" value={result.intermediate.I_eff_raw_mm4 ?? result.I_eff_mm4} suffix="mm⁴" />
          <Metric label="I_eff 보정" value={result.intermediate.I_eff_correction_factor ?? 1} suffix="" />
          <Metric label="피스 활용도 u/u_ref" value={intermediateValue(result, "screw_utilization_ratio")} suffix="" />
          <Metric label="강성 하중보정" value={intermediateValue(result, "stiffness_load_factor")} suffix="" />
          <Metric label="I_eff" value={result.I_eff_mm4} suffix="mm⁴" />
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-3 gap-3">
        <VerdictBadge label="응력" ok={stressOk} value={result.stress_verdict} />
        <VerdictBadge label="처짐" ok={deflectionOk} value={result.deflection_verdict} />
        <VerdictBadge label="피스 인장" ok={screwTensionOk} value={result.screw_tension_verdict} />
      </div>
      <ResultNotices notices={result.notices ?? []} />
      <div className="grid gap-2 rounded-md border border-border bg-white p-4 shadow-panel">
        <CaseMetric label="검토 CASE" value={designCaseLabel} />
        <CaseMetric label="강도 기준" value={strengthCheckModeLabel} />
        <Metric label="응력비" value={result.stress_ratio} suffix="" />
        <Metric label="Mu" value={result.Mu_kNm} suffix="kN·m" />
        <Metric label="Mn(적용)" value={result.Mn_kNm} suffix="kN·m" />
        <Metric label="Mn(부분합성)" value={intermediateValue(result, "Mn_composite_kNm")} suffix="kN·m" />
        <Metric label="Mn(STUD)" value={intermediateValue(result, "Mn_stud_only_kNm")} suffix="kN·m" />
        <Metric label="처짐" value={result.deflection_mm} suffix="mm" />
        <Metric label="처짐한계" value={result.deflection_limit_mm} suffix="mm" />
        {isSeismic ? <Metric label="지진모멘트" value={result.seismic_moment_kNm} suffix="kN·m" /> : null}
      </div>
      <LoadCombinationMetrics result={result} isSeismic={isSeismic} />
      <ReactionMetrics result={result} />
      <ScrewTensionMetrics result={result} />
      <div className="grid gap-2 rounded-md border border-border bg-white p-4 shadow-panel">
        <Metric label="중립축" value={result.neutral_axis_mm} suffix="mm" />
        <Metric label="I_full" value={result.I_full_mm4} suffix="mm⁴" />
        <Metric label="η" value={result.eta} suffix="" />
        <Metric label="I_eff(raw)" value={result.intermediate.I_eff_raw_mm4 ?? result.I_eff_mm4} suffix="mm⁴" />
        <Metric label="I_eff 보정" value={result.intermediate.I_eff_correction_factor ?? 1} suffix="" />
          <Metric label="피스 활용도 u/u_ref" value={intermediateValue(result, "screw_utilization_ratio")} suffix="" />
          <Metric label="강성 하중보정" value={intermediateValue(result, "stiffness_load_factor")} suffix="" />
        <Metric label="I_eff" value={result.I_eff_mm4} suffix="mm⁴" />
      </div>
    </div>
  );
}

function LoadCombinationMetrics({ result, isSeismic }: { result: WallCheckResult; isSeismic: boolean }) {
  return (
    <div className="grid gap-2 rounded-md border border-border bg-white p-4 shadow-panel">
      <Metric label="M(L)" value={intermediateValue(result, "moment_L_kNm")} suffix="kN·m" />
      {isSeismic ? <Metric label="M(0.7E)" value={intermediateValue(result, "moment_0_7E_kNm")} suffix="kN·m" /> : null}
      {isSeismic ? (
        <Metric
          label="M(0.75L+0.75(0.7E))"
          value={intermediateValue(result, "moment_0_75L_0_525E_kNm")}
          suffix="kN·m"
        />
      ) : null}
      <Metric label="Mu" value={result.Mu_kNm} suffix="kN·m" />
      <Metric label="연직하중" value={intermediateValue(result, "vertical_load_kN_m")} suffix="kN/m" />
    </div>
  );
}

function ScrewTensionMetrics({ result }: { result: WallCheckResult }) {
  return (
    <div className="grid gap-2 rounded-md border border-border bg-white p-4 shadow-panel">
      <Metric label="피스 전단 스터드측(tilting·지압/Ω)" value={intermediateValue(result, "screw_stud_side_shear_N")} suffix="N/개" />
      <Metric label="피스 인장 횡압력" value={intermediateValue(result, "screw_tension_pressure_kN_m2")} suffix="kN/m²" />
      <Metric label="피스 부담 피치" value={intermediateValue(result, "screw_tension_spacing_mm")} suffix="mm" />
      <Metric label="피스 인장 T" value={intermediateValue(result, "screw_tension_demand_N")} suffix="N/개" />
      <Metric label="풀아웃 Pnot/Ω" value={intermediateValue(result, "screw_pullout_allowable_N")} suffix="N/개" />
      <Metric label="풀아웃 사용률" value={intermediateValue(result, "screw_pullout_utilization")} suffix="" />
      <Metric label="풀스루 허용(입력/Ω)" value={intermediateValue(result, "screw_pull_through_allowable_N")} suffix="N/개" />
      <Metric label="풀스루 사용률" value={intermediateValue(result, "screw_pull_through_utilization")} suffix="" />
    </div>
  );
}

function ReactionMetrics({ result }: { result: WallCheckResult }) {
  if (result.design_case === "non_seismic") {
    return null;
  }

  return (
    <div className="grid gap-2 rounded-md border border-border bg-white p-4 shadow-panel">
      <Metric label="반력 L" value={intermediateValue(result, "reaction_L_kN_per_m")} suffix="kN/m" />
      <Metric label="반력 0.7E" value={intermediateValue(result, "reaction_0_7E_kN_per_m")} suffix="kN/m" />
      <Metric
        label="반력 0.75L+0.75(0.7E)"
        value={intermediateValue(result, "reaction_0_75L_0_525E_kN_per_m")}
        suffix="kN/m"
      />
      <Metric label="필요 반력" value={intermediateValue(result, "reaction_required_kN_per_m")} suffix="kN/m" />
      <Metric label="앵커 성능" value={intermediateValue(result, "anchor_capacity_kN")} suffix="kN/개" />
      <Metric label="검토 앵커 간격" value={intermediateValue(result, "anchor_spacing_mm")} suffix="mm" />
      <Metric label="허용 앵커 간격" value={intermediateValue(result, "anchor_allowable_spacing_mm")} suffix="mm" />
      <Metric label="앵커 저항" value={intermediateValue(result, "anchor_capacity_kN_per_m")} suffix="kN/m" />
      <Metric label="앵커 사용률" value={intermediateValue(result, "anchor_utilization")} suffix="" />
    </div>
  );
}

function intermediateValue(result: WallCheckResult, key: string) {
  return result.intermediate[key] ?? Number.NaN;
}

function VerdictBadge({ label, ok, value }: { label: string; ok: boolean; value: string }) {
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <div className={ok ? "rounded-md bg-success p-4 text-success-foreground" : "rounded-md bg-destructive p-4 text-destructive-foreground"}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium">{label}</span>
        <Icon className="h-5 w-5" aria-hidden="true" />
      </div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
    </div>
  );
}

function Metric({ label, value, suffix }: { label: string; value: number; suffix: string }) {
  if (!Number.isFinite(value)) {
    return null;
  }
  return (
    <div className="grid grid-cols-[1fr_auto] items-baseline gap-3 border-b border-border/70 py-2 last:border-b-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-right text-sm font-semibold text-foreground">
        {numberFormat.format(value)}
        {suffix ? <span className="ml-1 text-xs font-medium text-muted-foreground">{suffix}</span> : null}
      </span>
    </div>
  );
}

function CaseMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-baseline gap-3 border-b border-border/70 py-2 last:border-b-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-right text-sm font-semibold text-foreground">{value}</span>
    </div>
  );
}
