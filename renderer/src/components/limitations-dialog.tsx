"use client";
import { useEffect, useRef } from "react";
import { X } from "lucide-react";

import { productScopeNotice, resultScopeDisclaimer, supportScopeNotice } from "@/lib/result-notice";

// 결과 화면의 적용 범위·제한사항 팝업(스터드 타입 갤러리와 같은 dialog 방식). 계산서(인쇄)는 본문에 그대로 표기한다
// 팝업에는 제품 적용 범위도 항상 포함한다(인라인의 showProductScope와 무관 — 결과 화면에서 세 항목을 한 번에 보여주기 위한 의도된 차이)
const items: ReadonlyArray<readonly [string, string]> = [
  ["실험 검증 범위", resultScopeDisclaimer],
  ["지지 조건 적용 범위", supportScopeNotice],
  ["제품 적용 범위", productScopeNotice],
];

export function LimitationsDialog({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = dialog.current;
    if (d && !d.open) d.showModal();
    return () => d?.close();
  }, []);
  const title = "적용 범위·제한사항";
  return (
    <dialog
      ref={dialog}
      className="stud-gallery-dialog limitations-dialog"
      aria-label={title}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="gallery-content">
        <header>
          <h2>{title}</h2>
          <button type="button" onClick={onClose} aria-label="닫기" autoFocus>
            <X size={28} />
          </button>
        </header>
        <p className="gallery-intro">판정(O.K/N.G)에는 영향하지 않는 안내 문구임. 계산서에는 본문에 그대로 표기됨.</p>
        <dl className="limitations-list">
          {items.map(([label, text]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{text}</dd>
            </div>
          ))}
        </dl>
      </div>
    </dialog>
  );
}
