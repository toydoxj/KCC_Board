"use client";

import Link from "next/link";
import { ArrowLeft, ArrowUpDown, CheckCircle2, FileSpreadsheet, Search, SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";

import { inputClassName } from "@/components/ui/field";
import progressCases from "@/data/progress-cases.json";
import { cn } from "@/lib/utils";

type FilterMode = "all" | "noted";
type SortMode = "critical" | "height" | "drawing";

interface ProgressCase {
  id: string;
  sourceRow: number;
  groupNo: string | null;
  sequence: string | null;
  changeNo: string | null;
  drawingName: string;
  frontBoards: string[];
  studType: string | null;
  studSize: string | null;
  spacingMm: number | null;
  rearBoards: string[];
  heightKccMm: number | null;
  heightKccRaw: string | null;
  heightSeismicMm: number | null;
  heightSeismicRaw: string | null;
  strengthRatio: number | null;
  strengthRatioRaw: string | null;
  deflectionRatio: number | null;
  deflectionRatioRaw: string | null;
  runnerRatio: number | null;
  runnerRatioRaw: string | null;
  anchorSpacingMm: number | null;
  note: string | null;
  criticalRatio: number | null;
  isNew: boolean;
  isPassing: boolean | null;
}

interface ProgressDataset {
  metadata: {
    title: string;
    source: string;
    sheet: string;
    caseCount: number;
  };
  cases: ProgressCase[];
}

const data = progressCases as ProgressDataset;
const filterOptions: Array<{ value: FilterMode; label: string }> = [
  { value: "all", label: "전체" },
  { value: "noted", label: "메모" },
];
const sortOptions: Array<{ value: SortMode; label: string }> = [
  { value: "critical", label: "위험도" },
  { value: "height", label: "높이" },
  { value: "drawing", label: "도면명" },
];

export default function ProgressPrototypePage() {
  const [query, setQuery] = useState("");
  const [studType, setStudType] = useState("전체");
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [sortMode, setSortMode] = useState<SortMode>("critical");
  const [selectedId, setSelectedId] = useState(data.cases[0]?.id ?? "");

  const studTypes = useMemo(() => {
    const values = data.cases.map((item) => item.studType).filter((value): value is string => Boolean(value));
    return ["전체", ...Array.from(new Set(values)).sort((a, b) => a.localeCompare(b, "ko"))];
  }, []);

  const filteredCases = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return data.cases
      .filter((item) => {
        if (studType !== "전체" && item.studType !== studType) {
          return false;
        }
        if (filterMode === "noted" && !item.note) {
          return false;
        }
        if (!normalizedQuery) {
          return true;
        }
        return [
          item.drawingName,
          item.studType,
          item.studSize,
          item.note,
          ...item.frontBoards,
          ...item.rearBoards,
        ]
          .filter((value): value is string => Boolean(value))
          .some((value) => value.toLowerCase().includes(normalizedQuery));
      })
      .sort((a, b) => {
        if (sortMode === "height") {
          return (b.heightSeismicMm ?? 0) - (a.heightSeismicMm ?? 0);
        }
        if (sortMode === "drawing") {
          return a.drawingName.localeCompare(b.drawingName, "ko");
        }
        return (b.criticalRatio ?? 0) - (a.criticalRatio ?? 0);
      });
  }, [filterMode, query, sortMode, studType]);

  const selectedCase = filteredCases.find((item) => item.id === selectedId) ?? filteredCases[0] ?? data.cases[0];
  const summary = useMemo(() => {
    const maxHeight = Math.max(...data.cases.map((item) => item.heightSeismicMm ?? 0));
    return { maxHeight };
  }, []);

  return (
    <main className="min-h-screen bg-slate-100">
      <div className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-primary">
              <FileSpreadsheet className="h-4 w-4" aria-hidden="true" />
              refs/진행상황정리.xlsx
            </div>
            <h1 className="mt-1 text-xl font-semibold tracking-normal">프리셋결과</h1>
            <p className="mt-1 text-sm text-muted-foreground">{data.metadata.title}</p>
          </div>
          <Link
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border bg-white px-4 text-sm font-medium text-foreground transition-colors hover:bg-muted focus:outline-none focus:ring-2 focus:ring-ring"
            href="/"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            계산 화면
          </Link>
        </div>
      </div>

      <div className="mx-auto grid max-w-7xl gap-5 px-5 py-5">
        <section className="grid gap-3 md:grid-cols-2">
          <SummaryMetric label="총 케이스" value={`${data.metadata.caseCount}건`} sublabel="xlsx 기준" />
          <SummaryMetric label="최대 높이" value={`${formatNumber(summary.maxHeight)} mm`} sublabel="내진반영" />
        </section>

        <section className="rounded-md border border-border bg-white p-4 shadow-panel">
          <div className="grid gap-3 lg:grid-cols-[minmax(260px,1fr)_220px_220px_220px]">
            <label className="grid gap-1.5 text-sm">
              <span className="font-medium text-foreground">검색</span>
              <span className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                <input
                  className={cn(inputClassName, "pl-9")}
                  value={query}
                  placeholder="도면명, 보드, 스터드"
                  onChange={(event) => setQuery(event.target.value)}
                />
              </span>
            </label>
            <label className="grid gap-1.5 text-sm">
              <span className="font-medium text-foreground">스터드</span>
              <select className={inputClassName} value={studType} onChange={(event) => setStudType(event.target.value)}>
                {studTypes.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <div className="grid gap-1.5 text-sm">
              <span className="font-medium text-foreground">상태</span>
              <div className="grid grid-cols-2 overflow-hidden rounded-md border border-input bg-muted p-1">
                {filterOptions.map((option) => (
                  <button
                    key={option.value}
                    className={cn(
                      "h-8 rounded text-xs font-semibold transition-colors",
                      filterMode === option.value ? "bg-white text-primary shadow-sm" : "text-muted-foreground hover:text-foreground",
                    )}
                    type="button"
                    onClick={() => setFilterMode(option.value)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
            <label className="grid gap-1.5 text-sm">
              <span className="flex items-center gap-1 font-medium text-foreground">
                <ArrowUpDown className="h-4 w-4" aria-hidden="true" />
                정렬
              </span>
              <select className={inputClassName} value={sortMode} onChange={(event) => setSortMode(event.target.value as SortMode)}>
                {sortOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
          <section className="overflow-hidden rounded-md border border-border bg-white shadow-panel">
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
              <div>
                <h2 className="text-base font-semibold">검토 목록</h2>
                <p className="mt-1 text-sm text-muted-foreground">{filteredCases.length}건 표시</p>
              </div>
              <SlidersHorizontal className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px] border-collapse text-sm">
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-normal text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3">도면명</th>
                    <th className="px-3 py-3">스터드</th>
                    <th className="px-3 py-3">보드 구성</th>
                    <th className="px-3 py-3 text-right">높이</th>
                    <th className="px-3 py-3">ratio</th>
                    <th className="px-3 py-3 text-right">앵커</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCases.map((item) => (
                    <tr
                      key={item.id}
                      className={cn(
                        "cursor-pointer border-t border-border transition-colors hover:bg-cyan-50/50",
                        selectedCase?.id === item.id && "bg-cyan-50",
                      )}
                      onClick={() => setSelectedId(item.id)}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground">{item.drawingName}</span>
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground">xlsx row {item.sourceRow}</div>
                      </td>
                      <td className="px-3 py-3">
                        <div className="font-medium">{item.studType ?? "-"}</div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          {item.studSize ?? "-"} · {unitValue(item.spacingMm, "mm")}
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <div className="text-xs text-muted-foreground">전면 {joinBoards(item.frontBoards)}</div>
                        <div className="mt-1 text-xs text-muted-foreground">후면 {joinBoards(item.rearBoards)}</div>
                      </td>
                      <td className="px-3 py-3 text-right font-semibold">{unitValue(item.heightSeismicMm, "mm")}</td>
                      <td className="px-3 py-3">
                        <div className="grid gap-1">
                          <MiniRatio label="내력" value={item.strengthRatio} />
                          <MiniRatio label="처짐" value={item.deflectionRatio} />
                          <MiniRatio label="Run" value={item.runnerRatio} />
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right">{unitValue(item.anchorSpacingMm, "mm")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {selectedCase ? <CaseDetail item={selectedCase} /> : null}
        </div>
      </div>
    </main>
  );
}

function SummaryMetric({ label, value, sublabel }: { label: string; value: string; sublabel: string }) {
  return (
    <div className="rounded-md border border-border bg-white p-4 shadow-panel">
      <div className="text-sm font-medium text-muted-foreground">{label}</div>
      <div className="mt-2 text-2xl font-bold text-foreground">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{sublabel}</div>
    </div>
  );
}

function CaseDetail({ item }: { item: ProgressCase }) {
  const heightDelta = item.heightKccMm !== null && item.heightSeismicMm !== null ? item.heightSeismicMm - item.heightKccMm : null;
  return (
    <aside className="rounded-md border border-border bg-white p-4 shadow-panel">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{item.drawingName}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {item.sequence ?? "-"} / 변경 {item.changeNo ?? "-"} / row {item.sourceRow}
          </p>
        </div>
        <CheckCircle2 className={cn("h-5 w-5", item.isPassing ? "text-emerald-600" : "text-red-600")} aria-hidden="true" />
      </div>

      <div className="mt-4 grid gap-3">
        <DetailBlock label="스터드" value={`${item.studType ?? "-"} · ${item.studSize ?? "-"} · ${unitValue(item.spacingMm, "mm")}`} />
        <DetailBlock label="전면 보드" value={joinBoards(item.frontBoards)} />
        <DetailBlock label="후면 보드" value={joinBoards(item.rearBoards)} />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <NumberBlock label="KCC 정리" value={unitValue(item.heightKccMm, "mm", item.heightKccRaw)} />
        <NumberBlock label="내진 반영" value={unitValue(item.heightSeismicMm, "mm", item.heightSeismicRaw)} />
      </div>
      <div className="mt-2 rounded-md bg-slate-50 px-3 py-2 text-sm">
        높이 차이 <span className={cn("font-semibold", (heightDelta ?? 0) >= 0 ? "text-emerald-700" : "text-red-700")}>{signedUnit(heightDelta, "mm")}</span>
      </div>

      <div className="mt-4 grid gap-3">
        <RatioBar label="내력" value={item.strengthRatio} />
        <RatioBar label="처짐" value={item.deflectionRatio} />
        <RatioBar label="Runner" value={item.runnerRatio} />
      </div>

      <div className="mt-4 grid gap-2 text-sm">
        <DetailBlock label="접합앵커간격" value={unitValue(item.anchorSpacingMm, "mm")} />
        <DetailBlock label="비고" value={item.note ?? "-"} />
      </div>
    </aside>
  );
}

function DetailBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 border-b border-slate-200 pb-2 last:border-b-0">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className="text-sm font-semibold text-foreground">{value}</span>
    </div>
  );
}

function NumberBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-bold">{value}</div>
    </div>
  );
}

function RatioBar({ label, value }: { label: string; value: number | null }) {
  const width = Math.min(Math.max((value ?? 0) * 100, 0), 100);
  return (
    <div className="grid gap-1.5">
      <div className="flex justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className={cn("font-semibold", ratioTextColor(value))}>{ratioValue(value)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-200">
        <div className={cn("h-full rounded-full", ratioFillColor(value))} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function MiniRatio({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("text-xs font-semibold tabular-nums", ratioTextColor(value))}>{ratioValue(value)}</span>
    </div>
  );
}

function ratioTextColor(value: number | null) {
  if (value === null) {
    return "text-muted-foreground";
  }
  if (value >= 0.98) {
    return "text-red-700";
  }
  if (value >= 0.9) {
    return "text-amber-700";
  }
  return "text-emerald-700";
}

function ratioFillColor(value: number | null) {
  if (value === null) {
    return "bg-slate-400";
  }
  if (value >= 0.98) {
    return "bg-red-600";
  }
  if (value >= 0.9) {
    return "bg-amber-500";
  }
  return "bg-emerald-600";
}

function ratioValue(value: number | null) {
  return value === null ? "-" : value.toFixed(3);
}

function unitValue(value: number | null, unit: string, raw?: string | null) {
  if (value === null) {
    return raw ?? "-";
  }
  return `${formatNumber(value)} ${unit}`;
}

function signedUnit(value: number | null, unit: string) {
  if (value === null) {
    return "-";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value)} ${unit}`;
}

function joinBoards(values: string[]) {
  return values.length > 0 ? values.join(" / ") : "-";
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("ko-KR", {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 1,
  }).format(value);
}
