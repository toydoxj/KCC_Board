"use client";

import { type ChangeEvent, type ReactNode, useState } from "react";
import type { FieldErrors, UseFormRegister, UseFormSetValue } from "react-hook-form";
import { Calculator, RotateCcw } from "lucide-react";
import { StudGallery } from "./stud-gallery";
import type { AnchorProduct, StudSection } from "@/lib/api";
import type { CheckFormValues } from "@/app/page";
import { ANCHOR_CUSTOM_ID, anchorProductLabel, groupAnchorProductsByFamily, type AnchorClientResult } from "@/lib/anchor";
import { Field, inputClassName } from "@/components/ui/field";
import { Button } from "@/components/ui/button";
import type { CalculationMode } from "@/lib/calculation-mode";
import { displayStudGroup, boardColors } from "@/lib/visual-assets";
import { APP_VERSION } from "@/lib/app-info";

type Option = {value: string; label: string};
interface Props {
  register: UseFormRegister<CheckFormValues>;
  setValue: UseFormSetValue<CheckFormValues>;
  values: Partial<CheckFormValues>;
  errors: FieldErrors<CheckFormValues>;
  groups: Option[]; methods: Option[]; specs: Option[];
  siteClasses: Option[];
  onStudGroupChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  onModeChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onReset: () => void;
  busy: boolean;
  submitLabel: string;
  mirrorRear: boolean;
  onMirrorChange: (checked: boolean) => void;
  canMirror: boolean;
  notice: ReactNode;
  frontSlots: ReactNode[];
  rearSlots: ReactNode[];
  frontCount: number;
  rearCount: number;
  preview: ReactNode;
  stud?: StudSection;
  anchor: AnchorProps;
}

// 런너 고정 앵커 제품 선택 상태. 조회(resolution)는 page.tsx가 서버와 같은 규칙으로 계산해 넘긴다
interface AnchorProps {
  products: AnchorProduct[];
  capN: number | null;
  capNote: string;
  selected?: AnchorProduct;
  isCustom: boolean;
  embedmentOptions: number[];
  fcOptions: number[];
  resolution: AnchorClientResult | null;
  onProductChange: (anchorId: string) => void;
  onEmbedmentChange: (embedmentMm: number) => void;
  onFcChange: (fc: number | null) => void;
}

const modes: {value: CalculationMode; label: string; detail: string}[] = [
  {value: "maxHeight", label: "최대높이 산정", detail: "선택 사양의 최대 가능 높이 산정"},
  {value: "anchorHeight", label: "런너 고정못 간격에 따른 최대높이", detail: "선택 간격을 만족하는 최대높이 산정"},
  {value: "heightCheck", label: "현장 높이 검토", detail: "현장 계획 높이의 적합성 확인"},
];

// Step 04 설계하중·처짐한계 참고설명 (2차 심사의견 B-2). helper와 라벨 title 툴팁에 같은 문구를 쓴다
const step04Help = {
  span: "상·하부 런너 지지점 간 순높이(바닥~슬래브 하부). 부분높이·개구부 벽체는 적용 범위 외",
  // 0.36·0.48 kN/m² 프리셋 출처 확인 필요
  liveLoad: "0.25 kN/m²: KDS 41 12 00 (3.7.2) 내벽 횡하중 최소값(높이 1.8 m 이상 내벽). 0.36·0.48 kN/m²: 상향 적용 시 선택값",
  deflection: "L/240: 석고보드 마감 일반 한계(기본값). L/300·L/360: 타일·석재 등 취성 마감 또는 발주처 요구 시",
  verticalLoad: "벽체 상부에 작용하는 연직하중(kN/m). 비내력 칸막이벽은 통상 0",
  seismicS: "지진구역 I: 0.22, 지진구역 II: 0.14 (KDS 41 17 00)",
  siteClass: "단주기 지반증폭계수 Fa 자동 산정(KDS 41 17 00 표 4.2-1)",
  s5: "S5 지반에서 기반암 깊이 불분명 시 Fa 1.1배",
  ip: "1.0: 일반 비구조요소 / 1.5: 피난경로·위험물·중요도(특) 건축물",
  zOverH: "z: 벽체 설치 층 높이, h: 건물 평균 지붕 높이. 모르면 1.0(최상층, 안전측)",
} as const;

