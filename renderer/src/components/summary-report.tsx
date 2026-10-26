import type { ReactNode } from "react";
import { governingHeight, heightReview } from "@/lib/height-review";
import type { CalculationReportData, ReportBoardSlot } from "./calculation-report";
import { boardColor, displayStudGroup, findStudAsset } from "@/lib/visual-assets";
import type { StudSection } from "@/lib/api";
import { productScopeNotice, resultScopeDisclaimer } from "@/lib/result-notice";

const n=(v: number|null|undefined,d=3)=>v==null?"-":v.toLocaleString("ko-KR",{maximumFractionDigits:d});
const unit=(v:number|null|undefined,u:string)=>v==null?"-":`${n(v)} ${u}`;
type Row=[string,ReactNode,string,ReactNode];
function Table({rows}:{rows:Row[]}) {return <table className="summary-table"><tbody>{rows.map((r,i)=><tr key={i}><th>{r[0]}</th><td colSpan={r[2]?1:3}>{r[1]}</td>{r[2]&&<><th>{r[2]}</th><td>{r[3]}</td></>}</tr>)}</tbody></table>;}
function Heading({children}:{children:ReactNode}) {return <h2 className="summary-section-title">{children}</h2>;}
function Fraction({top,bottom}:{top:ReactNode;bottom:ReactNode}) {return <span className="math-fraction"><span>{top}</span><span>{bottom}</span></span>;}
const hasBoard=(b:ReportBoardSlot)=>b.thickness!==null&&b.thickness>0;

function Assembly({data}:{data:CalculationReportData}) {
  const front=data.frontBoards.filter(hasBoard);
  const rear=data.rearBoards.filter(hasBoard);
  const stud={group:data.stud.group,name:data.stud.spec} as StudSection;
  const asset=findStudAsset(stud,data.stud.method);
  const ch=data.stud.group.startsWith("CH-STUD");
  const isI=data.stud.group==="I-STUD";
  const inserted=(ch||isI)&&rear.length>0;
  const sh=asset?.css_height_px??80,sw=asset?.css_width_px??60;
  // Summary only: use the visible height of ONE stud, not the SVG canvas or
  // the stacked height of a double-stud illustration, to scale board thickness.
  const reference=data.stud.group==="C-STUD"?findStudAsset(stud,"기본"):asset;
  const referenceHeight=ch?(reference?.upper_c_height_px??sh):(reference?.shape_height_px??sh);
  const boardScale=referenceHeight/(data.stud.H&&data.stud.H>0?data.stud.H:50);
  const h=sh+rear.reduce((s,b)=>s+(inserted?0:b.thickness??0),0)*boardScale+front.reduce((s,b)=>s+(b.thickness??0)*boardScale,0)+20;
  const zoom=Math.min(0.8,125/h);
  const shapeW=sw*zoom,shapeH=sh*zoom;
  const x0=13,width=415;
  const centers=[85,220,355];
  let cursor=8;
  const rearRects=inserted?[]:rear.map((b,i)=>{const y=cursor;cursor+=(b.thickness??0)*boardScale*zoom;return <rect data-board-face="rear" key={i} x={x0} y={y} width={width} height={(b.thickness??0)*boardScale*zoom} fill={boardColor(b.kind)} stroke="#777" strokeWidth=".6"/>;});
  const top=cursor;cursor+=shapeH;
  const frontRects=front.map((b,i)=>{const y=cursor;cursor+=(b.thickness??0)*boardScale*zoom;return <rect data-board-face="front" key={i} x={x0} y={y} width={width} height={(b.thickness??0)*boardScale*zoom} fill={boardColor(b.kind)} stroke="#777" strokeWidth=".6"/>;});
  // The CH rear board must fill its dedicated insertion slot; ordinary board
  // layers retain the thickness scale used for the surrounding stud body.
  const slotH=ch?(asset?.board_display_height_px??50)*zoom:(rear[0]?.thickness??25)*boardScale*zoom;
  const slotY=ch&&asset?.board_insert_top_px!==undefined?top+(sh-asset.board_insert_top_px-(asset.board_display_height_px??50))*zoom:top+2;
  const webs=centers.map(c=>ch&&asset?.slot_center_x_px!==undefined?c+shapeW/2-asset.slot_center_x_px*zoom:c);
  const webGap=((asset?.stroke_px??3)/2+1)*zoom;
  const breaks=[x0,...webs.flatMap(x=>[x-webGap,x+webGap]),x0+width];
  return <div className="summary-assembly"><div className="summary-board-list"><strong>1면 (전면)</strong>{data.frontBoards.map((b,i)=><div key={i}>1-{i+1}P　{hasBoard(b)?`${b.kind} ${b.thickness}T`:"-"}</div>)}</div><svg viewBox={`0 0 440 ${cursor+8}`} aria-label="스터드 단면 3개를 나란히 배치한 보드 구성도" role="img">{rearRects}{inserted&&breaks.map((x,i)=>i%2===0&&i<breaks.length-1?<rect key={i} x={x} y={slotY} width={breaks[i+1]-x} height={slotH} fill={boardColor(rear[0].kind)} stroke="#777" strokeWidth=".6"/>:null)}{centers.map((c,i)=>asset?<image key={i} href={`/stud-assets/${asset.svg}`} x={c-shapeW/2} y={top} width={shapeW} height={shapeH} transform={ch?`rotate(180 ${c} ${top+shapeH/2})`:undefined}/>:<path key={i} d={`M ${c-shapeW/2} ${top} h ${shapeW} M ${c} ${top} v ${shapeH} M ${c-shapeW/2} ${top+shapeH} h ${shapeW}`} stroke="#171717" strokeWidth="2" fill="none"/>)}{frontRects}</svg><div className="summary-board-list"><strong>2면 (후면)</strong>{[...data.rearBoards].reverse().map((b,i)=><div key={i}>2-{i+1}P　{hasBoard(b)?`${b.kind} ${b.thickness}T`:"-"}</div>)}</div></div>;
}

