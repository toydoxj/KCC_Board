import type { ReactNode } from "react";

import type { LayerResult, WallCheckResult } from "@/lib/api";
import { calculationModeLabels, type CalculationMode } from "@/lib/calculation-mode";

export interface ReportBoardSlot {
  label: string;
  kind: string;
  thickness: number | null;
  mass_kg_m2: number | null;
  Fy: number | null;
  Fu: number | null;
  E_GPa: number | null;
}

export interface ReportStud {
  group: string;
  method: string;
  spec: string;
  multiplier: number;
  H: number | null;
  totalH: number | null;
  gapMm: number | null;
  connectionInertiaFactor: number | null;
  sectionModulusDepth: number | null;
  B: number | null;
  t: number | null;
  A: number | null;
  IxRaw: number | null;
  SxRaw: number | null;
  Ix: number | null;
  Sx: number | null;
}

export interface CalculationReportData {
  generatedAt: string;
  calculationMode: CalculationMode;
  rearBoards: ReportBoardSlot[];
  frontBoards: ReportBoardSlot[];
  stud: ReportStud;
  geometry: {
    spacingMm: number;
    spanMm: number;
    deflectionLimitDenom: number;
  };
  loads: {
    horizontalLoadKgM2: number;
    seismicS: number;
    seismicSiteClass: string;
    s5BedrockDepthUnknown: boolean;
    seismicIp: number;
  };
  bolts: {
    outerCount: number;
    middleCount: number;
    innerCount: number;
    outerPitch: number;
    middlePitch: number;
    innerPitch: number;
  };
  result: WallCheckResult;
}

interface CalculationReportProps {
  data: CalculationReportData;
  className?: string;
}

const numberFormat = new Intl.NumberFormat("ko-KR", {
  maximumFractionDigits: 3,
});

const compactFormat = new Intl.NumberFormat("ko-KR", {
  maximumFractionDigits: 6,
});

const dateFormat = new Intl.DateTimeFormat("ko-KR", {
  dateStyle: "medium",
  timeStyle: "short",
});

const studYieldStrength = 275;

