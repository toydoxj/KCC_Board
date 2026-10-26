import type { BoardProperty, StudSection } from "@/lib/api";
import { boardColor, displayStudGroup, findStudAsset } from "@/lib/visual-assets";

interface Props {rearBoards: BoardProperty[]; frontBoards: BoardProperty[]; stud?: StudSection; studMethod?: string;}
export function StructurePreview({rearBoards, frontBoards, stud, studMethod}: Props) {
  const asset = findStudAsset(stud,studMethod);
  const isCh = stud?.group.startsWith("CH-STUD") ?? false;
  const isI = stud?.group === "I-STUD";
  const inserted = (isCh || isI) && rearBoards.length > 0;
  const rGap = stud?.group === "R-STUD" ? 12 : 0;
  const scale = 1.0;
  const studW = asset?.css_width_px ?? 78;
  const studH = asset?.css_height_px ?? Math.max(50,(stud?.H??50)*0.5+25);
  const left = (340-studW)/2;
  const boardX = 38;
  const boardW = 264;
  const boardScale = 2;
  const rearH = inserted ? 0 : rearBoards.reduce((s,b)=>s+b.thickness*boardScale,0);
  const top = 34+rearH+(rearBoards.length&&!inserted?rGap:0);
  const frontTop=top+studH+(frontBoards.length?rGap:0);
  const height=frontTop+frontBoards.reduce((s,b)=>s+b.thickness*boardScale,0)+30;
  let rearY=34;
  let frontY=frontTop;
  const drawBoard = (b: BoardProperty, x:number, y:number, w:number, h:number, key:string, label?:string) => <g key={key}><rect x={x} y={y} width={w} height={h} fill={boardColor(b.kind)} stroke="#777" strokeWidth="0.8"/>{label && <text x={x+w/2} y={y+h/2} textAnchor="middle" dominantBaseline="central" fontSize="10" fill="#202733">{label}</text>}</g>;
  // V16 CH SVG has its insertion slot at the bottom. Rotate it 180 degrees to
  // place the rear board above and front layers below, as in the user's example.
  const insertY = isCh && asset?.board_insert_top_px !== undefined
    ? top+studH-asset.board_insert_top_px-(asset.board_display_height_px??50)
    : top+4;
  const insertH=isCh?(asset?.board_display_height_px??(rearBoards[0]?.thickness??25)*boardScale):(rearBoards[0]?.thickness??0)*boardScale;
  const insertX=isCh && asset?.slot_center_x_px !== undefined ? left+studW-asset.slot_center_x_px : 170;
  const insertGap=(asset?.stroke_px??4)/2+1;

  return <div className="structure-art">
    <svg viewBox={`0 0 340 ${Math.max(height,220)}`} role="img" aria-label={`${displayStudGroup(stud?.group??"스터드")} ${stud?.name??""} ${studMethod??""} 구조체 구성`} style={{width:"100%",maxHeight:440}}>
      <text x="38" y="20" fontSize="11" fill="#64748b">2면 (후면)</text>
      {!inserted && rearBoards.map((b,i)=>{const y=rearY;rearY+=b.thickness*boardScale;return drawBoard(b,boardX,y,boardW,b.thickness*boardScale,`rear-${i}`,`2-${rearBoards.length-i}P ${b.kind} ${b.thickness}T`);})}
      {inserted && <g>{drawBoard(rearBoards[0],boardX,insertY,insertX-insertGap-boardX,insertH,"insert-left",`2-1P ${rearBoards[0].kind}`)}{drawBoard(rearBoards[0],insertX+insertGap,insertY,boardX+boardW-insertX-insertGap,insertH,"insert-right",`${rearBoards[0].thickness}T`)}</g>}
      {asset ? <image data-stud-asset={asset.svg} href={`/stud-assets/${asset.svg}`} x={left} y={top} width={studW*scale} height={studH*scale} transform={isCh?`rotate(180 170 ${top+studH/2})`:undefined}/> : <g data-fallback="legacy-section" stroke="#171717" fill="none" strokeWidth="3">
        {isI ? <path d={`M ${left} ${top} h ${studW} M 170 ${top} v ${studH} M ${left} ${top+studH} h ${studW}`}/> : <path d={`M ${left+5} ${top+10} V ${top+2} H ${left+studW-2} V ${top+studH-2} H ${left+5} v -8`}/>}
      </g>}
      {frontBoards.map((b,i)=>{const y=frontY;frontY+=b.thickness*boardScale;return drawBoard(b,boardX,y,boardW,b.thickness*boardScale,`front-${i}`,`1-${i+1}P ${b.kind} ${b.thickness}T`);})}
      <text x="38" y={frontY+19} fontSize="11" fill="#64748b">1면 (전면)</text>
    </svg>
    <p className="preview-caption">{displayStudGroup(stud?.group??"")} · {studMethod} {asset?"":"· 기본 단면도"}</p>

  </div>;
}
