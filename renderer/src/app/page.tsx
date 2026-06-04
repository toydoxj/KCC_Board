"use client";

import { type ChangeEvent, useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Calculator, Printer, RefreshCcw } from "lucide-react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { CalculationReport, type CalculationReportData, type ReportBoardSlot } from "@/components/calculation-report";
import { SectionPreview } from "@/components/section-preview";
import { ResultPanel } from "@/components/result-panel";
import { Button } from "@/components/ui/button";
import { Field, inputClassName } from "@/components/ui/field";
import {
  checkWall,
  fetchCatalog,
  type BoardProperty,
  type SiteClass,
  type StudMethod,
  type StudSection,
  type WallCheckPayload,
  type WallCheckResult,
} from "@/lib/api";
import { calculationModeLabels, type CalculationMode } from "@/lib/calculation-mode";
import { cn } from "@/lib/utils";
import { useCheckStore } from "@/store/check-store";

const noneBoardValue = "NONE";
const noThicknessValue = "";
const fallbackStudMethod = "기본";
const hiddenOmega = 1.67;
const hiddenBoltDiameter = 3.5;
const hiddenBoltYieldStrength = 480;
const calculationModeOptions: Array<{ value: CalculationMode; label: string }> = [
  { value: "heightCheck", label: calculationModeLabels.heightCheck },
  { value: "maxHeight", label: calculationModeLabels.maxHeight },
];
const siteClassOptions: Array<{ value: SiteClass; label: string }> = [
  { value: "S1", label: "S1 암반" },
  { value: "S2", label: "S2 얕고 단단" },
  { value: "S3", label: "S3 얕고 연약" },
  { value: "S4", label: "S4 깊고 단단" },
  { value: "S5", label: "S5 깊고 연약" },
];

const formSchema = z.object({
  calculationMode: z.enum(["heightCheck", "maxHeight"]),
  rearBoardOuterKind: z.string().min(1),
  rearBoardOuterThickness: z.string(),
  rearBoardMiddleKind: z.string().min(1),
  rearBoardMiddleThickness: z.string(),
  rearBoardInnerKind: z.string().min(1),
  rearBoardInnerThickness: z.string(),
  frontBoardInnerKind: z.string().min(1),
  frontBoardInnerThickness: z.string(),
  frontBoardMiddleKind: z.string().min(1),
  frontBoardMiddleThickness: z.string(),
  frontBoardOuterKind: z.string().min(1),
  frontBoardOuterThickness: z.string(),
  studGroup: z.string().min(1),
  studMethod: z.string().min(1),
  studSpec: z.string().min(1),
  horizontalLoadKgM2: z.coerce.number().positive(),
  spacingMm: z.coerce.number().positive(),
  spanMm: z.coerce.number().positive(),
  deflectionLimitDenom: z.coerce.number().int().positive(),
  boltCountOuter: z.coerce.number().positive(),
  boltCountMiddle: z.coerce.number().positive(),
  boltCountInner: z.coerce.number().positive(),
  boltPitchOuter: z.coerce.number().positive(),
  boltPitchMiddle: z.coerce.number().positive(),
  boltPitchInner: z.coerce.number().positive(),
  seismicS: z.coerce.number().positive(),
  seismicSiteClass: z.enum(["S1", "S2", "S3", "S4", "S5"]),
  s5BedrockDepthUnknown: z.boolean(),
  seismicIp: z.coerce.number().positive(),
});

type CheckFormValues = z.infer<typeof formSchema>;
type BoardKindField =
  | "rearBoardOuterKind"
  | "rearBoardMiddleKind"
  | "rearBoardInnerKind"
  | "frontBoardInnerKind"
  | "frontBoardMiddleKind"
  | "frontBoardOuterKind";
type BoardThicknessField =
  | "rearBoardOuterThickness"
  | "rearBoardMiddleThickness"
  | "rearBoardInnerThickness"
  | "frontBoardInnerThickness"
  | "frontBoardMiddleThickness"
  | "frontBoardOuterThickness";