export function CalculationReport({ data, className = "" }: CalculationReportProps) {
  const stressOk = data.result.stress_verdict === "O.K";
  const deflectionOk = data.result.deflection_verdict === "O.K";
  const calculationModeLabel = calculationModeLabels[data.calculationMode];
  const heightLabel = data.calculationMode === "maxHeight" ? "산정 높이" : "검토 높이";
  const mnTerms = nominalMomentTerms(data);
  const boardMoment = mnTerms
    .filter((term) => term.type === "board")
    .reduce((sum, term) => sum + term.moment_kNm, 0);
  const studMoment = mnTerms
    .filter((term) => term.type === "stud")
    .reduce((sum, term) => sum + term.moment_kNm, 0);

  return (
    <article className={`report-document bg-white text-slate-950 ${className}`}>
      <header className="border-b-2 border-slate-950 pb-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-normal">석고보드 건식벽체 구조검토 계산서</h1>
            <p className="mt-1 text-sm text-slate-600">{calculationModeLabel} / 부분합성 단면 검토</p>
          </div>
          <div className="text-right text-sm">
            <div className="font-semibold">작성일</div>
            <div>{dateFormat.format(new Date(data.generatedAt))}</div>
          </div>
        </div>
      </header>

      <section className="mt-5 grid gap-3 md:grid-cols-2">
        <ReportBlock title="판정 요약">
          {data.calculationMode === "maxHeight" ? (
            <>
              <div className="rounded-md border border-cyan-700 bg-cyan-50 p-3">
                <div className="text-xs font-medium text-slate-600">최대 가능 높이</div>
                <div className="mt-1 text-2xl font-bold text-cyan-900">
                  {formatNumber(data.result.max_height_mm)} mm
                </div>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <Verdict label="산정 응력" ok={stressOk} value={data.result.stress_verdict} />
                <Verdict label="산정 처짐" ok={deflectionOk} value={data.result.deflection_verdict} />
              </div>
              <div className="mt-3 grid gap-1 text-sm">
                <KeyValue label="계산 방향" value={calculationModeLabel} />
                <KeyValue label="산정 단위" value={`${formatNumber(data.result.max_height_increment_mm)} mm`} />
                <KeyValue label="응력비" value={formatNumber(data.result.stress_ratio)} />
                <KeyValue label="처짐" value={`${formatNumber(data.result.deflection_mm)} mm`} />
              </div>
            </>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2">
                <Verdict label="응력" ok={stressOk} value={data.result.stress_verdict} />
                <Verdict label="처짐" ok={deflectionOk} value={data.result.deflection_verdict} />
              </div>
              <div className="mt-3 grid gap-1 text-sm">
                <KeyValue label="계산 방향" value={calculationModeLabel} />
                <KeyValue label="응력비" value={formatNumber(data.result.stress_ratio)} />
                <KeyValue label="Mu" value={`${formatNumber(data.result.Mu_kNm)} kN·m`} />
                <KeyValue label="Mn" value={`${formatNumber(data.result.Mn_kNm)} kN·m`} />
                <KeyValue label="처짐" value={`${formatNumber(data.result.deflection_mm)} mm`} />
                <KeyValue label="처짐한계" value={`${formatNumber(data.result.deflection_limit_mm)} mm`} />
              </div>
            </>
          )}
        </ReportBlock>

        <ReportBlock title="검토 조건">
          <div className="grid gap-1 text-sm">
            <KeyValue label="스터드" value={`${data.stud.group} / ${data.stud.method} / ${data.stud.spec}`} />
            <KeyValue label="스터드 간격" value={`${formatNumber(data.geometry.spacingMm)} mm`} />
            <KeyValue label={heightLabel} value={`${formatNumber(data.geometry.spanMm)} mm`} />
            <KeyValue label="수평하중" value={`${formatNumber(data.loads.horizontalLoadKgM2)} kg/m²`} />
            <KeyValue label="처짐한계" value={`L/${formatNumber(data.geometry.deflectionLimitDenom)}`} />
            {data.calculationMode === "maxHeight" ? (
              <KeyValue label="높이 산정 단위" value={`${formatNumber(data.result.max_height_increment_mm)} mm`} />
            ) : null}
            <KeyValue label="지진 입력" value={`${data.loads.seismicSiteClass}, S=${formatNumber(data.loads.seismicS)}, Ip=${formatNumber(data.loads.seismicIp)}`} />
          </div>
        </ReportBlock>
      </section>

      <section className="mt-5 grid gap-3 md:grid-cols-2">
        <ReportBlock title="스터드 단면">
          <div className="grid gap-1 text-sm">
            <KeyValue label="시공방식 계수" value={formatNumber(data.stud.multiplier)} />
            <KeyValue label={data.stud.gapMm === null ? "H" : "h(1개)"} value={unitValue(data.stud.H, "mm")} />
            {data.stud.gapMm === null ? null : (
              <>
                <KeyValue label="스터드 간격" value={unitValue(data.stud.gapMm, "mm")} />
                <KeyValue label="전체 높이" value={unitValue(data.stud.totalH, "mm")} />
                <KeyValue
                  label="보정계수"
                  value={data.stud.connectionInertiaFactor === 1 ? "미적용" : formatNullableNumber(data.stud.connectionInertiaFactor)}
                />
                <KeyValue label="S 산정 h" value={unitValue(data.stud.sectionModulusDepth, "mm")} />
              </>
            )}
            <KeyValue label="B" value={unitValue(data.stud.B, "mm")} />
            <KeyValue label="t" value={unitValue(data.stud.t, "mm")} />
            <KeyValue label="A" value={unitValue(data.stud.A, "mm²")} />
            {data.stud.gapMm === null ? (
              <>
                <KeyValue label="Ix" value={unitValue(data.stud.Ix, "mm⁴")} />
                <KeyValue label="Sx" value={unitValue(data.stud.Sx, "mm³")} />
              </>
            ) : (
              <>
                <KeyValue label="Ix" value={unitValue(data.stud.Ix, "mm⁴")} />
                <KeyValue label="Sx" value={unitValue(data.stud.Sx, "mm³")} />
              </>
            )}
          </div>
        </ReportBlock>

        <ReportBlock title="연결볼트 배치">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                <TableHead>구분</TableHead>
                <TableHead>개수</TableHead>
                <TableHead>피치</TableHead>
              </tr>
            </thead>
            <tbody>
              <BoltRow label="3번(외측)" count={data.bolts.outerCount} pitch={data.bolts.outerPitch} />
              <BoltRow label="2번(중간)" count={data.bolts.middleCount} pitch={data.bolts.middlePitch} />
              <BoltRow label="1번(내측)" count={data.bolts.innerCount} pitch={data.bolts.innerPitch} />
            </tbody>
          </table>
        </ReportBlock>
      </section>

      <section className="mt-5">
        <ReportBlock title="보드 구성 및 물성">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                <TableHead>위치</TableHead>
                <TableHead>종류</TableHead>
                <TableHead>두께</TableHead>
                <TableHead>질량</TableHead>
                <TableHead>Fy</TableHead>
                <TableHead>Fu</TableHead>
                <TableHead>E</TableHead>
              </tr>
            </thead>
            <tbody>
              {[...data.rearBoards, ...data.frontBoards].map((board) => (
                <tr key={board.label}>
                  <TableCell>{board.label}</TableCell>
                  <TableCell>{board.kind}</TableCell>
                  <TableCell>{board.thickness === null ? "-" : `${formatNumber(board.thickness)}T`}</TableCell>
                  <TableCell>{unitValue(board.mass_kg_m2, "kg/m²")}</TableCell>
                  <TableCell>{unitValue(board.Fy, "N/mm²")}</TableCell>
                  <TableCell>{unitValue(board.Fu, "N/mm²")}</TableCell>
                  <TableCell>{unitValue(board.E_GPa, "GPa")}</TableCell>
                </tr>
              ))}
            </tbody>
          </table>
        </ReportBlock>
      </section>

      <section className="mt-5">
        <ReportBlock title="계산 결과">
          <div className="grid gap-1 text-sm md:grid-cols-2 md:gap-x-6">
            <KeyValue label="중립축" value={`${formatNumber(data.result.neutral_axis_mm)} mm`} />
            <KeyValue label="I_full" value={`${formatNumber(data.result.I_full_mm4)} mm⁴`} />
            <KeyValue label="합성률 η" value={formatNumber(data.result.eta)} />
            <KeyValue
              label="I_eff(raw)"
              value={`${formatNumber(data.result.intermediate.I_eff_raw_mm4 ?? data.result.I_eff_mm4)} mm⁴`}
            />
            <KeyValue
              label="I_eff 보정"
              value={formatNumber(data.result.intermediate.I_eff_correction_factor ?? 1)}
            />
            <KeyValue label="I_eff" value={`${formatNumber(data.result.I_eff_mm4)} mm⁴`} />
            {data.calculationMode === "maxHeight" ? (
              <KeyValue label="최대 가능 높이" value={`${formatNumber(data.result.max_height_mm)} mm`} />
            ) : null}
            <KeyValue label="지진모멘트" value={`${formatNumber(data.result.seismic_moment_kNm)} kN·m`} />
            <KeyValue label="지진중량 Wp" value={unitValue(data.result.intermediate.seismic_weight_kN, "kN")} />
          </div>
        </ReportBlock>
      </section>

      <section className="mt-5">
        <ReportBlock title="반력 산정">
          <div className="mb-3 grid gap-1 rounded-md bg-slate-50 p-3 text-sm">
            <div>Rh,L = (L × H × B) / 2 / B</div>
            <div>Rh,E = (Fp / 2 × 2) / B</div>
            <div>Rh = max(L, 0.7E, 0.75L + 0.7E)</div>
            <div>앵커 간격 = 앵커 성능 / Rh × 1000</div>
          </div>
          <div className="grid gap-1 text-sm md:grid-cols-2 md:gap-x-6">
            <KeyValue
              label="반력 L"
              value={`${formatNumber(data.result.intermediate.reaction_L_kN_per_m ?? 0)} kN/m`}
            />
            <KeyValue
              label="반력 0.7E"
              value={`${formatNumber(data.result.intermediate.reaction_0_7E_kN_per_m ?? 0)} kN/m`}
            />
            <KeyValue
              label="반력 0.75L+0.7E"
              value={`${formatNumber(data.result.intermediate.reaction_0_75L_0_7E_kN_per_m ?? 0)} kN/m`}
            />
            <KeyValue
              label="필요 반력"
              value={`${formatNumber(data.result.intermediate.reaction_required_kN_per_m ?? 0)} kN/m`}
            />
            <KeyValue
              label="앵커 성능"
              value={`${formatNumber(data.result.intermediate.anchor_capacity_kN ?? 0)} kN/개`}
            />
            <KeyValue
              label="앵커 간격"
              value={`${formatNumber(data.result.intermediate.anchor_spacing_mm ?? 0)} mm`}
            />
          </div>
        </ReportBlock>
      </section>

      <section className="mt-5">
        <ReportBlock title="Mn 산정 상세">
          <div className="mb-3 grid gap-1 rounded-md bg-slate-50 p-3 text-sm">
            <div className="font-semibold">Mn = ΣM보드 + M스터드</div>
            <div>M보드,i = |min(Pn,i, Vc,i) × d_i| × 10^-3</div>
            <div>M스터드 = Fy,stud × S스터드 × 10^-6, S스터드 = I_stud / h_ref × 2</div>
            {data.stud.gapMm === null ? null : (
              <>
                <div>
                  I스터드 = 2 × [A0 × (h + {formatNumber(data.stud.gapMm)} / 2)^2 + Ix0]
                </div>
              </>
            )}
            <div>
              = {formatNumber(boardMoment)} + {formatNumber(studMoment)} = {formatNumber(data.result.Mn_kNm)} kN·m
            </div>
          </div>
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                <TableHead>요소</TableHead>
                <TableHead>적용식</TableHead>
                <TableHead>Pn</TableHead>
                <TableHead>Vc</TableHead>
                <TableHead>적용힘</TableHead>
                <TableHead>d 또는 S</TableHead>
                <TableHead>Mn 기여</TableHead>
              </tr>
            </thead>
            <tbody>
              {mnTerms.map((term) => (
                <MnTermRow key={term.name} term={term} />
              ))}
            </tbody>
          </table>
        </ReportBlock>
      </section>

      <section className="mt-5">
        <ReportBlock title="층별 중간값">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                <TableHead>층</TableHead>
                <TableHead>구분</TableHead>
                <TableHead>y</TableHead>
                <TableHead>A'</TableHead>
                <TableHead>d</TableHead>
                <TableHead>I</TableHead>
                <TableHead>축강도</TableHead>
                <TableHead>전단누계</TableHead>
              </tr>
            </thead>
            <tbody>
              {data.result.layers.map((layer) => (
                <LayerRow key={layer.name} layer={layer} />
              ))}
            </tbody>
          </table>
        </ReportBlock>
      </section>
    </article>
  );
}

function ReportBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-md border border-slate-300">
      <h2 className="border-b border-slate-300 bg-slate-100 px-3 py-2 text-sm font-bold">{title}</h2>
      <div className="p-3">{children}</div>
    </div>
  );
}

function Verdict({ label, ok, value }: { label: string; ok: boolean; value: string }) {
  return (
    <div className={ok ? "rounded-md border border-emerald-700 bg-emerald-50 p-3" : "rounded-md border border-red-700 bg-red-50 p-3"}>
      <div className="text-xs font-medium text-slate-600">{label}</div>
      <div className={ok ? "mt-1 text-xl font-bold text-emerald-800" : "mt-1 text-xl font-bold text-red-800"}>
        {value}
      </div>
    </div>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-2 border-b border-slate-200 py-1 last:border-b-0">
      <span className="text-slate-600">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  );
}

function BoltRow({ label, count, pitch }: { label: string; count: number; pitch: number }) {
  return (
    <tr>
      <TableCell>{label}</TableCell>
      <TableCell>{formatNumber(count)}개</TableCell>
      <TableCell>{formatNumber(pitch)} mm</TableCell>
    </tr>
  );
}

function LayerRow({ layer }: { layer: LayerResult }) {
  return (
    <tr>
      <TableCell>{layer.name}</TableCell>
      <TableCell>{layer.layer_type === "stud" ? "스터드" : "보드"}</TableCell>
      <TableCell>{formatNumber(layer.y_centroid_mm)}</TableCell>
      <TableCell>{formatNumber(layer.transformed_area_mm2)}</TableCell>
      <TableCell>{formatNumber(layer.distance_to_neutral_axis_mm)}</TableCell>
      <TableCell>{formatNumber(layer.inertia_about_neutral_axis_mm4)}</TableCell>
      <TableCell>{formatNumber(layer.axial_strength_kN)}</TableCell>
      <TableCell>{formatNumber(layer.cumulative_shear_kN)}</TableCell>
    </tr>
  );
}

