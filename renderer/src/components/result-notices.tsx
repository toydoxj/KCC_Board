import { AlertTriangle, BadgeCheck, FlaskConical, Info } from "lucide-react";

import type { WallCheckResult } from "@/lib/api";
import { productScopeNotice, resultScopeDisclaimer, supportScopeNotice, testedConfigurationStatus } from "@/lib/result-notice";

interface ResultNoticesProps {
  notices: string[];
  // 계산서에서만 제품 적용 범위 문구를 표시한다
  showProductScope?: boolean;
  // 시험 시편 구성 대조 배지(2차 심사의견 A-1). 내진·비내진 모두 표시
  result?: WallCheckResult;
}

// 시험 구성 대조 배지. 판정(O.K/N.G)과 구분하여 표시한다
export function TestedConfigurationBadge({ result }: { result: WallCheckResult }) {
  const status = testedConfigurationStatus(result);
  if (status === null) {
    return null;
  }
  const Icon = status.matched ? BadgeCheck : FlaskConical;
  return (
    <div
      data-tested-configuration={status.matched ? "match" : "mismatch"}
      className={`flex items-start gap-2 rounded-md border p-3 text-sm ${
        status.matched ? "border-emerald-400 bg-emerald-50 text-emerald-900" : "border-orange-400 bg-orange-50 text-orange-900"
      }`}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{status.text}</span>
    </div>
  );
}

// 실험 검증 범위 안내(F-2)와 입력 경고(F-4, 표준 외 피스 간격 등). 판정에는 영향하지 않는다.
export function ResultNotices({ notices, showProductScope = false, result }: ResultNoticesProps) {
  return (
    <div className="grid gap-2 text-sm">
      {result ? <TestedConfigurationBadge result={result} /> : null}
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
          <br />
          {supportScopeNotice}
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
