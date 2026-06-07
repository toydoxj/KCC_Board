import { CheckCircle2, Ruler, XCircle } from "lucide-react";

import type { WallCheckResult } from "@/lib/api";
import type { CalculationMode } from "@/lib/calculation-mode";

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

  if (mode === "maxHeight") {
    return (
      <div className="grid gap-4">
        <div className="rounded-md border border-primary/40 bg-cyan-50 p-4">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-semibold text-primary">최대 가능 높이</span>
            <Ruler className="h-5 w-5 text-primary" aria-hidden="true" />
          </div>
          <div className="mt-3 text-3xl font-bold text-foreground">
            {numberFormat.format(result.max_height_mm)}
            <span className="ml-1 text-base font-semibold text-muted-foreground">mm</span>
          </div>
          <div className="mt-1 text-xs font-medium text-muted-foreground">
            {numberFormat.format(result.max_height_increment_mm)}mm 단위
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <VerdictBadge label="산정 응력" ok={stressOk} value={result.stress_verdict} />
          <VerdictBadge label="산정 처짐" ok={deflectionOk} value={result.deflection_verdict} />
        </div>
        <div className="grid gap-2 rounded-md border border-border bg-white p-4 shadow-panel">
          <Metric label="응력비" value={result.stress_ratio} suffix="" />
          <Metric label="Mu" value={result.Mu_kNm} suffix="kN·m" />
          <Metric label="Mn" value={result.Mn_kNm} suffix="kN·m" />
          <Metric label="처짐" value={result.deflection_mm} suffix="mm" />
          <Metric label="처짐한계" value={result.deflection_limit_mm} suffix="mm" />
        </div>
        <ReactionMetrics result={result} />
        <div className="grid gap-2 rounded-md border border-border bg-white p-4 shadow-panel">
          <Metric label="중립축" value={result.neutral_axis_mm} suffix="mm" />
          <Metric label="I_full" value={result.I_full_mm4} suffix="mm⁴" />
          <Metric label="η" value={result.eta} suffix="" />
          <Metric label="I_eff(raw)" value={result.intermediate.I_eff_raw_mm4 ?? result.I_eff_mm4} suffix="mm⁴" />
          <Metric label="I_eff 보정" value={result.intermediate.I_eff_correction_factor ?? 1} suffix="" />
          <Metric label="I_eff" value={result.I_eff_mm4} suffix="mm⁴" />
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 gap-3">
        <VerdictBadge label="응력" ok={stressOk} value={result.stress_verdict} />
        <VerdictBadge label="처짐" ok={deflectionOk} value={result.deflection_verdict} />
      </div>
      <div className="grid gap-2 rounded-md border border-border bg-white p-4 shadow-panel">
        <Metric label="응력비" value={result.stress_ratio} suffix="" />
        <Metric label="Mu" value={result.Mu_kNm} suffix="kN·m" />
        <Metric label="Mn" value={result.Mn_kNm} suffix="kN·m" />
        <Metric label="처짐" value={result.deflection_mm} suffix="mm" />
        <Metric label="처짐한계" value={result.deflection_limit_mm} suffix="mm" />
        <Metric label="지진모멘트" value={result.seismic_moment_kNm} suffix="kN·m" />
      </div>
      <ReactionMetrics result={result} />
      <div className="grid gap-2 rounded-md border border-border bg-white p-4 shadow-panel">
        <Metric label="중립축" value={result.neutral_axis_mm} suffix="mm" />
        <Metric label="I_full" value={result.I_full_mm4} suffix="mm⁴" />
        <Metric label="η" value={result.eta} suffix="" />
        <Metric label="I_eff(raw)" value={result.intermediate.I_eff_raw_mm4 ?? result.I_eff_mm4} suffix="mm⁴" />
        <Metric label="I_eff 보정" value={result.intermediate.I_eff_correction_factor ?? 1} suffix="" />
        <Metric label="I_eff" value={result.I_eff_mm4} suffix="mm⁴" />
      </div>
    </div>
  );
}

function ReactionMetrics({ result }: { result: WallCheckResult }) {
  return (
    <div className="grid gap-2 rounded-md border border-border bg-white p-4 shadow-panel">
      <Metric label="반력 L" value={intermediateValue(result, "reaction_L_kN_per_m")} suffix="kN/m" />
      <Metric label="반력 0.7E" value={intermediateValue(result, "reaction_0_7E_kN_per_m")} suffix="kN/m" />
      <Metric
        label="반력 0.75L+0.7E"
        value={intermediateValue(result, "reaction_0_75L_0_7E_kN_per_m")}
        suffix="kN/m"
      />
      <Metric label="필요 반력" value={intermediateValue(result, "reaction_required_kN_per_m")} suffix="kN/m" />
      <Metric label="앵커 성능" value={intermediateValue(result, "anchor_capacity_kN")} suffix="kN/개" />
      <Metric label="앵커 간격" value={intermediateValue(result, "anchor_spacing_mm")} suffix="mm" />
    </div>
  );
}

function intermediateValue(result: WallCheckResult, key: string) {
  return result.intermediate[key] ?? 0;
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
