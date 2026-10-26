"use client";

import { type ChangeEvent, type ReactNode, useState } from "react";
import type { FieldErrors, UseFormRegister, UseFormSetValue } from "react-hook-form";
import { Calculator, RotateCcw } from "lucide-react";
import { StudGallery } from "./stud-gallery";
import type { StudSection } from "@/lib/api";
import type { CheckFormValues } from "@/app/page";
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
}

const modes: {value: CalculationMode; label: string; detail: string}[] = [
  {value: "maxHeight", label: "최대높이 산정", detail: "선택 사양의 최대 가능 높이 산정"},
  {value: "anchorHeight", label: "런너 고정못 간격에 따른 최대높이", detail: "선택 간격을 만족하는 최대높이 산정"},
  {value: "heightCheck", label: "현장 높이 검토", detail: "현장 계획 높이의 적합성 확인"},
];

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
  const method = values.studMethod ?? "기본";


  function numberField(name: keyof CheckFormValues, label: string, step = "1", extra: {min?: number; max?: number; readOnly?: boolean} = {}) {
    return <Field label={label} error={errors[name]?.message}><input className={inputClassName} type="number" step={step} {...register(name)} {...extra} aria-label={label}/></Field>;
  }

  function preset(name:keyof CheckFormValues,label:string,options:number[],format:(v:number)=>string,step="any",extra: {min?:number;max?:number;disabled?:boolean}={}) {
    const value=Number(values[name]);
    const customKey=name==="boltPitchInner"?`${name}:${p.frontCount===1&&p.rearCount===1?"single":"multi"}`:name;
    const isCustom=custom[customKey]||!options.includes(value);
    return <div className="preset-field"><label htmlFor={name+"-select"}>{label}</label>
      <input type="hidden" {...register(name)}/>
      <select id={name+"-select"} aria-label={label} className={inputClassName} value={extra.disabled?"not-applicable":isCustom?"custom":String(value)} disabled={extra.disabled} onChange={e=>{
        setCustom(c=>({...c,[customKey]:e.target.value==="custom"}));
        if(e.target.value!=="custom")p.setValue(name,Number(e.target.value),{shouldDirty:true,shouldValidate:true});
      }}>{extra.disabled?<option value="not-applicable">미적용</option>:<>{options.map(v=><option key={v} value={v}>{format(v)}</option>)}<option value="custom">사용자 정의</option></>}</select>
      {!extra.disabled&&isCustom&&<input type="number" step={step} min={extra.min??(step==="1"?1:undefined)} max={extra.max} className={inputClassName} aria-label={label+" 사용자 정의"} value={values[name] as number??""} onChange={e=>p.setValue(name,e.target.value===""?"":Number(e.target.value),{shouldDirty:true,shouldValidate:true})}/>}
      {!extra.disabled&&errors[name]?.message&&<span className="text-xs text-destructive">{errors[name]?.message}</span>}
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
        {preset("spacingMm","스터드 간격 (mm)",[300,450,600],v=>`${v} mm`)}
      </div>
      <div className="board-and-preview">
        <div className="board-inputs"><h3>석고보드 타입 및 두께</h3><p className="helper">1P는 스터드에 가장 가까운 보드입니다.</p>
          <div className="board-face"><div className="face-title"><strong>1면 <span>(전면)</span></strong></div><p className="helper">스터드측 → 바깥쪽</p><div className="board-slots">{p.frontSlots}</div></div>
          <div className="board-face"><div className="face-title"><strong>2면 <span>(후면)</span></strong><label className="mirror-label"><input type="checkbox" checked={p.mirrorRear} disabled={!p.canMirror} onChange={e=>p.onMirrorChange(e.target.checked)}/>1면과 동일</label></div><p className="helper">스터드측 → 바깥쪽{!p.canMirror ? " · 고정 구성으로 동일 적용 불가" : p.mirrorRear ? " · 1면의 변경사항이 자동 적용됩니다." : ""}</p><fieldset disabled={p.mirrorRear} className="board-slots">{p.rearSlots}</fieldset></div>
          {group.startsWith("CH") && <p className="helper">2면 1P는 끼움부에 배치됩니다. {group.includes("개량") ? "12.5T형: 12.5T" : "CH-STUD: 25T"} 고정 두께를 적용합니다.</p>}
        </div>
        <div className="structure-preview"><h3>구조체 구성</h3>{p.preview}<dl className="preview-summary"><div><dt>스터드 규격</dt><dd>{values.studSpec}</dd></div><div><dt>스터드 간격</dt><dd>{values.spacingMm} mm</dd></div><div><dt>높이</dt><dd>{values.calculationMode==="heightCheck"?`${Number(values.spanMm??0).toLocaleString()} mm`:"자동산정"}</dd></div></dl></div>
      </div>
      <details className="color-legend" open><summary>석고보드 색상 구분</summary><div>{Object.entries(boardColors).map(([name,color])=><span key={name}><i style={{background:color}}/>{name}</span>)}</div></details>
      <div className="subheading"><h3>석고보드 나사못 간격</h3><span className="unit-label">단위 mm</span></div>
      <div className="field-grid three">{preset("boltPitchInner","1P 나사못 간격 (mm)",[300,450,600],v=>`${v} mm`,"any",{min:100,max:900})}{preset("boltPitchMiddle","2P 나사못 간격 (mm)",[300,450,600],v=>`${v} mm`,"any",{min:100,max:900,disabled:maxPly<2})}{preset("boltPitchOuter","3P 나사못 간격 (mm)",[300,450,600],v=>`${v} mm`,"any",{min:100,max:900,disabled:maxPly<3})}</div>
      <p className="helper">사용자 정의 나사못 간격은 100~900 mm 범위에서 입력할 수 있습니다.</p>
      <p className="helper">{maxPly===2 ? `2P+1P 구성의 단독 1P 면에는 2P 마감층 피치(${values.boltPitchMiddle ?? 300} mm)가 적용됩니다. 3P 입력은 사용하지 않습니다.` : maxPly>=3 ? "단독 1P 면에는 3P 마감층 피치가 적용됩니다. 기존 v0.6.3 적용 방식입니다." : "1P 구성은 1P 피치를 사용합니다. 2P·3P 입력은 사용하지 않습니다."}</p>
      {seismic&&<div className="runner-section"><div className="subheading"><h3>런너 고정못</h3></div><div className="field-grid two">{preset("anchorCapacityKn","런너 고정못 성능 (kN/개)",[0.4,0.2],v=>`${v} kN/개`)}<Field label="런너 고정못 간격 (mm)" error={errors.anchorSpacingMm?.message}><select aria-label="런너 고정못 간격 (mm)" className={inputClassName} {...register("anchorSpacingMm")}>{Array.from({length:10},(_,i)=>150+i*50).map(v=><option key={v} value={v}>{v} mm</option>)}</select></Field></div><p className="helper">고정못 간격은 150~600 mm, 50 mm 단위</p></div>}
    </Step>
    <Step number="04" title="설계하중 및 처짐한계 조건" description="높이, 활하중, 처짐한계와 연직하중을 입력해 주세요.">
      <div className="field-grid four">{values.calculationMode==="heightCheck"?numberField("spanMm","현장 높이 (mm)"):<Field label="산정 높이"><input className={inputClassName+" bg-slate-100 text-slate-500 cursor-not-allowed"} aria-label="산정 높이" value="자동산정" readOnly disabled/></Field>}{preset("liveLoadKnM2","활하중 (kN/m²)",[0.25,0.36,0.48],v=>`${v} kN/m²`)}{preset("deflectionLimitDenom","처짐한계",[240,300,360],v=>`L/${v}`,"1")}{numberField("verticalLoadKnM","연직하중 (kN/m)","0.01",{min:0})}</div>
      {seismic&&<div className="seismic-section"><div className="subheading"><h3>지진하중 조건</h3></div><div className="field-grid four">
        {numberField("seismicS","지역계수 (S)","0.01")}
        <Field label="지반등급" error={errors.seismicSiteClass?.message}><select className={inputClassName} {...register("seismicSiteClass")}>{p.siteClasses.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>
        <div className="grid gap-1.5 text-sm"><span>S5 기반암 깊이 불분명</span><label className="checkbox-field"><input type="checkbox" disabled={values.seismicSiteClass!=="S5"} {...register("s5BedrockDepthUnknown")}/>110% 적용</label></div>
        {numberField("seismicIp","중요도계수 (Ip)","0.1")}
      </div></div>}
    </Step>
    <div className="input-actions"><Button type="button" variant="secondary" onClick={()=>{setCustom({});p.onReset();}}><RotateCcw size={17}/>입력값 초기화</Button><Button type="submit" disabled={p.busy}><Calculator size={18}/>{p.busy?"계산 중…":p.submitLabel}</Button></div>
    {gallery&&<StudGallery kind={gallery} onClose={()=>setGallery(null)}/>}
  </div>;
}