interface NominalMomentTerm {
  name: string;
  type: "board" | "stud";
  expression: string;
  axialStrength_kN: number | null;
  cumulativeShear_kN: number | null;
  appliedForce_kN: number | null;
  distanceOrSection: number;
  distanceOrSectionUnit: string;
  moment_kNm: number;
}

function MnTermRow({ term }: { term: NominalMomentTerm }) {
  return (
    <tr>
      <TableCell>{term.name}</TableCell>
      <TableCell>{term.expression}</TableCell>
      <TableCell>{unitValue(term.axialStrength_kN, "kN")}</TableCell>
      <TableCell>{unitValue(term.cumulativeShear_kN, "kN")}</TableCell>
      <TableCell>{unitValue(term.appliedForce_kN, "kN")}</TableCell>
      <TableCell>{unitValue(term.distanceOrSection, term.distanceOrSectionUnit)}</TableCell>
      <TableCell>{unitValue(term.moment_kNm, "kN·m")}</TableCell>
    </tr>
  );
}

function nominalMomentTerms(data: CalculationReportData) {
  const sectionModulusDepth = data.stud.sectionModulusDepth ?? data.stud.H ?? 0;
  return data.result.layers.map<NominalMomentTerm>((layer) => {
    if (layer.layer_type === "board") {
      const appliedForce = Math.min(layer.axial_strength_kN, layer.cumulative_shear_kN);
      return {
        name: layer.name,
        type: "board",
        expression: "|min(Pn,Vc)×d|×10^-3",
        axialStrength_kN: layer.axial_strength_kN,
        cumulativeShear_kN: layer.cumulative_shear_kN,
        appliedForce_kN: appliedForce,
        distanceOrSection: Math.abs(layer.distance_to_neutral_axis_mm),
        distanceOrSectionUnit: "mm",
        moment_kNm: Math.abs(appliedForce * layer.distance_to_neutral_axis_mm * 1e-3),
      };
    }

    const sectionModulus = sectionModulusDepth > 0 ? (layer.inertia_about_neutral_axis_mm4 / sectionModulusDepth) * 2.0 : 0;
    return {
      name: layer.name,
      type: "stud",
      expression: "Fy,stud×S×10^-6",
      axialStrength_kN: null,
      cumulativeShear_kN: null,
      appliedForce_kN: null,
      distanceOrSection: sectionModulus,
      distanceOrSectionUnit: "mm³",
      moment_kNm: studYieldStrength * sectionModulus * 1e-6,
    };
  });
}

function TableHead({ children }: { children: ReactNode }) {
  return <th className="border border-slate-300 bg-slate-100 px-2 py-1 text-left font-semibold">{children}</th>;
}

function TableCell({ children }: { children: ReactNode }) {
  return <td className="border border-slate-300 px-2 py-1 align-top">{children}</td>;
}

function unitValue(value: number | null | undefined, unit: string) {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${formatNumber(value)} ${unit}`;
}

function formatNullableNumber(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "-";
  }
  return formatNumber(value);
}

function formatNumber(value: number) {
  const formatter = Math.abs(value) < 1 && value !== 0 ? compactFormat : numberFormat;
  return formatter.format(value);
}