// 비구조요소 지진력 산정식 요약. KDS 41 17 00 18장 Fp 식·상하한 조항 번호, ap·Rp 표 번호 출처 확인 필요(OI-02)
const seismicFormulaSummary = "Fp = 0.4·ap·SDS·Ip·Wp·(1+2z/h)/Rp (ap = 1.0, Rp = 2.5), 0.3·SDS·Ip·Wp ≤ Fp ≤ 1.6·SDS·Ip·Wp";

// 런너 고정못 허용내력 입력 안내 (2차 심사의견 D-1)
const anchorCapacityHelp = "매입깊이·모재(콘크리트) 강도·직경 조건이 반영된 제조사 시험성적서의 허용내력을 입력합니다. 프리셋 0.4/0.2 kN은 예시값입니다.";
const anchorProductHelp = "제품·매입깊이·콘크리트 강도를 고르면 제조사 Data Sheet·ICC-ES 허용 전단값이 자동 입력됩니다. 국내 인증값이 아니므로 현장 조건이 다르면 사용자 정의로 시험성적서 값을 입력하십시오.";
const anchorRecBasisNote = "제조사 권장하중 — 안전율 미기재(확인 필요)";
// 기본 제품(is_default) 안내: 기본 매입깊이 27 mm → 0.4 kN(2026-11-09 사용자 확정). 값은 시드 default_embedment_mm·표에서 오고 여기서는 문구만 둔다
const anchorDefaultProductNote = "기본값 0.4 kN은 Hilti X-U P8 매입 hET ≥ 27 mm(X-U 32 P8 이상) 기준임. 매입이 22 mm이면 0.3 kN(hET 22 mm)을 선택할 것.";
const anchorNoStrengthLabel = "해당 없음(강도 무관)";

function formatN(value: number) {
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(value);
}

function formatKn(value: number) {
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 3 }).format(value);
}

function mmOrDash(value: number | null) {
  return value === null ? "—" : `${value} mm`;
}

function Step({number, title, description, children}: {number: string; title: string; description: string; children: ReactNode}) {
  return <section className="input-step"><div className="step-heading"><span className="step-number">{number}</span><h2>{title}</h2><span className="required-mark">필수 *</span></div><p className="step-description">{description}</p>{children}</section>;
}