const defaultValues: CheckFormValues = {
  calculationMode: "heightCheck",
  rearBoardOuterKind: noneBoardValue,
  rearBoardOuterThickness: noThicknessValue,
  rearBoardMiddleKind: "방화",
  rearBoardMiddleThickness: thicknessValue(19),
  rearBoardInnerKind: "방화",
  rearBoardInnerThickness: thicknessValue(19),
  frontBoardInnerKind: "방화",
  frontBoardInnerThickness: thicknessValue(19),
  frontBoardMiddleKind: "방화",
  frontBoardMiddleThickness: thicknessValue(19),
  frontBoardOuterKind: noneBoardValue,
  frontBoardOuterThickness: noThicknessValue,
  studGroup: "C-STUD",
  studMethod: "맞댐이음",
  studSpec: "50S-45-08",
  horizontalLoadKgM2: 24,
  spacingMm: 450,
  spanMm: 7500,
  deflectionLimitDenom: 240,
  boltCountOuter: 2,
  boltCountMiddle: 2,
  boltCountInner: 1,
  boltPitchOuter: 600,
  boltPitchMiddle: 600,
  boltPitchInner: 300,
  seismicS: 0.22,
  seismicSiteClass: "S5",
  s5BedrockDepthUnknown: false,
  seismicIp: 1.5,
};

