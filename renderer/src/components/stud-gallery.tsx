"use client";
import { useEffect, useRef } from "react";
import { X } from "lucide-react";

const types = [
  ["c", "C-STUD", "경량벽체 기본 스터드"],
  ["ch", "CH-STUD", "샤프트월 스터드"],
  ["ch", "CH-STUD(12.5T형)", "12.5T 끼움 보드 적용"],
  ["i", "I-STUD", "샤프트월 스터드"],
  ["hr", "HR-STUD", "고층고 스터드"],
  ["mp", "MP-STUD", "고차음 스터드"],
  ["silent", "T.silent-STUD", "고차음 스터드"],
  ["r", "R-STUD", "고차음 스터드"],
  ["rv", "RV-STUD", "내진 스터드"],
];
const methods = [
  ["c", "기본", "스터드 양면에 나사못으로 보드 시공"],
  ["butt", "맞댐이음", "스터드 웨브를 맞대어 연결한 보강 구성"],
  ["central", "중앙부 이음", "더블스터드를 연결재로 연결한 구성"],
  ["double", "이중스터드", "더블스터드 사용"],
  ["double", "일면마감", "이중스터드 형상에 한쪽 면만 보드 시공"],
];

export function StudGallery({kind, onClose}:{kind:"types"|"methods";onClose:()=>void}) {
  const dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{const d=dialog.current;if(d&&!d.open)d.showModal();return()=>d?.close();},[]);
  const title=kind==="types"?"스터드 타입":"시공방식";
  return <dialog ref={dialog} className="stud-gallery-dialog" aria-label={title} onCancel={onClose} onClick={e=>{if(e.target===e.currentTarget)onClose();}}>
    <div className="gallery-content"><header><h2>{title}</h2><button type="button" onClick={onClose} aria-label="닫기" autoFocus><X size={28}/></button></header>
      {kind==="methods"&&<p className="gallery-intro">C스터드 시공방식 예시입니다. 선택 가능한 방식은 스터드 타입별 목록을 따릅니다.</p>}
      <div className={`stud-gallery-grid ${kind==="methods"?"methods":"types"}`}>{(kind==="types"?types:methods).map(([asset,name,description])=><figure key={name}><div className="gallery-image"><img src={`/installation/${asset}.png`} alt={`${name} 시공 이미지`}/></div><figcaption><strong>{name}</strong><span>{description}</span></figcaption></figure>)}</div>
    </div>
  </dialog>;
}