export function InputWorkspace(p: Props) {
  const {register, values, errors} = p;
  const seismic = values.designCase !== "non_seismic";
  const maxPly = Math.max(p.frontCount, p.rearCount);
  const [gallery,setGallery]=useState<"types"|"methods"|null>(null);
  const [custom,setCustom]=useState<Record<string,boolean>>({});
  const group = values.studGroup ?? "C-STUD";
  // CH·I-STUD는 후면 고정 보드(300 mm·4개)가 있어 일면마감 1P 단독 규칙 대상이 아니다
  const hasFixedRear = group.replace(/\s/g, "").toUpperCase().startsWith("CH-STUD") || group.replace(/\s/g, "").toUpperCase() === "I-STUD";
  const oneSidedSinglePly = !hasFixedRear && p.frontCount + p.rearCount === 1;
  const method = values.studMethod ?? "기본";


  function numberField(name: keyof CheckFormValues, label: string, step = "1", extra: {min?: number; max?: number; readOnly?: boolean; help?: string; emptyAsNaN?: boolean} = {}) {
    const {help, emptyAsNaN, ...inputExtra} = extra;
    // emptyAsNaN: 빈 입력을 0이 아닌 NaN으로 넘겨 zod 검증 오류로 처리한다(빈 값이 0으로 바뀌면 결과가 달라지는 항목)
    const registration = emptyAsNaN ? register(name, {setValueAs: (v: unknown) => (v === "" || v === null || v === undefined ? Number.NaN : Number(v))}) : register(name);
    return <Field label={label} error={errors[name]?.message} help={help}><input className={inputClassName} type="number" step={step} {...registration} {...inputExtra} aria-label={label}/></Field>;
  }

  function preset(name:keyof CheckFormValues,label:string,options:number[],format:(v:number)=>string,step="any",extra: {min?:number;max?:number;disabled?:boolean;help?:string}={}) {
    const value=Number(values[name]);
    const customKey=name==="boltPitchInner"?`${name}:${(p.frontCount===1&&p.rearCount===1)||oneSidedSinglePly?"single":"multi"}`:name;
    const isCustom=custom[customKey]||!options.includes(value);
    return <div className="preset-field"><label htmlFor={name+"-select"} title={extra.help}>{label}</label>
      <input type="hidden" {...register(name)}/>
      <select id={name+"-select"} aria-label={label} className={inputClassName} value={extra.disabled?"not-applicable":isCustom?"custom":String(value)} disabled={extra.disabled} onChange={e=>{
        setCustom(c=>({...c,[customKey]:e.target.value==="custom"}));
        if(e.target.value!=="custom")p.setValue(name,Number(e.target.value),{shouldDirty:true,shouldValidate:true});
      }}>{extra.disabled?<option value="not-applicable">미적용</option>:<>{options.map(v=><option key={v} value={v}>{format(v)}</option>)}<option value="custom">사용자 정의</option></>}</select>
      {!extra.disabled&&isCustom&&<input type="number" step={step} min={extra.min??(step==="1"?1:undefined)} max={extra.max} className={inputClassName} aria-label={label+" 사용자 정의"} value={values[name] as number??""} onChange={e=>p.setValue(name,e.target.value===""?"":Number(e.target.value),{shouldDirty:true,shouldValidate:true})}/>}
      {!extra.disabled&&errors[name]?.message&&<span className="text-xs text-destructive">{errors[name]?.message}</span>}
      {extra.help&&<p className="helper">{extra.help}</p>}
    </div>;
  }

  function renderAnchorSection() {
    const a = p.anchor;
    const product = a.selected;
    const resolution = a.resolution;
    const resolved = resolution && resolution.ok ? resolution.value : null;
    const resolutionError = resolution && !resolution.ok ? resolution.message : null;
    const selectedProductId = values.anchorProductId ?? (product?.anchor_id ?? ANCHOR_CUSTOM_ID);
    const embedmentValue = values.anchorEmbedmentMm === undefined || values.anchorEmbedmentMm === null ? "" : String(values.anchorEmbedmentMm);
    const fcValue = values.anchorConcreteFcMPa === undefined || values.anchorConcreteFcMPa === null ? "" : String(values.anchorConcreteFcMPa);
    const noStrength = !a.isCustom && a.fcOptions.length === 0;
    const anchorSpacing = Number(values.anchorSpacingMm);
    const minSpacingWarning =
      !a.isCustom && product?.min_spacing_mm !== null && product?.min_spacing_mm !== undefined && anchorSpacing < product.min_spacing_mm
        ? `선택한 런너 고정못 간격 ${anchorSpacing} mm는 제품 최소 간격 ${product.min_spacing_mm} mm보다 작습니다. 제조사 기술자료를 확인하십시오.`
        : null;

    return <div className="runner-section">
      <div className="subheading"><h3>런너 고정못</h3></div>
      <div className="field-grid two">
        <Field label="앵커 제품" help={anchorProductHelp}>
          <select aria-label="앵커 제품" className={inputClassName} value={selectedProductId} disabled={a.products.length===0} onChange={e=>a.onProductChange(e.target.value)}>
            {a.products.length===0&&<option value={selectedProductId}>자재 DB 로딩 중…</option>}
            {groupAnchorProductsByFamily(a.products).map(group=><optgroup key={group.family} label={group.label}>{group.items.map(item=><option key={item.anchor_id} value={item.anchor_id}>{item.family==="custom"?item.product:anchorProductLabel(item)}</option>)}</optgroup>)}
          </select>
        </Field>
        <Field label="매입깊이 hET (mm)" help="hET: 콘크리트 모재 안의 유효 매입깊이. 제품 허용하중 표의 값만 선택할 수 있습니다.">
          <select aria-label="매입깊이 hET (mm)" className={inputClassName} value={embedmentValue} disabled={a.isCustom||a.embedmentOptions.length===0} onChange={e=>a.onEmbedmentChange(Number(e.target.value))}>
            {a.isCustom?<option value="">—</option>:a.embedmentOptions.map(v=><option key={v} value={v}>{v} mm</option>)}
          </select>
        </Field>
      </div>
      <div className="field-grid two">
        <Field label="콘크리트 강도 f'c (MPa)" help="ICC-ES 허용하중은 콘크리트 강도별로 다릅니다. 제조사 권장하중(rec) 제품은 강도 무관입니다.">
          <select aria-label="콘크리트 강도 f'c (MPa)" className={inputClassName} value={noStrength?"":fcValue} disabled={a.isCustom||noStrength} onChange={e=>a.onFcChange(e.target.value===""?null:Number(e.target.value))}>
            {a.isCustom?<option value="">—</option>:noStrength?<option value="">{anchorNoStrengthLabel}</option>:a.fcOptions.map(v=><option key={v} value={v}>{v} MPa</option>)}
          </select>
        </Field>
        <div className="grid gap-1.5 text-sm">
          <span title={a.capNote}>내진 전단 상한 {a.capN===null?"":`${formatN(a.capN)} N`} 적용</span>
          <label className="checkbox-field" title={a.capNote}><input type="checkbox" disabled={a.isCustom} {...register("anchorApplySeismicCap")}/>{a.capN===null?"상한 적용":`허용 전단 ≤ ${formatN(a.capN)} N/개 적용`}</label>
          <span className="helper block">{a.capNote||"ICC-ES ESR 공통: SDC D·E·F 런너 고정 허용 전단 상한. 국내 적용은 참고 수준(확인 필요)"}</span>
        </div>
      </div>
      <div className="field-grid two">
        {a.isCustom
          ? preset("anchorCapacityKn","런너 고정못 허용내력 (제조사 설계값, kN/개)",[0.4,0.2],v=>`${v} kN/개`,"any",{help:anchorCapacityHelp})
          : <Field label="런너 고정못 허용내력 (제조사 설계값, kN/개)" error={errors.anchorCapacityKn?.message} help="제품 허용하중 표에서 자동 입력된 값입니다. 직접 입력하려면 앵커 제품을 '사용자 정의'로 바꾸십시오.">
              <input type="hidden" {...register("anchorCapacityKn")}/>
              <input className={inputClassName+" bg-slate-100 text-slate-700 cursor-not-allowed"} aria-label="런너 고정못 허용내력 (제조사 설계값, kN/개)" value={values.anchorCapacityKn===undefined||values.anchorCapacityKn===null||Number.isNaN(Number(values.anchorCapacityKn))?"":`${formatKn(Number(values.anchorCapacityKn))} kN/개`} readOnly/>
            </Field>}
        <Field label="런너 고정못 간격 (mm)" error={errors.anchorSpacingMm?.message}><select aria-label="런너 고정못 간격 (mm)" className={inputClassName} {...register("anchorSpacingMm")}>{Array.from({length:10},(_,i)=>150+i*50).map(v=><option key={v} value={v}>{v} mm</option>)}</select></Field>
      </div>
      <p className="helper">고정못 간격은 150~600 mm, 50 mm 단위</p>
      {minSpacingWarning&&<p className="input-warning" role="status">{minSpacingWarning}</p>}
      <div className="field-grid two">
        <Field label="허용내력 출처(제조사·제품명)" error={errors.anchorCapacitySource?.message} help={a.isCustom?"선택 입력. 계산에는 쓰지 않고 계산서에만 표기합니다.":"제품 선택 시 자동 입력됩니다(수정 가능). 계산에는 쓰지 않고 계산서에만 표기합니다."}>
          <input className={inputClassName} type="text" maxLength={200} placeholder="예: 제조사 / 제품명 / 시험성적서 번호" {...register("anchorCapacitySource")} aria-label="허용내력 출처(제조사·제품명)"/>
        </Field>
      </div>
      {!a.isCustom&&product&&<div className="anchor-reference" role="note" aria-label="앵커 제품 참조">
        <strong>{anchorProductLabel(product)}</strong>
        {resolved
          ? <>
              <p>허용 전단 {formatN(resolved.shearN)} N (= {formatKn(resolved.capacityKn)} kN/개) · 허용 인장 {formatN(resolved.tensionN)} N · 기준: {product.basis_label} · 조건: {product.concrete_condition}</p>
              {resolved.capApplied&&<p>표 값 {formatN(resolved.tableShearN)} N → 상한 {formatN(resolved.capN??0)} N 적용</p>}
              <p>최소 두께/연단/간격: {mmOrDash(product.min_concrete_thickness_mm)} / {mmOrDash(product.min_edge_mm)} / {mmOrDash(product.min_spacing_mm)}{product.shank_diameter_mm!==null?` · 축경 ${product.shank_diameter_mm} mm`:""}</p>
              <p>출처: {product.source}{product.approvals?` · 승인: ${product.approvals}`:""}</p>
              {product.basis==="rec"&&<p className="anchor-reference-note">{anchorRecBasisNote}</p>}
              {product.is_default&&<p className="anchor-reference-note" data-anchor-default-note>{anchorDefaultProductNote}</p>}
            </>
          : <p className="text-destructive">{resolutionError??"허용하중 표를 조회할 수 없습니다."}</p>}
      </div>}
    </div>;
  }

  return <div className="input-workspace">
    <div className="input-intro"><div><span className="eyebrow">DRYWALL HEIGHT DESIGN</span><h1>석고보드 벽체 허용높이 검토</h1><p>{seismic?"석고보드와 스터드 사양에 따른 허용높이 및 런너 고정못 간격을 검토합니다.":"석고보드와 스터드 사양에 따른 허용높이를 검토합니다."}</p></div><span className="copy-badge">KCC Board v{APP_VERSION}</span></div>
    {p.notice}
    <Step number="01" title="검토 CASE" description="내진 또는 비내진 조건을 먼저 선택해 주세요.">
      <div className="choice-grid case-choices">{[{value:"seismic",label:"내진",detail:"지진하중과 런너 고정못을 함께 검토합니다."},{value:"non_seismic",label:"비내진",detail:"활하중 기준으로 응력·처짐·피스 인장을 검토합니다."}].map(o=><label key={o.value} className={`choice-card ${values.designCase === o.value ? "selected" : ""}`}><input type="radio" value={o.value} {...register("designCase")} onChange={e=>{register("designCase").onChange(e);if(e.target.value === "non_seismic" && values.calculationMode === "anchorHeight")p.setValue("calculationMode","maxHeight",{shouldDirty:true});if(e.target.value === "seismic" && values.calculationMode === "maxHeight")p.setValue("calculationMode","anchorHeight",{shouldDirty:true});}}/><span><strong>{o.label}</strong><small>{o.detail}</small></span></label>)}</div>
    </Step>
    <Step number="02" title="계산 방향" description="검토 목적에 맞는 계산 방향을 선택해 주세요.">
      <div className="choice-grid mode-choices">{modes.filter(o=>o.value==="heightCheck"||(seismic?o.value==="anchorHeight":o.value==="maxHeight")).map(o=><label key={o.value} className={`choice-card ${values.calculationMode === o.value ? "selected" : ""}`}><input type="radio" value={o.value} checked={values.calculationMode===o.value} {...register("calculationMode")} onChange={p.onModeChange}/><span><strong>{o.label}</strong><small>{o.detail}</small></span></label>)}</div>
    </Step>
    <Step number="03" title="구조체 사양" description="스터드 사양을 선택하고, 각 면의 보드를 스터드측에서 바깥쪽 순서로 입력해 주세요.">
      <div className="subheading"><h3>스터드 사양</h3></div>
      <div className="field-grid four">
        <div className="stud-select-field"><div className="field-head"><label htmlFor="stud-group">스터드 타입</label><button type="button" onClick={()=>setGallery("types")}>스터드 타입 보기 +</button></div><select id="stud-group" aria-label="스터드 타입" className={inputClassName} {...register("studGroup")} onChange={p.onStudGroupChange}>{p.groups.map(o=><option key={o.value} value={o.value}>{displayStudGroup(o.label)}</option>)}</select></div>
        <div className="stud-select-field"><div className="field-head"><label htmlFor="stud-method">시공방식</label><button type="button" onClick={()=>setGallery("methods")}>시공방식 보기 +</button></div><select id="stud-method" aria-label="시공방식" className={inputClassName} {...register("studMethod")}>{p.methods.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}</select></div>
        <div><Field label="스터드 규격" error={errors.studSpec?.message}><select className={inputClassName} {...register("studSpec")}>{p.specs.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}</select></Field><dl className="stud-dimensions"><div><dt>길이 :</dt><dd>{p.stud?.H??"-"} mm</dd></div><div><dt>폭 :</dt><dd>{p.stud?.B??"-"} mm</dd></div><div><dt>두께 :</dt><dd>{p.stud?.t??"-"} mm</dd></div></dl></div>
        <div>{preset("spacingMm","스터드 간격 (mm)",[300,450,600],v=>`${v} mm`,"any",{min:150,max:600})}<p className="helper">사용자 정의 스터드 간격은 150~600 mm 범위에서 입력할 수 있습니다. 시험 검증 간격은 300·450·600 mm입니다.</p></div>
      </div>
      <div className="board-and-preview">
        <div className="board-inputs"><h3>석고보드 타입 및 두께</h3><p className="helper">1P는 스터드에 가장 가까운 보드입니다.</p>
          <div className="board-face"><div className="face-title"><strong>1면 <span>(전면)</span></strong></div><p className="helper">스터드측 → 바깥쪽</p><div className="board-slots">{p.frontSlots}</div></div>
          <div className="board-face"><div className="face-title"><strong>2면 <span>(후면)</span></strong><label className="mirror-label"><input type="checkbox" checked={p.mirrorRear} disabled={!p.canMirror} onChange={e=>p.onMirrorChange(e.target.checked)}/>1면과 동일</label></div><p className="helper">스터드측 → 바깥쪽{!p.canMirror ? " · 고정 구성으로 동일 적용 불가" : p.mirrorRear ? " · 1면의 변경사항이 자동 적용됩니다." : ""}</p><fieldset disabled={p.mirrorRear} className="board-slots">{p.rearSlots}</fieldset></div>
          {group.startsWith("CH") && <p className="helper">2면 1P는 끼움부에 배치됩니다. {group.includes("개량") ? "12.5T형: 12.5T" : "CH-STUD: 25T"} 고정 두께를 적용합니다. 실제 피스 없이 홈에 끼워지므로 피스 인장 검토에서 제외하고, 전단 연결은 300 mm·피치당 4개 체결 상당으로 가정합니다.</p>}
        </div>
        <div className="structure-preview"><h3>구조체 구성</h3>{p.preview}<dl className="preview-summary"><div><dt>스터드 규격</dt><dd>{values.studSpec}</dd></div><div><dt>스터드 간격</dt><dd>{values.spacingMm} mm</dd></div><div><dt>높이</dt><dd>{values.calculationMode==="heightCheck"?`${Number(values.spanMm??0).toLocaleString()} mm`:"자동산정"}</dd></div></dl></div>
      </div>
      <details className="color-legend" open><summary>석고보드 색상 구분</summary><div>{Object.entries(boardColors).map(([name,color])=><span key={name}><i style={{background:color}}/>{name}</span>)}</div></details>
      <div className="subheading"><h3>석고보드 나사못 간격</h3><span className="unit-label">단위 mm</span></div>
      <div className="field-grid three">{preset("boltPitchInner","1P 나사못 간격 (mm)",[300,450,600],v=>`${v} mm`,"any",{min:100,max:900})}{preset("boltPitchMiddle","2P 나사못 간격 (mm)",[300,450,600],v=>`${v} mm`,"any",{min:100,max:900,disabled:maxPly<2})}{preset("boltPitchOuter","3P 나사못 간격 (mm)",[300,450,600],v=>`${v} mm`,"any",{min:100,max:900,disabled:maxPly<3})}</div>
      <p className="helper">사용자 정의 나사못 간격은 100~900 mm 범위에서 입력할 수 있습니다.</p>
      <p className="helper">{maxPly===2 ? `2P+1P 구성의 단독 1P 면에는 2P 마감층 피치(${values.boltPitchMiddle ?? 300} mm)가 적용됩니다. 3P 입력은 사용하지 않습니다.` : maxPly>=3 ? "단독 1P 면에는 3P 마감층 피치가 적용됩니다. 기존 v0.6.3 적용 방식입니다." : oneSidedSinglePly ? "일면마감 1P 단독 구성은 1P 피치(표준 300 mm)에 피치당 피스 2개를 적용합니다. 2P·3P 입력은 사용하지 않습니다." : "1P 구성은 1P 피치(표준 300 mm)를 사용합니다. 2P·3P 입력은 사용하지 않습니다."}</p>
      {seismic&&renderAnchorSection()}
    </Step>
    <Step number="04" title="설계하중 및 처짐한계 조건" description="높이, 활하중, 처짐한계와 연직하중을 입력해 주세요.">
      <div className="field-grid four">{values.calculationMode==="heightCheck"?numberField("spanMm","현장 높이 (mm)","1",{help:step04Help.span}):<Field label="산정 높이" help={step04Help.span}><input className={inputClassName+" bg-slate-100 text-slate-500 cursor-not-allowed"} aria-label="산정 높이" value="자동산정" readOnly disabled/></Field>}{preset("liveLoadKnM2","활하중 (kN/m²)",[0.25,0.36,0.48],v=>`${v} kN/m²`,"any",{help:step04Help.liveLoad})}{preset("deflectionLimitDenom","처짐한계",[240,300,360],v=>`L/${v}`,"1",{help:step04Help.deflection})}{numberField("verticalLoadKnM","연직하중 (kN/m)","0.01",{min:0,help:step04Help.verticalLoad})}</div>
      {seismic&&<div className="seismic-section"><div className="subheading"><h3>지진하중 조건</h3></div><p className="helper seismic-formula">{seismicFormulaSummary}</p><div className="field-grid four">
        {numberField("seismicS","지역계수 (S)","0.001",{help:step04Help.seismicS})}
        <Field label="지반등급" error={errors.seismicSiteClass?.message} help={step04Help.siteClass}><select className={inputClassName} {...register("seismicSiteClass")}>{p.siteClasses.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>
        <div className="grid gap-1.5 text-sm"><span title={step04Help.s5}>S5 기반암 깊이 불분명</span><label className="checkbox-field"><input type="checkbox" disabled={values.seismicSiteClass!=="S5"} {...register("s5BedrockDepthUnknown")}/>110% 적용</label><span className="helper block">{step04Help.s5}</span></div>
        {numberField("seismicIp","중요도계수 (Ip)","0.1",{help:step04Help.ip})}
        {numberField("seismicZOverH","설치높이비 z/h","any",{min:0,max:1,help:step04Help.zOverH,emptyAsNaN:true})}
      </div></div>}
    </Step>
    <div className="input-actions"><Button type="button" variant="secondary" onClick={()=>{setCustom({});p.onReset();}}><RotateCcw size={17}/>입력값 초기화</Button><Button type="submit" disabled={p.busy}><Calculator size={18}/>{p.busy?"계산 중…":p.submitLabel}</Button></div>
    {gallery&&<StudGallery kind={gallery} onClose={()=>setGallery(null)}/>}
  </div>;
}