export function SummaryReport({data}:{data:CalculationReportData}) {
  const r=data.result,g=data.geometry,l=data.loads,b=data.bolts;
  const seismic=r.design_case!=="non_seismic";
  const frontCount=data.frontBoards.filter(hasBoard).length,rearCount=data.rearBoards.filter(hasBoard).length;
  const count=Math.max(frontCount,rearCount);
  const heightCheck=data.calculationMode==="heightCheck";
  const anchorMode=data.calculationMode==="anchorHeight";
  const height=heightCheck?g.spanMm:governingHeight(r);
  const heightTitle=heightCheck?"현장 높이":anchorMode?"런너 고정못 기준 최대높이":"최대 가능 높이";
  const review=heightReview(r,data.calculationMode,g.spanMm);
  const verdict=(label:string,ok:boolean)=><div data-verdict={label} className={`summary-verdict ${ok?"":"ng"}`}><span>{label}</span><b>{ok?"O.K":"N.G"}</b></div>;
  const criteria=seismic?"응력·처짐·런너 고정못·피스 인장 조건 만족값":"응력·처짐·피스 인장 조건 만족값";
  const pitch=[b.innerPitch,b.middlePitch,b.outerPitch],screws=[b.innerCount,b.middleCount,b.outerCount];
  return <article className="summary-document">
    <div className="summary-brand-row"><img src="/kcc-logo.png" alt="KCC" width="60" height="28"/><span className="document-version">V1.0</span></div>
    <h1>석고보드 벽체 허용높이 검토 결과</h1>
    <Heading>1. 결과 요약</Heading>
    <div data-verdict-group="summary" className={`summary-cards ${seismic?"with-anchor":""}`}><div className="summary-height"><strong>{heightTitle}</strong><b>{n(height,0)} mm</b><small>{heightCheck&&<>최대 가능 높이 {n(review.maximumMm,0)} mm<br/></>}{criteria}</small></div>{verdict("응력",r.stress_verdict==="O.K")}{verdict("처짐",r.deflection_verdict==="O.K")}{seismic&&verdict("런너 고정못",review.anchorOk)}{verdict("피스 인장",r.screw_tension_verdict==="O.K")}</div>
    {r.notices?.length>0&&<div className="summary-notices">{r.notices.map((notice,i)=><p key={i}>{notice}</p>)}</div>}
    <Heading>검토 조건</Heading>
    <Table rows={[
      ["스터드",`${displayStudGroup(data.stud.group)} / ${data.stud.method} / ${data.stud.spec}`,"스터드 간격",unit(g.spacingMm,"mm")],
      ["검토 구분",l.designCaseLabel,"강도 기준",r.strength_check_mode==="stud_only"?"스터드 단독":"부분합성"],
      ["활하중",unit(l.liveLoadKnM2,"kN/m²"),"연직하중",unit(l.verticalLoadKnM,"kN/m")],
      [`처짐한계 (L/${g.deflectionLimitDenom})`,`${n(g.spanMm)} / ${n(g.deflectionLimitDenom)} = ${n(r.deflection_limit_mm,1)} mm`,seismic?"지진 입력":"",seismic?`${l.seismicSiteClass} / S ${l.seismicS} / Ip ${l.seismicIp}${l.s5BedrockDepthUnknown?" / 110%":""}`:null],
      ...(seismic?[["런너 고정못 성능",unit(g.anchorCapacityKn,"kN/개"),"런너 고정못 간격",unit(g.anchorSpacingMm,"mm")] as Row]:[]),
    ]}/>
    <Heading>보드 구성</Heading><Assembly data={data}/>
    <Heading>계산 결과</Heading>
    <Table rows={[
      ["처짐",unit(r.deflection_mm,"mm"),"응력비",n(r.stress_ratio,6)],
      ["중립축",unit(r.neutral_axis_mm,"mm"),"처짐한계",unit(r.deflection_limit_mm,"mm")],
      ["합성률 η",n(r.eta,6),"완전합성 단면2차모멘트",unit(r.I_full_mm4,"mm⁴")],
      ["유효강성 보정계수",n(r.intermediate.I_eff_correction_factor),"유효 단면2차모멘트",unit(r.I_eff_mm4,"mm⁴")],
      ["Mn(적용)",unit(r.Mn_kNm,"kN·m"),"Mu",unit(r.Mu_kNm,"kN·m")],
      ["Mn(STUD)",unit(r.intermediate.Mn_stud_only_kNm,"kN·m"),seismic?"런너 고정못 사용률":"높이 산정 단위",seismic?n(r.intermediate.anchor_utilization,6):unit(r.max_height_increment_mm,"mm")],
      ["피스 인장력",unit(r.intermediate.screw_tension_demand_N,"N/개"),"피스 인장 사용률",n(r.intermediate.screw_tension_utilization,6)],
      ...(seismic?[["지진모멘트",unit(r.seismic_moment_kNm,"kN·m"),"지진중량 Wp",unit(r.intermediate.seismic_weight_kN,"kN")] as Row]:[]),
    ]}/>
    <Heading>검토식</Heading><div className="summary-formula-grid">
      <div className="summary-formula-label">응력 검토</div><div className="summary-formula-body"><span className="math-expression">Ω × <Fraction top={<><i>M</i><sub>u</sub></>} bottom={<><i>M</i><sub>n</sub></>}/> ≤ 1.00</span></div>
      <div className="summary-formula-label">처짐 검토</div><div className="summary-formula-body"><span className="math-expression"><span>δ<sub className="math-korean">최대</sub></span> = <Fraction top={<>5 × <i>w</i> × <i>L</i><sup>4</sup></>} bottom={<>384 × <i>E</i> × <i>I</i><sub>e</sub></>}/> ≤ <Fraction top={<i>L</i>} bottom={g.deflectionLimitDenom}/></span></div>
      {seismic&&<><div className="summary-formula-label runner-label">런너 고정못 사용률</div><div className="summary-formula-body runner-formula"><span className="math-expression"><Fraction top={<><i>R</i><sub>h</sub></>} bottom={<><i>P</i><sub>f</sub> ÷ (<i>s</i><sub>f</sub>/1000)</>}/> ≤ 1.00</span></div></>}
      <div className="summary-formula-label">피스 인장 사용률</div><div className="summary-formula-body screw-tension-formula"><span className="math-expression"><Fraction top={<><i>T</i><sub>req</sub></>} bottom={<>min(<Fraction top={<><i>P</i><sub>out</sub></>} bottom={<>Ω<sub>t</sub></>}/>, <Fraction top={<><i>P</i><sub>through</sub></>} bottom={<>Ω<sub>t</sub></>}/>)</>}/><span className="math-comparison">≤ 1.00</span></span></div>
    </div>
    <Heading>스터드 단면</Heading><Table rows={[
      ["높이",unit(data.stud.H,"mm"),"폭",unit(data.stud.B,"mm")],
      ["두께",unit(data.stud.t,"mm"),"단면적",unit(data.stud.A,"mm²")],
      ["단면2차모멘트",unit(data.stud.Ix,"mm⁴"),"단면계수",unit(data.stud.Sx,"mm³")],
    ]}/>
    <Heading>석고보드 고정 나사못 배치</Heading><table className="summary-table screw-table"><thead><tr><th>적용 위치</th><th>나사못 개수</th><th>간격</th></tr></thead><tbody>{[1,2,3].map((p)=><tr key={p}><td>{p}P {p<=count?(p===count?"(마감)":"(내측)"):""}</td><td>{p<=count?`${screws[p-1]}개`:"미적용"}</td><td>{p<=count?`${pitch[p-1]} mm`:"-"}</td></tr>)}{r.intermediate.fixed_rear_board_screw_pitch_mm!==undefined&&<tr><td>2면 고정 보드</td><td>{n(r.intermediate.fixed_rear_board_screw_count)}개</td><td>{n(r.intermediate.fixed_rear_board_screw_pitch_mm)} mm</td></tr>}</tbody></table>
    <footer><p className="summary-scope-disclaimer">{resultScopeDisclaimer}</p><p className="summary-scope-disclaimer">{productScopeNotice}</p>프로그램 결과는 입력조건 및 적용 기준에 따른 설계 참고자료입니다.<br/>실제 시공 전에는 현장 조건과 검토 기준을 구조전문가와 확인하시기 바랍니다.</footer>
  </article>;
}
