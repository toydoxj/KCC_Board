import type { WallCheckResult } from "./api";
import type { CalculationMode } from "./calculation-mode";

// One shared choice of governing height for results, summary and detailed report.
export function governingHeight(result:WallCheckResult) {
  return result.design_case === "non_seismic" ? result.max_height_mm : result.anchor_max_height_mm;
}

export function heightReview(result:WallCheckResult,mode:CalculationMode,spanMm:number) {
  const enabled=result.design_case!=="non_seismic";
  const maximumMm=governingHeight(result);
  const utilization=result.intermediate.anchor_utilization;
  const anchorOk=typeof utilization==="number"&&Number.isFinite(utilization)&&utilization>=0&&utilization<=1;
  const withinHeight=Number.isFinite(spanMm)&&spanMm>0&&maximumMm>0&&spanMm<=maximumMm;
  const overallOk=withinHeight&&(!enabled||anchorOk)&&result.stress_verdict==="O.K"&&result.deflection_verdict==="O.K"&&result.screw_tension_verdict==="O.K";
  return {enabled,maximumMm,anchorOk,withinHeight,overallOk};
}