export default function Home() {
  const {
    catalog,
    catalogLoading,
    checking,
    errorMessage,
    result,
    setCatalog,
    setCatalogLoading,
    setChecking,
    setErrorMessage,
    setResult,
  } = useCheckStore();

  const {
    register,
    handleSubmit,
    reset,
    control,
    setValue,
    formState: { errors },
  } = useForm<CheckFormValues>({
    resolver: zodResolver(formSchema),
    defaultValues,
  });

  useEffect(() => {
    let mounted = true;
    setCatalogLoading(true);
    fetchCatalog()
      .then((nextCatalog) => {
        if (!mounted) {
          return;
        }
        setCatalog(nextCatalog);
        reset(defaultValues);
        setErrorMessage(null);
      })
      .catch((error: unknown) => {
        if (mounted) {
          setErrorMessage(error instanceof Error ? error.message : "자재 목록을 불러오지 못했습니다.");
        }
      })
      .finally(() => {
        if (mounted) {
          setCatalogLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, [reset, setCatalog, setCatalogLoading, setErrorMessage]);

  const formValues = useWatch({ control });
  const selectedRearBoards = useMemo(
    () =>
      compactBoards(catalog?.boards ?? [], [
        boardSelection(formValues.rearBoardOuterKind, formValues.rearBoardOuterThickness),
        boardSelection(formValues.rearBoardMiddleKind, formValues.rearBoardMiddleThickness),
        boardSelection(formValues.rearBoardInnerKind, formValues.rearBoardInnerThickness),
      ]),
    [
      catalog?.boards,
      formValues.rearBoardInnerKind,
      formValues.rearBoardInnerThickness,
      formValues.rearBoardMiddleKind,
      formValues.rearBoardMiddleThickness,
      formValues.rearBoardOuterKind,
      formValues.rearBoardOuterThickness,
    ],
  );
  const selectedFrontBoards = useMemo(
    () =>
      compactBoards(catalog?.boards ?? [], [
        boardSelection(formValues.frontBoardInnerKind, formValues.frontBoardInnerThickness),
        boardSelection(formValues.frontBoardMiddleKind, formValues.frontBoardMiddleThickness),
        boardSelection(formValues.frontBoardOuterKind, formValues.frontBoardOuterThickness),
      ]),
    [
      catalog?.boards,
      formValues.frontBoardInnerKind,
      formValues.frontBoardInnerThickness,
      formValues.frontBoardMiddleKind,
      formValues.frontBoardMiddleThickness,
      formValues.frontBoardOuterKind,
      formValues.frontBoardOuterThickness,
    ],
  );
  const selectedStudGroup = formValues.studGroup ?? defaultValues.studGroup;
  const selectedStud = useMemo(
    () => findStud(catalog?.studs ?? [], selectedStudGroup, formValues.studSpec ?? defaultValues.studSpec),
    [catalog?.studs, formValues.studSpec, selectedStudGroup],
  );
  const selectedSiteClass = (formValues.seismicSiteClass ?? defaultValues.seismicSiteClass) as SiteClass;
  const selectedCalculationMode = (formValues.calculationMode ?? defaultValues.calculationMode) as CalculationMode;
  const heightFieldLabel = selectedCalculationMode === "maxHeight" ? "기준 높이 mm" : "검토 높이 mm";
  const submitButtonLabel = selectedCalculationMode === "maxHeight" ? "최대높이 산정" : "높이 검토";
  const calculationModeRegister = register("calculationMode");
  const studGroupRegister = register("studGroup");
  const [reportData, setReportData] = useState<CalculationReportData | null>(null);

  async function onSubmit(values: CheckFormValues) {
    setChecking(true);
    setErrorMessage(null);
    try {
      const payload = buildPayload(values);
      const nextResult = await checkWall(payload);
      setResult(nextResult);
      setReportData(createReportData(values, nextResult, catalog?.boards ?? [], catalog?.studs ?? []));
    } catch (error: unknown) {
      setResult(null);
      setReportData(null);
      setErrorMessage(error instanceof Error ? error.message : "계산을 완료하지 못했습니다.");
    } finally {
      setChecking(false);
    }
  }

  function handleReset() {
    reset(defaultValues);
    setResult(null);
    setReportData(null);
    setErrorMessage(null);
  }

  function handlePrintReport() {
    if (!reportData) {
      return;
    }
    window.print();
  }

  function clearCalculationResult() {
    setResult(null);
    setReportData(null);
  }

  function handleCalculationModeChange(event: ChangeEvent<HTMLInputElement>) {
    calculationModeRegister.onChange(event);
    clearCalculationResult();
  }

  function renderCalculationModeControl() {
    return (
      <div className="grid gap-1.5">
        <div className="text-sm font-medium text-foreground">계산 방향</div>
        <div className="grid grid-cols-2 overflow-hidden rounded-md border border-input bg-muted p-1">
          {calculationModeOptions.map((option) => {
            const selected = selectedCalculationMode === option.value;
            return (
              <label
                key={option.value}
                className={cn(
                  "flex h-10 cursor-pointer items-center justify-center rounded px-3 text-sm font-semibold transition-colors",
                  selected ? "bg-white text-primary shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
              >
                <input
                  className="sr-only"
                  type="radio"
                  value={option.value}
                  checked={selected}
                  {...calculationModeRegister}
                  onChange={handleCalculationModeChange}
                />
                {option.label}
              </label>
            );
          })}
        </div>
      </div>
    );
  }

  function renderBoardSlot(label: string, kindField: BoardKindField, thicknessField: BoardThicknessField) {
    const kindRegister = register(kindField);
    const selectedKind = (formValues[kindField] as string | undefined) ?? noneBoardValue;
    const thicknessDisabled = selectedKind === noneBoardValue;

    return (
      <div className="grid gap-1.5">
        <div className="text-sm font-medium text-foreground">{label}</div>
        <div className="grid grid-cols-[minmax(0,1fr)_96px] gap-2">
          <select
            aria-label={`${label} 종류`}
            className={inputClassName}
            {...kindRegister}
            onChange={(event) => {
              kindRegister.onChange(event);
              setValue(thicknessField, firstCompleteThicknessValue(catalog?.boards ?? [], event.target.value), {
                shouldDirty: true,
                shouldValidate: true,
              });
            }}
          >
            {boardKindOptions(catalog?.boards).map((option) => (
              <option key={option.value} value={option.value} disabled={option.disabled}>
                {option.label}
              </option>
            ))}
          </select>
          <select
            aria-label={`${label} 두께`}
            className={inputClassName}
            disabled={thicknessDisabled}
            {...register(thicknessField)}
          >
            {boardThicknessOptions(catalog?.boards, selectedKind).map((option) => (
              <option key={option.value} value={option.value} disabled={option.disabled}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    );
  }

  return (
    <main className="min-h-screen">
      <div className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4">
          <div>
            <h1 className="text-xl font-semibold tracking-normal">KCC Board</h1>
            <p className="mt-1 text-sm text-muted-foreground">석고보드·스터드 부분합성 건식벽체 구조검토</p>
          </div>
          <div className="rounded-md border border-border px-3 py-2 text-sm font-medium">
            API {catalogLoading ? "확인 중" : catalog ? "연결됨" : "대기"}
          </div>
        </div>
      </div>

      <div className="mx-auto grid max-w-7xl gap-5 px-5 py-5 xl:grid-cols-[minmax(640px,1fr)_420px]">
        <form onSubmit={handleSubmit(onSubmit)} className="grid gap-5">
          <section className="rounded-md border border-border bg-white p-5 shadow-panel">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold">검토 입력</h2>
              <div className="flex gap-2">
                <Button type="button" variant="secondary" onClick={handleReset} title="기본값">
                  <RefreshCcw className="h-4 w-4" aria-hidden="true" />
                  기본값
                </Button>
                <Button type="submit" disabled={checking || catalogLoading} title={submitButtonLabel}>
                  <Calculator className="h-4 w-4" aria-hidden="true" />
                  {checking ? "계산 중" : submitButtonLabel}
                </Button>
              </div>
            </div>

            {errorMessage ? (
              <div className="mb-4 rounded-md border border-destructive/30 bg-red-50 px-3 py-2 text-sm font-medium text-destructive">
                {errorMessage}
              </div>
            ) : null}

            <div className="grid gap-5 lg:grid-cols-[1fr_260px]">
              <div className="grid gap-5">
                {renderCalculationModeControl()}

                <div className="grid gap-3 sm:grid-cols-3">
                  {renderBoardSlot("후면 외측 보드", "rearBoardOuterKind", "rearBoardOuterThickness")}
                  {renderBoardSlot("후면 중간 보드", "rearBoardMiddleKind", "rearBoardMiddleThickness")}
                  {renderBoardSlot("후면 내측 보드", "rearBoardInnerKind", "rearBoardInnerThickness")}
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  {renderBoardSlot("전면 내측 보드", "frontBoardInnerKind", "frontBoardInnerThickness")}
                  {renderBoardSlot("전면 중간 보드", "frontBoardMiddleKind", "frontBoardMiddleThickness")}
                  {renderBoardSlot("전면 외측 보드", "frontBoardOuterKind", "frontBoardOuterThickness")}
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <Field label="스터드" error={errors.studGroup?.message}>
                    <select
                      className={inputClassName}
                      {...studGroupRegister}
                      onChange={(event) => {
                        studGroupRegister.onChange(event);
                        setValue("studMethod", firstStudMethodValue(catalog?.studMethods ?? [], event.target.value), {
                          shouldDirty: true,
                          shouldValidate: true,
                        });
                        setValue("studSpec", firstStudSpecValue(catalog?.studs ?? [], event.target.value), {
                          shouldDirty: true,
                          shouldValidate: true,
                        });
                      }}
                    >
                      {studGroupOptions(catalog?.studs).map((stud) => (
                        <option key={stud.value} value={stud.value}>
                          {stud.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="시공방식" error={errors.studMethod?.message}>
                    <select className={inputClassName} {...register("studMethod")}>
                      {studMethodOptions(catalog?.studMethods, selectedStudGroup).map((method) => (
                        <option key={method.value} value={method.value}>
                          {method.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="타입" error={errors.studSpec?.message}>
                    <select className={inputClassName} {...register("studSpec")}>
                      {studSpecOptions(catalog?.studs, selectedStudGroup).map((spec) => (
                        <option key={spec.value} value={spec.value}>
                          {spec.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>

                <div className="grid gap-3 sm:grid-cols-4">
                  <Field label="스터드 간격 mm" error={errors.spacingMm?.message}>
                    <input className={inputClassName} type="number" step="1" {...register("spacingMm")} />
                  </Field>
                  <Field label={heightFieldLabel} error={errors.spanMm?.message}>
                    <input className={inputClassName} type="number" step="1" {...register("spanMm")} />
                  </Field>
                  <Field label="수평하중 kg/m²" error={errors.horizontalLoadKgM2?.message}>
                    <input className={inputClassName} type="number" step="0.01" {...register("horizontalLoadKgM2")} />
                  </Field>
                  <Field label="처짐한계 L/" error={errors.deflectionLimitDenom?.message}>
                    <input className={inputClassName} type="number" step="1" {...register("deflectionLimitDenom")} />
                  </Field>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <Field label="3번(외측) 개수" error={errors.boltCountOuter?.message}>
                    <input className={inputClassName} type="number" step="1" {...register("boltCountOuter")} />
                  </Field>
                  <Field label="2번(중간) 개수" error={errors.boltCountMiddle?.message}>
                    <input className={inputClassName} type="number" step="1" {...register("boltCountMiddle")} />
                  </Field>
                  <Field label="1번(내측) 개수" error={errors.boltCountInner?.message}>
                    <input className={inputClassName} type="number" step="1" {...register("boltCountInner")} />
                  </Field>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <Field label="3번(외측) 피치 mm" error={errors.boltPitchOuter?.message}>
                    <input className={inputClassName} type="number" step="1" {...register("boltPitchOuter")} />
                  </Field>
                  <Field label="2번(중간) 피치 mm" error={errors.boltPitchMiddle?.message}>
                    <input className={inputClassName} type="number" step="1" {...register("boltPitchMiddle")} />
                  </Field>
                  <Field label="1번(내측) 피치 mm" error={errors.boltPitchInner?.message}>
                    <input className={inputClassName} type="number" step="1" {...register("boltPitchInner")} />
                  </Field>
                </div>

                <div className="grid gap-3 sm:grid-cols-4">
                  <Field label="S" error={errors.seismicS?.message}>
                    <input className={inputClassName} type="number" step="0.01" {...register("seismicS")} />
                  </Field>
                  <Field label="지반 등급" error={errors.seismicSiteClass?.message}>
                    <select className={inputClassName} {...register("seismicSiteClass")}>
                      {siteClassOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="S5 기반암 깊이 불분명" error={errors.s5BedrockDepthUnknown?.message}>
                    <label className="flex h-10 items-center gap-2 rounded-md border border-input bg-white px-3 text-sm font-medium">
                      <input
                        className="h-4 w-4"
                        type="checkbox"
                        disabled={selectedSiteClass !== "S5"}
                        {...register("s5BedrockDepthUnknown")}
                      />
                      110%
                    </label>
                  </Field>
                  <Field label="Ip" error={errors.seismicIp?.message}>
                    <input className={inputClassName} type="number" step="0.1" {...register("seismicIp")} />
                  </Field>
                </div>
              </div>

              <div className="rounded-md border border-border bg-slate-50 p-3">
                <SectionPreview rearBoards={selectedRearBoards} frontBoards={selectedFrontBoards} stud={selectedStud} />
              </div>
            </div>
          </section>
        </form>

        <aside className="grid content-start gap-5">
          <section className="rounded-md border border-border bg-white p-5 shadow-panel">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold">결과</h2>
              <Button type="button" variant="secondary" disabled={!reportData} onClick={handlePrintReport} title="계산서 출력">
                <Printer className="h-4 w-4" aria-hidden="true" />
                출력
              </Button>
            </div>
            <ResultPanel result={result} mode={selectedCalculationMode} />
          </section>
        </aside>
      </div>
      {reportData ? (
        <div className="screen-report mx-auto max-w-7xl px-5 pb-8">
          <section className="rounded-md border border-border bg-white p-5 shadow-panel">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold">계산서 미리보기</h2>
              <Button type="button" onClick={handlePrintReport} title="계산서 출력">
                <Printer className="h-4 w-4" aria-hidden="true" />
                계산서 출력
              </Button>
            </div>
            <CalculationReport data={reportData} className="rounded-md border border-slate-200 p-6" />
          </section>
        </div>
      ) : null}
      {reportData ? (
        <div className="print-report">
          <CalculationReport data={reportData} />
        </div>
      ) : null}
    </main>
  );
}

function boardKindOptions(boards: BoardProperty[] | undefined) {
  const source =
    boards && boards.length > 0
      ? boards
      : [{ kind: "방화", thickness: 19, mass_kg_m2: 16.1, Fy: 0, E_GPa: 0, is_complete: true, missing_fields: [] }];
  const kindMap = new Map<string, BoardProperty[]>();
  for (const board of source) {
    kindMap.set(board.kind, [...(kindMap.get(board.kind) ?? []), board]);
  }
  const kindOptions = Array.from(kindMap.entries())
    .sort(([left], [right]) => left.localeCompare(right, "ko-KR"))
    .map(([kind, kindBoards]) => {
      const hasCompleteThickness = kindBoards.some((board) => board.is_complete);
      return {
        value: kind,
        label: hasCompleteThickness ? kind : `${kind} (물성 미완성)`,
        disabled: !hasCompleteThickness,
      };
    });
  return [{ value: noneBoardValue, label: "없음", disabled: false }, ...kindOptions];
}

function boardThicknessOptions(boards: BoardProperty[] | undefined, kind: string) {
  if (kind === noneBoardValue) {
    return [{ value: noThicknessValue, label: "-", disabled: false }];
  }
  return (boards ?? [])
    .filter((board) => board.kind === kind)
    .sort((left, right) => left.thickness - right.thickness)
    .map((board) => ({
      value: thicknessValue(board.thickness),
      label: board.is_complete ? `${board.thickness}T` : `${board.thickness}T (물성 미완성: ${board.missing_fields.join(", ")})`,
      disabled: !board.is_complete,
    }));
}

function firstCompleteThicknessValue(boards: BoardProperty[], kind: string) {
  if (kind === noneBoardValue) {
    return noThicknessValue;
  }
  const board = boards
    .filter((item) => item.kind === kind && item.is_complete)
    .sort((left, right) => left.thickness - right.thickness)[0];
  return board ? thicknessValue(board.thickness) : noThicknessValue;
}

function thicknessValue(thickness: number) {
  return String(thickness);
}

function boardSelection(kind: string | undefined, thickness: string | undefined) {
  if (!kind || kind === noneBoardValue || !thickness) {
    return null;
  }
  return { kind, thickness: Number(thickness) };
}

function compactBoards(boards: BoardProperty[], selections: Array<{ kind: string; thickness: number } | null>) {
  return selections
    .map((selection) => {
      if (!selection) {
        return undefined;
      }
      return boards.find(
        (board) => board.kind === selection.kind && board.thickness === selection.thickness && board.is_complete,
      );
    })
    .filter((board): board is BoardProperty => Boolean(board));
}

function studGroupOptions(studs: StudSection[] | undefined) {
  const groups = new Set((studs ?? []).map((stud) => stud.group));
  if (groups.size === 0) {
    groups.add(defaultValues.studGroup);
  }
  return Array.from(groups)
    .sort((left, right) => left.localeCompare(right, "ko-KR", { numeric: true }))
    .map((group) => ({
      value: group,
      label: group,
    }));
}

function studMethodOptions(studMethods: StudMethod[] | undefined, group: string) {
  const matchedMethods = (studMethods ?? [])
    .filter((item) => normalizeStudType(item.stud_type) === normalizeStudType(group))
    .map((item) => item.method ?? fallbackStudMethod);
  const methods = uniqueValues(matchedMethods);
  const source = methods.length > 0 ? methods : [fallbackStudMethod];
  return source.map((method) => ({
    value: method,
    label: method,
  }));
}

function firstStudMethodValue(studMethods: StudMethod[], group: string) {
  return studMethodOptions(studMethods, group)[0]?.value ?? fallbackStudMethod;
}

function studSpecOptions(studs: StudSection[] | undefined, group: string) {
  const specs = (studs ?? [])
    .filter((stud) => stud.group === group)
    .sort((left, right) => left.name.localeCompare(right.name, "ko-KR", { numeric: true }))
    .map((stud) => stud.name);
  const source = specs.length > 0 ? specs : [defaultValues.studSpec];
  return source.map((spec) => ({
    value: spec,
    label: spec,
  }));
}

function firstStudSpecValue(studs: StudSection[], group: string) {
  return studSpecOptions(studs, group)[0]?.value ?? defaultValues.studSpec;
}

function normalizeStudType(value: string) {
  return value.replace(/[.\s]/g, "-").replace(/-+/g, "-").toUpperCase();
}

function uniqueValues(values: string[]) {
  return values.filter((value, index) => values.indexOf(value) === index);
}

function findStud(studs: StudSection[], group: string, spec: string) {
  return studs.find((stud) => stud.group === group && stud.name === spec);
}

function compactBoardPayloads(selections: Array<{ kind: string; thickness: number } | null>) {
  return selections.filter((board): board is { kind: string; thickness: number } => Boolean(board));
}

function buildPayload(values: CheckFormValues): WallCheckPayload {
  return {
    rear_boards: compactBoardPayloads([
      boardSelection(values.rearBoardOuterKind, values.rearBoardOuterThickness),
      boardSelection(values.rearBoardMiddleKind, values.rearBoardMiddleThickness),
      boardSelection(values.rearBoardInnerKind, values.rearBoardInnerThickness),
    ]),
    front_boards: compactBoardPayloads([
      boardSelection(values.frontBoardInnerKind, values.frontBoardInnerThickness),
      boardSelection(values.frontBoardMiddleKind, values.frontBoardMiddleThickness),
      boardSelection(values.frontBoardOuterKind, values.frontBoardOuterThickness),
    ]),
    stud: {
      stud_type: values.studGroup,
      spec: values.studSpec,
      method: values.studMethod,
    },
    horizontal_load_kg_m2: values.horizontalLoadKgM2,
    spacing_mm: values.spacingMm,
    span_mm: values.spanMm,
    deflection_limit_denom: values.deflectionLimitDenom,
    bolt: {
      diameter: hiddenBoltDiameter,
      yield_strength: hiddenBoltYieldStrength,
      pitch: [values.boltPitchOuter, values.boltPitchMiddle, values.boltPitchInner],
      count: [values.boltCountOuter, values.boltCountMiddle, values.boltCountInner],
    },
    seismic: {
      S: values.seismicS,
      site_class: values.seismicSiteClass,
      s5_bedrock_depth_unknown: values.seismicSiteClass === "S5" && values.s5BedrockDepthUnknown,
      Ip: values.seismicIp,
    },
    omega: hiddenOmega,
  };
}

function createReportData(
  values: CheckFormValues,
  result: WallCheckResult,
  boards: BoardProperty[],
  studs: StudSection[],
): CalculationReportData {
  const stud = findStud(studs, values.studGroup, values.studSpec);
  const siteClassLabel = siteClassOptions.find((option) => option.value === values.seismicSiteClass)?.label ?? values.seismicSiteClass;
  const studMultiplier = studMultiplierForMethod(values.studMethod);

  return {
    generatedAt: new Date().toISOString(),
    calculationMode: values.calculationMode,
    rearBoards: [
      reportBoardSlot("후면 3번(외측)", values.rearBoardOuterKind, values.rearBoardOuterThickness, boards),
      reportBoardSlot("후면 2번(중간)", values.rearBoardMiddleKind, values.rearBoardMiddleThickness, boards),
      reportBoardSlot("후면 1번(내측)", values.rearBoardInnerKind, values.rearBoardInnerThickness, boards),
    ],
    frontBoards: [
      reportBoardSlot("전면 1번(내측)", values.frontBoardInnerKind, values.frontBoardInnerThickness, boards),
      reportBoardSlot("전면 2번(중간)", values.frontBoardMiddleKind, values.frontBoardMiddleThickness, boards),
      reportBoardSlot("전면 3번(외측)", values.frontBoardOuterKind, values.frontBoardOuterThickness, boards),
    ],
    stud: {
      group: values.studGroup,
      method: values.studMethod,
      spec: values.studSpec,
      multiplier: studMultiplier,
      H: stud?.H ?? null,
      B: stud?.B ?? null,
      t: stud?.t ?? null,
      A: multiplyNullable(stud?.A, studMultiplier),
      Ix: multiplyNullable(stud?.Ix, studMultiplier),
      Sx: multiplyNullable(stud?.Sx, studMultiplier),
    },
    geometry: {
      spacingMm: values.spacingMm,
      spanMm: values.spanMm,
      deflectionLimitDenom: values.deflectionLimitDenom,
    },
    loads: {
      horizontalLoadKgM2: values.horizontalLoadKgM2,
      seismicS: values.seismicS,
      seismicSiteClass: siteClassLabel,
      s5BedrockDepthUnknown: values.seismicSiteClass === "S5" && values.s5BedrockDepthUnknown,
      seismicIp: values.seismicIp,
    },
    bolts: {
      outerCount: values.boltCountOuter,
      middleCount: values.boltCountMiddle,
      innerCount: values.boltCountInner,
      outerPitch: values.boltPitchOuter,
      middlePitch: values.boltPitchMiddle,
      innerPitch: values.boltPitchInner,
    },
    result,
  };
}

function studMultiplierForMethod(method: string) {
  return method.includes("맞댐") ? 2.0 : 1.0;
}

function multiplyNullable(value: number | null | undefined, multiplier: number) {
  return value === null || value === undefined ? null : value * multiplier;
}

function reportBoardSlot(
  label: string,
  kind: string,
  thicknessValueText: string,
  boards: BoardProperty[],
): ReportBoardSlot {
  const selection = boardSelection(kind, thicknessValueText);
  if (!selection) {
    return {
      label,
      kind: "없음",
      thickness: null,
      mass_kg_m2: null,
      Fy: null,
      E_GPa: null,
    };
  }
  const board = boards.find((item) => item.kind === selection.kind && item.thickness === selection.thickness);
  return {
    label,
    kind: selection.kind,
    thickness: selection.thickness,
    mass_kg_m2: board?.mass_kg_m2 ?? null,
    Fy: board?.Fy ?? null,
    E_GPa: board?.E_GPa ?? null,
  };
}
