import { AlertTriangle, Info } from "lucide-react";

import { productScopeNotice, resultScopeDisclaimer } from "@/lib/result-notice";

interface ResultNoticesProps {
  notices: string[];
  // 계산서에서만 제품 적용 범위 문구를 표시한다
  showProductScope?: boolean;
}

// 실험 검증 범위 안내(D-2)와 입력 경고(F-4, 표준 외 피스 간격 등). 판정에는 영향하지 않는다.
export function ResultNotices({ notices, showProductScope = false }: ResultNoticesProps) {
  return (
    <div className="grid gap-2 text-sm">
      {notices.map((notice) => (
        <div key={notice} className="flex items-start gap-2 rounded-md border border-amber-400 bg-amber-50 p-3 text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{notice}</span>
        </div>
      ))}
      <div className="flex items-start gap-2 rounded-md border border-slate-300 bg-slate-50 p-3 text-slate-700">
        <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          {resultScopeDisclaimer}
          {showProductScope ? (
            <>
              <br />
              {productScopeNotice}
            </>
          ) : null}
        </span>
      </div>
    </div>
  );
}
