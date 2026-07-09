"use client";

import { type ChangeEvent, useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { Calculator, FileSpreadsheet, Printer, RefreshCcw } from "lucide-react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { CalculationReport, type CalculationReportData, type ReportBoardSlot } from "@/components/calculation-report";
import { SectionPreview } from "@/components/section-preview";
import { ResultPanel } from "@/components/result-panel";
import { Button } from "@/components/ui/button";
import { Field, inputClassName } from "@/components/ui/field";
import progressCases from "@/data/progress-cases.json";
import {
  checkWall,
  fetchCatalog,
  type BoardProperty,
  type DesignCase,
  type SiteClass,
  type StudMethod,
  type StudSection,
  type WallCheckPayload,
  type WallCheckResult,
} from "@/lib/api";
import {
  calculationModeLabels,
  type CalculationMode,
} from "@/lib/calculation-mode";
import { cn } from "@/lib/utils";
import { useCheckStore } from "@/store/check-store";

const noneBoardValue = "NONE";
const noThicknessValue = "";
const fallbackStudMethod = "기본";
const hiddenOmega = 1.5;
const hiddenBoltDiameter = 3.5;
const hiddenBoltYieldStrength = 480;
const hiddenBoltCountOuter = 2;
const hiddenBoltCountMiddle = 2;
const hiddenBoltCountInner = 1;
const gravity = 9.81;
const anchorSpacingMinMm = 150;
const anchorSpacingMaxMm = 600;
const anchorSpacingIncrementMm = 50;
const centralJointStudGapMm = 25;
const studConnectionInertiaFactor = 1;
const chStudRearBoardThicknessMm = 25;
const chStudImprovedRearBoardThicknessMm = 12.5;
const iStudRearBoardKind = "방화";
const iStudRearBoardThicknessMm = 25;
const doubleStudMethod = "이중스터드";
const oneSideFinishMethod = "일면마감";
const calculationModeOptions: Array<{ value: CalculationMode; label: string }> = [
  { value: "heightCheck", label: "높이검토" },
  { value: "maxHeight", label: "최대높이" },
  { value: "anchorHeight", label: "앵커간격" },
];
const designCaseOptions: Array<{ value: DesignCase; label: string }> = [
  { value: "seismic", label: "내진" },
  { value: "non_seismic", label: "비내진" },
];
const siteClassOptions: Array<{ value: SiteClass; label: string }> = [
  { value: "S1", label: "S1 암반" },
  { value: "S2", label: "S2 얕고 단단" },
  { value: "S3", label: "S3 얕고 연약" },
  { value: "S4", label: "S4 깊고 단단" },
  { value: "S5", label: "S5 깊고 연약" },
];

const formSchema = z.object({
  calculationMode: z.enum(["heightCheck", "maxHeight", "anchorHeight"]),
  strengthCheckMode: z.enum(["composite", "stud_only"]),
  designCase: z.enum(["seismic", "non_seismic"]),
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
  liveLoadKnM2: z.coerce.number().positive(),
  verticalLoadKnM: z.coerce.number().min(0),
  spacingMm: z.coerce.number().positive(),
  spanMm: z.coerce.number().positive(),
  deflectionLimitDenom: z.coerce.number().int().positive(),
  anchorCapacityKn: z.coerce.number().positive(),
  anchorSpacingMm: z.coerce
    .number()
    .min(anchorSpacingMinMm)
    .max(anchorSpacingMaxMm)
    .refine((value) => value % anchorSpacingIncrementMm === 0, "50mm 단위로 입력해야 합니다."),
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
type ProgressCase = {
  id: string;
  drawingName: string;
  frontBoards: string[];
  studType: string | null;
  studSize: string | null;
  spacingMm: number | null;
  anchorSpacingMm: number | null;
  rearBoards: string[];
  heightSeismicMm: number | null;
  isNew: boolean;
};
type ProgressDataset = {
  cases: ProgressCase[];
};

const productCases = (progressCases as ProgressDataset).cases;
const noProductValue = "";

const defaultValues: CheckFormValues = {
  calculationMode: "heightCheck",
  strengthCheckMode: "composite",
  designCase: "seismic",
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
  liveLoadKnM2: 0.25,
  verticalLoadKnM: 0,
  spacingMm: 450,
  spanMm: 7500,
  deflectionLimitDenom: 240,
  anchorCapacityKn: 0.4,
  anchorSpacingMm: 450,
  boltPitchOuter: 300,
  boltPitchMiddle: 300,
  boltPitchInner: 600,
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
    getValues,
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
  const selectedStudGroup = formValues.studGroup ?? defaultValues.studGroup;
  const selectedStudMethod = formValues.studMethod ?? defaultValues.studMethod;
  const selectedFixedRearBoardThickness = fixedRearBoardThicknessForGroup(selectedStudGroup);
  const selectedFixedRearBoardKind = fixedRearBoardKindForGroup(selectedStudGroup);
  const selectedHasFixedRearBoard = selectedFixedRearBoardThickness !== null;
  const selectedIsOneSideFinish = isOneSideFinishMethod(selectedStudMethod);
  const selectedRearBoardInputsDisabled = selectedHasFixedRearBoard || selectedIsOneSideFinish;
  const selectedRearBoards = useMemo(
    () =>
      compactBoards(
        catalog?.boards ?? [],
        selectedIsOneSideFinish
          ? []
          : selectedFixedRearBoardThickness === null
            ? [
                boardSelection(formValues.rearBoardOuterKind, formValues.rearBoardOuterThickness),
                boardSelection(formValues.rearBoardMiddleKind, formValues.rearBoardMiddleThickness),
                boardSelection(formValues.rearBoardInnerKind, formValues.rearBoardInnerThickness),
              ]
            : [
                boardSelection(selectedFixedRearBoardKind ?? formValues.rearBoardInnerKind, thicknessValue(selectedFixedRearBoardThickness)),
              ],
      ),
    [
      catalog?.boards,
      formValues.rearBoardInnerKind,
      formValues.rearBoardInnerThickness,
      formValues.rearBoardMiddleKind,
      formValues.rearBoardMiddleThickness,
      formValues.rearBoardOuterKind,
      formValues.rearBoardOuterThickness,
      selectedFixedRearBoardKind,
      selectedFixedRearBoardThickness,
      selectedIsOneSideFinish,
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
  const selectedStud = useMemo(
    () => findStud(catalog?.studs ?? [], selectedStudGroup, formValues.studSpec ?? defaultValues.studSpec),
    [catalog?.studs, formValues.studSpec, selectedStudGroup],
  );
  const selectedSiteClass = (formValues.seismicSiteClass ?? defaultValues.seismicSiteClass) as SiteClass;
  const selectedCalculationMode = (formValues.calculationMode ?? defaultValues.calculationMode) as CalculationMode;
  const heightFieldLabel =
    selectedCalculationMode === "heightCheck"
      ? "검토 높이 mm"
      : selectedCalculationMode === "anchorHeight"
        ? "앵커 산정 기준높이 mm"
        : "산정 높이 mm";
  const submitButtonLabel =
    selectedCalculationMode === "heightCheck"
      ? "높이 검토"
      : selectedCalculationMode === "anchorHeight"
        ? "앵커간격 산정"
        : "최대높이 산정";
  const calculationModeRegister = register("calculationMode");
  const studGroupRegister = register("studGroup");
  const [reportData, setReportData] = useState<CalculationReportData | null>(null);
  const [selectedProductId, setSelectedProductId] = useState(noProductValue);
  const [productMessage, setProductMessage] = useState<string | null>(null);

  useEffect(() => {
    if (selectedIsOneSideFinish) {
      setRearBoardValue("rearBoardOuterKind", noneBoardValue, formValues.rearBoardOuterKind);
      setRearBoardValue("rearBoardOuterThickness", noThicknessValue, formValues.rearBoardOuterThickness);
      setRearBoardValue("rearBoardMiddleKind", noneBoardValue, formValues.rearBoardMiddleKind);
      setRearBoardValue("rearBoardMiddleThickness", noThicknessValue, formValues.rearBoardMiddleThickness);
      setRearBoardValue("rearBoardInnerKind", noneBoardValue, formValues.rearBoardInnerKind);
      setRearBoardValue("rearBoardInnerThickness", noThicknessValue, formValues.rearBoardInnerThickness);
      return;
    }

    if (!catalog || selectedFixedRearBoardThickness === null) {
      return;
    }

    const fixedRearBoardKind = boardKindForFixedThickness(
      catalog.boards,
      selectedFixedRearBoardThickness,
      formValues.rearBoardInnerKind,
      selectedFixedRearBoardKind ?? undefined,
    );
    if (!fixedRearBoardKind) {
      const fixedBoardLabel = selectedFixedRearBoardKind
        ? `${selectedFixedRearBoardKind} ${selectedFixedRearBoardThickness}T`
        : `${selectedFixedRearBoardThickness}T`;
      setErrorMessage(`${selectedStudGroup} 후면 고정 보드 ${fixedBoardLabel} 물성이 없습니다.`);
      return;
    }

    setRearBoardValue("rearBoardOuterKind", noneBoardValue, formValues.rearBoardOuterKind);
    setRearBoardValue("rearBoardOuterThickness", noThicknessValue, formValues.rearBoardOuterThickness);
    setRearBoardValue("rearBoardMiddleKind", noneBoardValue, formValues.rearBoardMiddleKind);
    setRearBoardValue("rearBoardMiddleThickness", noThicknessValue, formValues.rearBoardMiddleThickness);
    setRearBoardValue("rearBoardInnerKind", fixedRearBoardKind, formValues.rearBoardInnerKind);
    setRearBoardValue("rearBoardInnerThickness", thicknessValue(selectedFixedRearBoardThickness), formValues.rearBoardInnerThickness);

    function setRearBoardValue(
      field: BoardKindField | BoardThicknessField,
      nextValue: string,
      currentValue: string | undefined,
    ) {
      if (currentValue !== nextValue) {
        setValue(field, nextValue, {
          shouldDirty: true,
          shouldValidate: true,
        });
      }
    }
  }, [
    catalog,
    formValues.rearBoardInnerKind,
    formValues.rearBoardInnerThickness,
    formValues.rearBoardMiddleKind,
    formValues.rearBoardMiddleThickness,
    formValues.rearBoardOuterKind,
    formValues.rearBoardOuterThickness,
    selectedFixedRearBoardKind,
    selectedFixedRearBoardThickness,
    selectedIsOneSideFinish,
    selectedStudGroup,
    setErrorMessage,
    setValue,
  ]);

  async function onSubmit(values: CheckFormValues) {
    setChecking(true);
    setErrorMessage(null);
    try {
      let nextValues = values;
      let nextResult = await checkWall(buildPayload(values));

      const nextTargetHeight =
        values.calculationMode === "anchorHeight" ? nextResult.anchor_max_height_mm : nextResult.max_height_mm;
      if (
        values.calculationMode !== "heightCheck"
        && nextTargetHeight > 0
        && nextTargetHeight !== values.spanMm
      ) {
        nextValues = {
          ...values,
          spanMm: nextTargetHeight,
        };
        nextResult = await checkWall(buildPayload(nextValues));
        setValue("spanMm", nextValues.spanMm, {
          shouldDirty: true,
          shouldValidate: true,
        });
      }

      setResult(nextResult);
      setReportData(createReportData(nextValues, nextResult, catalog?.boards ?? [], catalog?.studs ?? []));
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
    setSelectedProductId(noProductValue);
    setProductMessage(null);
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

  function handleProductChange(event: ChangeEvent<HTMLSelectElement>) {
    const productId = event.target.value;
    setSelectedProductId(productId);
    clearCalculationResult();
    if (!productId) {
      setProductMessage(null);
      return;
    }

    const product = productCases.find((item) => item.id === productId);
    if (!product) {
      setProductMessage("선택한 제품 정보를 찾지 못했습니다.");
      return;
    }

    const preset = createProductPreset(product, catalog?.boards ?? [], catalog?.studs ?? [], catalog?.studMethods ?? []);
    reset({ ...getValues(), ...preset.values });
    setProductMessage(
      preset.warnings.length > 0
        ? `${product.drawingName}: ${preset.warnings.join(" ")}`
        : `${product.drawingName} 입력값을 적용했습니다.`,
    );
  }

  function renderCalculationModeControl() {
    return (
      <div className="grid gap-1.5">
        <div className="text-sm font-medium text-foreground">계산 방향</div>
        <div className="grid grid-cols-3 overflow-hidden rounded-md border border-input bg-muted p-1">
          {calculationModeOptions.map((option) => {
            const selected = selectedCalculationMode === option.value;
            return (
              <label
                key={option.value}
                className={cn(
                  "flex h-10 cursor-pointer items-center justify-center whitespace-nowrap rounded px-2 text-xs font-semibold transition-colors sm:text-sm",
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

  function renderBoardSlot(
    label: string,
    kindField: BoardKindField,
    thicknessField: BoardThicknessField,
    options: { disabled?: boolean; fixedThickness?: number; required?: boolean } = {},
  ) {
    const kindRegister = register(kindField);
    const selectedKind = (formValues[kindField] as string | undefined) ?? noneBoardValue;
    const disabled = options.disabled ?? false;
    const thicknessDisabled = disabled || selectedKind === noneBoardValue || options.fixedThickness !== undefined;
    const kindOptions = disabled
      ? [{ value: noneBoardValue, label: "없음", disabled: false }]
      : boardKindOptions(catalog?.boards, options.fixedThickness, !options.required);
    const thicknessOptions =
      options.fixedThickness === undefined
        ? boardThicknessOptions(catalog?.boards, selectedKind)
        : [{ value: thicknessValue(options.fixedThickness), label: `${options.fixedThickness}T`, disabled: false }];

    return (
      <div className="grid gap-1.5">
        <div className="text-sm font-medium text-foreground">{label}</div>
        <div className="grid grid-cols-[minmax(0,1fr)_96px] gap-2">
          <select
            aria-label={`${label} 종류`}
            className={inputClassName}
            disabled={disabled}
            {...kindRegister}
            onChange={(event) => {
              kindRegister.onChange(event);
              setValue(
                thicknessField,
                options.fixedThickness === undefined
                  ? firstCompleteThicknessValue(catalog?.boards ?? [], event.target.value)
                  : thicknessValue(options.fixedThickness),
                {
                  shouldDirty: true,
                  shouldValidate: true,
                },
              );
            }}
          >
            {kindOptions.map((option) => (
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
            {thicknessOptions.map((option) => (
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
        <div className="mx-auto flex max-w-7xl flex-col items-start gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-normal">KCC Board</h1>
            <p className="mt-1 text-sm text-muted-foreground">석고보드·스터드 부분합성 건식벽체 구조검토</p>
          </div>
          <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:flex-nowrap sm:justify-end">
            <Link
              className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md border border-border bg-white px-4 text-sm font-medium text-foreground transition-colors hover:bg-muted focus:outline-none focus:ring-2 focus:ring-ring"
              href="/prototype"
            >
              <FileSpreadsheet className="h-4 w-4 shrink-0" aria-hidden="true" />
              프리셋결과
            </Link>
            <div className="shrink-0 whitespace-nowrap rounded-md border border-border px-3 py-2 text-sm font-medium">
              API {catalogLoading ? "확인 중" : catalog ? "연결됨" : "대기"}
            </div>
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
                  <RefreshCcw className="h-4 w-4 shrink-0" aria-hidden="true" />
                  기본값
                </Button>
                <Button type="submit" disabled={checking || catalogLoading} title={submitButtonLabel}>
                  <Calculator className="h-4 w-4 shrink-0" aria-hidden="true" />
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
	                <div className="grid gap-3 rounded-md border border-dashed border-border bg-slate-50 p-3 md:grid-cols-[minmax(260px,1fr)_minmax(180px,240px)]">
	                  <Field label="제품명">
	                    <select className={inputClassName} value={selectedProductId} onChange={handleProductChange}>
	                      <option value={noProductValue}>직접 입력</option>
	                      {productCases.map((product) => (
	                        <option key={product.id} value={product.id}>
	                          {product.drawingName}
	                          {product.isNew ? " (신규)" : ""} · {product.studType ?? "-"} · {unitValue(product.heightSeismicMm, "mm")}
	                        </option>
	                      ))}
	                    </select>
	                  </Field>
	                  <div className="grid content-end">
	                    <div className="min-h-10 rounded-md border border-border bg-white px-3 py-2 text-sm text-muted-foreground">
	                      {productMessage ?? "제품명을 선택하면 보드, 스터드, 간격, 높이를 자동 입력합니다."}
	                    </div>
	                  </div>
	                </div>

	                {renderCalculationModeControl()}

	                <div className="grid gap-3 sm:grid-cols-3">
                  {renderBoardSlot("후면 외측 보드", "rearBoardOuterKind", "rearBoardOuterThickness", {
                    disabled: selectedRearBoardInputsDisabled,
                  })}
                  {renderBoardSlot("후면 중간 보드", "rearBoardMiddleKind", "rearBoardMiddleThickness", {
                    disabled: selectedRearBoardInputsDisabled,
                  })}
                  {renderBoardSlot("후면 내측 보드", "rearBoardInnerKind", "rearBoardInnerThickness", {
                    disabled: selectedIsOneSideFinish,
                    fixedThickness: selectedFixedRearBoardThickness ?? undefined,
                    required: selectedHasFixedRearBoard,
                  })}
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

                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Field label="검토 CASE" error={errors.designCase?.message}>
                    <select className={inputClassName} {...register("designCase")}>
                      {designCaseOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="스터드 간격 mm" error={errors.spacingMm?.message}>
                    <input className={inputClassName} type="number" step="1" {...register("spacingMm")} />
                  </Field>
                  <Field label={heightFieldLabel} error={errors.spanMm?.message}>
                    <input className={inputClassName} type="number" step="1" {...register("spanMm")} />
                  </Field>
                  <Field label="활하중 kN/m²" error={errors.liveLoadKnM2?.message}>
                    <input className={inputClassName} type="number" step="0.01" {...register("liveLoadKnM2")} />
                  </Field>
                  <Field label="연직하중 kN/m" error={errors.verticalLoadKnM?.message}>
                    <input className={inputClassName} type="number" step="0.01" min="0" {...register("verticalLoadKnM")} />
                  </Field>
                  <Field label="처짐한계 L/" error={errors.deflectionLimitDenom?.message}>
                    <input className={inputClassName} type="number" step="1" {...register("deflectionLimitDenom")} />
                  </Field>
                  <Field label="앵커 성능 kN/개" error={errors.anchorCapacityKn?.message}>
                    <input className={inputClassName} type="number" step="0.01" {...register("anchorCapacityKn")} />
                  </Field>
                  <Field label="앵커 간격 mm" error={errors.anchorSpacingMm?.message}>
                    <input
                      className={inputClassName}
                      type="number"
                      min={anchorSpacingMinMm}
                      max={anchorSpacingMaxMm}
                      step={anchorSpacingIncrementMm}
                      {...register("anchorSpacingMm")}
                    />
                  </Field>
                </div>

                <div className="rounded-md border border-border bg-white px-3 py-2 text-sm font-medium text-muted-foreground">
                  런너는 0.8T 이상 전부 적용 가능
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
                <SectionPreview
                  rearBoards={selectedRearBoards}
                  frontBoards={selectedFrontBoards}
                  stud={selectedStud}
                  studMethod={selectedStudMethod}
                />
              </div>
            </div>
          </section>
        </form>

        <aside className="grid content-start gap-5">
          <section className="rounded-md border border-border bg-white p-5 shadow-panel">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold">결과</h2>
              <Button type="button" variant="secondary" disabled={!reportData} onClick={handlePrintReport} title="계산서 출력">
                <Printer className="h-4 w-4 shrink-0" aria-hidden="true" />
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
                <Printer className="h-4 w-4 shrink-0" aria-hidden="true" />
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

function unitValue(value: number | null, unit: string) {
  return value === null ? "-" : `${formatNumber(value)} ${unit}`;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("ko-KR", {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 1,
  }).format(value);
}

function liveLoadKnM2ToKgM2(value: number) {
  return (value * 1000.0) / gravity;
}

function createProductPreset(
  product: ProgressCase,
  boards: BoardProperty[],
  studs: StudSection[],
  studMethods: StudMethod[],
) {
  const warnings: string[] = [];
  const values: Partial<CheckFormValues> = {
    calculationMode: "heightCheck",
  };
  if (product.spacingMm !== null) {
    values.spacingMm = product.spacingMm;
  }
  if (product.anchorSpacingMm !== null) {
    values.anchorSpacingMm = normalizeAnchorSpacing(product.anchorSpacingMm, warnings);
  }
  if (product.heightSeismicMm !== null) {
    values.spanMm = product.heightSeismicMm;
  }

  const studGroup = resolveProductStudGroup(product.studType, studs, warnings);
  const studMethod = resolveProductStudMethod(product.studType, studGroup, studMethods, warnings);
  const studSpec = resolveProductStudSpec(product.studSize, studGroup, studs, warnings);
  values.studGroup = studGroup;
  values.studMethod = studMethod;
  values.studSpec = studSpec;

  applyFrontBoardPreset(values, product.frontBoards, boards, warnings);
  applyRearBoardPreset(values, product.rearBoards, boards, warnings, studGroup, studMethod);

  return { values, warnings };
}

function applyFrontBoardPreset(
  values: Partial<CheckFormValues>,
  boardLabels: string[],
  boards: BoardProperty[],
  warnings: string[],
) {
  const parsedBoards = boardLabels.map((label) => resolveProductBoard(label, boards, warnings));
  setBoardSlot(values, "frontBoardInnerKind", "frontBoardInnerThickness", parsedBoards[0] ?? null);
  setBoardSlot(values, "frontBoardMiddleKind", "frontBoardMiddleThickness", parsedBoards[1] ?? null);
  setBoardSlot(values, "frontBoardOuterKind", "frontBoardOuterThickness", parsedBoards[2] ?? null);
}

function applyRearBoardPreset(
  values: Partial<CheckFormValues>,
  boardLabels: string[],
  boards: BoardProperty[],
  warnings: string[],
  studGroup: string,
  studMethod: string,
) {
  if (isOneSideFinishMethod(studMethod)) {
    setBoardSlot(values, "rearBoardOuterKind", "rearBoardOuterThickness", null);
    setBoardSlot(values, "rearBoardMiddleKind", "rearBoardMiddleThickness", null);
    setBoardSlot(values, "rearBoardInnerKind", "rearBoardInnerThickness", null);
    return;
  }

  const fixedRearThickness = fixedRearBoardThicknessForGroup(studGroup);
  if (fixedRearThickness !== null) {
    const fixedKind = fixedRearBoardKindForGroup(studGroup);
    const productBoard = boardLabels.map((label) => parseBoardLabel(label)).find((board) => board !== null);
    const kind = fixedKind ?? productBoard?.kind ?? "방화";
    setBoardSlot(values, "rearBoardOuterKind", "rearBoardOuterThickness", null);
    setBoardSlot(values, "rearBoardMiddleKind", "rearBoardMiddleThickness", null);
    setBoardSlot(values, "rearBoardInnerKind", "rearBoardInnerThickness", { kind, thickness: fixedRearThickness });
    if (productBoard && !isSameThickness(productBoard.thickness, fixedRearThickness)) {
      warnings.push(`${studGroup} 후면 보드는 ${fixedRearThickness}T 고정값으로 적용했습니다.`);
    }
    return;
  }

  const parsedBoards = boardLabels.map((label) => resolveProductBoard(label, boards, warnings));
  if (parsedBoards.length >= 3) {
    setBoardSlot(values, "rearBoardOuterKind", "rearBoardOuterThickness", parsedBoards[0] ?? null);
    setBoardSlot(values, "rearBoardMiddleKind", "rearBoardMiddleThickness", parsedBoards[1] ?? null);
    setBoardSlot(values, "rearBoardInnerKind", "rearBoardInnerThickness", parsedBoards[2] ?? null);
    return;
  }
  setBoardSlot(values, "rearBoardOuterKind", "rearBoardOuterThickness", null);
  setBoardSlot(values, "rearBoardMiddleKind", "rearBoardMiddleThickness", parsedBoards[0] ?? null);
  setBoardSlot(values, "rearBoardInnerKind", "rearBoardInnerThickness", parsedBoards[1] ?? null);
}

function setBoardSlot(
  values: Partial<CheckFormValues>,
  kindField: BoardKindField,
  thicknessField: BoardThicknessField,
  board: { kind: string; thickness: number } | null,
) {
  values[kindField] = board?.kind ?? noneBoardValue;
  values[thicknessField] = board ? thicknessValue(board.thickness) : noThicknessValue;
}

function resolveProductBoard(label: string, boards: BoardProperty[], warnings: string[]) {
  const parsed = parseBoardLabel(label);
  if (!parsed) {
    warnings.push(`${label} 보드를 해석하지 못했습니다.`);
    return null;
  }
  const matched = boards.find((board) => board.kind === parsed.kind && isSameThickness(board.thickness, parsed.thickness));
  if (!matched) {
    warnings.push(`${label} 보드가 자재 DB에 없습니다.`);
    return null;
  }
  if (!matched.is_complete) {
    warnings.push(`${label} 보드는 물성이 미완성입니다.`);
  }
  return parsed;
}

function parseBoardLabel(label: string) {
  const matched = label.trim().match(/^(.+?)(\d+(?:\.\d+)?)$/);
  if (!matched) {
    return null;
  }
  return {
    kind: matched[1],
    thickness: Number(matched[2]),
  };
}

function resolveProductStudGroup(studType: string | null, studs: StudSection[], warnings: string[]) {
  const normalized = (studType ?? "").replace(/\s/g, "").toUpperCase();
  const preferredGroup =
    normalized.startsWith("C-STUD")
      ? "C-STUD"
      : normalized.startsWith("CH-STUD")
        ? "CH-STUD"
        : normalized.startsWith("R-STUD")
          ? "R-STUD"
          : normalized.startsWith("MP-STUD")
            ? "MP-STUD"
            : normalized.startsWith("T.SILENT-STUD")
              ? "T.silent-STUD"
              : null;
  if (preferredGroup && studs.some((stud) => stud.group === preferredGroup)) {
    return preferredGroup;
  }
  warnings.push(`${studType ?? "알 수 없는 스터드"}는 현재 DB 그룹과 직접 매칭되지 않아 기본 C-STUD로 적용했습니다.`);
  return defaultValues.studGroup;
}

function resolveProductStudMethod(
  studType: string | null,
  studGroup: string,
  studMethods: StudMethod[],
  warnings: string[],
) {
  const methodOptions = studMethodOptions(studMethods, studGroup).map((option) => option.value);
  const preferredMethod =
    (studType ?? "").includes("이중") && methodOptions.includes(oneSideFinishMethod)
      ? oneSideFinishMethod
      : (studType ?? "").includes("이중")
        ? doubleStudMethod
        : fallbackStudMethod;
  if (methodOptions.includes(preferredMethod)) {
    return preferredMethod;
  }
  const fallbackMethod = methodOptions[0] ?? fallbackStudMethod;
  if (preferredMethod !== fallbackMethod) {
    warnings.push(`${studType ?? studGroup} 시공방식은 ${fallbackMethod}로 대체했습니다.`);
  }
  return fallbackMethod;
}

function resolveProductStudSpec(studSize: string | null, studGroup: string, studs: StudSection[], warnings: string[]) {
  const groupStuds = studs.filter((stud) => stud.group === studGroup);
  const parsedSize = parseStudSize(studSize);
  const preferredSpec = parsedSize ? productSpecName(studGroup, parsedSize) : null;
  const exact = preferredSpec ? groupStuds.find((stud) => stud.name === preferredSpec) : undefined;
  if (exact) {
    return exact.name;
  }
  const closest = parsedSize ? closestStudByHeight(groupStuds, parsedSize.height) : undefined;
  if (closest) {
    warnings.push(`${studSize ?? "-"} 규격은 ${closest.name}로 대체했습니다.`);
    return closest.name;
  }
  warnings.push(`${studSize ?? "-"} 규격을 찾지 못해 기본 규격을 적용했습니다.`);
  return firstStudSpecValue(studs, studGroup);
}

function parseStudSize(studSize: string | null) {
  const matched = (studSize ?? "").match(/^(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)/);
  if (!matched) {
    return null;
  }
  return {
    height: Number(matched[1]),
    width: Number(matched[2]),
    thickness: Number(matched[3]),
  };
}

function productSpecName(studGroup: string, size: { height: number; width: number; thickness: number }) {
  const height = Math.round(size.height);
  const width = Math.round(size.width);
  const thicknessCode = String(Math.round(size.thickness * 10)).padStart(2, "0");
  if (studGroup === "C-STUD" || studGroup === "R-STUD") {
    return `${height}S-${width}-${thicknessCode}`;
  }
  if (studGroup === "CH-STUD" || studGroup === "CH-STUD(개량형)") {
    return `${height}CHS-${thicknessCode}`;
  }
  if (studGroup === "MP-STUD" || studGroup === "RV-STUD") {
    return `${studGroup.split("-")[0]}-${height}`;
  }
  return null;
}

function closestStudByHeight(studs: StudSection[], height: number) {
  return studs
    .map((stud) => ({ stud, distance: Math.abs(stud.H - height) }))
    .sort((left, right) => left.distance - right.distance)[0]?.stud;
}

function boardKindOptions(boards: BoardProperty[] | undefined, requiredThickness?: number, includeNone = true) {
  const source =
    boards && boards.length > 0
      ? boards
      : [{ kind: "방화", thickness: 19, mass_kg_m2: 16.1, Fy: 0, Fu: 0, E_GPa: 0, is_complete: true, missing_fields: [] }];
  const kindMap = new Map<string, BoardProperty[]>();
  for (const board of source) {
    if (requiredThickness !== undefined && !isSameThickness(board.thickness, requiredThickness)) {
      continue;
    }
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
  return includeNone ? [{ value: noneBoardValue, label: "없음", disabled: false }, ...kindOptions] : kindOptions;
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

function normalizeAnchorSpacing(value: number, warnings: string[]) {
  const rounded = Math.round(value / anchorSpacingIncrementMm) * anchorSpacingIncrementMm;
  const limited = Math.min(anchorSpacingMaxMm, Math.max(anchorSpacingMinMm, rounded));
  if (limited !== value) {
    warnings.push(`앵커 간격은 ${anchorSpacingMinMm}~${anchorSpacingMaxMm}mm 범위의 50mm 단위로 보정했습니다.`);
  }
  return limited;
}

function boardKindForFixedThickness(
  boards: BoardProperty[],
  thickness: number,
  currentKind: string | undefined,
  requiredKind?: string,
) {
  const completeBoards = boards.filter((board) => board.is_complete && isSameThickness(board.thickness, thickness));
  if (requiredKind) {
    return completeBoards.find((board) => board.kind === requiredKind)?.kind ?? null;
  }
  const current = completeBoards.find((board) => board.kind === currentKind);
  const preferred = completeBoards.find((board) => board.kind === "방화");
  const fallback = completeBoards.sort((left, right) => left.kind.localeCompare(right.kind, "ko-KR"))[0];
  return (current ?? preferred ?? fallback)?.kind ?? null;
}

function thicknessValue(thickness: number) {
  return String(thickness);
}

function isSameThickness(left: number, right: number) {
  return Math.abs(left - right) < 1e-6;
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
  const methods = uniqueValues(matchedMethods).filter((method) => method !== "겹침");
  if (
    normalizeStudType(group) === "C-STUD"
    && methods.includes(doubleStudMethod)
    && !methods.includes(oneSideFinishMethod)
  ) {
    methods.push(oneSideFinishMethod);
  }
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

function isOneSideFinishMethod(method: string | undefined) {
  return (method ?? "").replace(/\s/g, "") === oneSideFinishMethod;
}

function fixedRearBoardThicknessForGroup(group: string) {
  if (!isChStudGroup(group)) {
    return isIStudGroup(group) ? iStudRearBoardThicknessMm : null;
  }
  return group.includes("개량형") ? chStudImprovedRearBoardThicknessMm : chStudRearBoardThicknessMm;
}

function fixedRearBoardKindForGroup(group: string) {
  return isIStudGroup(group) ? iStudRearBoardKind : null;
}

function fixedRearBoardLabelForGroup(group: string) {
  return isIStudGroup(group) ? "I 연결" : "CH 끼움";
}

function isChStudGroup(group: string) {
  return group.replace(/\s/g, "").toUpperCase().startsWith("CH-STUD");
}

function isIStudGroup(group: string) {
  return group.replace(/\s/g, "").toUpperCase() === "I-STUD";
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

function rearBoardPayloads(values: CheckFormValues) {
  if (isOneSideFinishMethod(values.studMethod)) {
    return [];
  }

  const fixedRearBoardThickness = fixedRearBoardThicknessForGroup(values.studGroup);
  const fixedRearBoardKind = fixedRearBoardKindForGroup(values.studGroup);
  if (fixedRearBoardThickness !== null) {
    return compactBoardPayloads([
      boardSelection(fixedRearBoardKind ?? values.rearBoardInnerKind, thicknessValue(fixedRearBoardThickness)),
    ]);
  }
  return compactBoardPayloads([
    boardSelection(values.rearBoardOuterKind, values.rearBoardOuterThickness),
    boardSelection(values.rearBoardMiddleKind, values.rearBoardMiddleThickness),
    boardSelection(values.rearBoardInnerKind, values.rearBoardInnerThickness),
  ]);
}

function buildPayload(values: CheckFormValues): WallCheckPayload {
  return {
    rear_boards: rearBoardPayloads(values),
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
    design_case: values.designCase,
    strength_check_mode: values.strengthCheckMode,
    horizontal_load_kg_m2: liveLoadKnM2ToKgM2(values.liveLoadKnM2),
    live_load_kN_m2: values.liveLoadKnM2,
    vertical_load_kN_m: values.verticalLoadKnM,
    spacing_mm: values.spacingMm,
    span_mm: values.spanMm,
    deflection_limit_denom: values.deflectionLimitDenom,
    bolt: {
      diameter: hiddenBoltDiameter,
      yield_strength: hiddenBoltYieldStrength,
      pitch: [values.boltPitchOuter, values.boltPitchMiddle, values.boltPitchInner],
      count: [hiddenBoltCountOuter, hiddenBoltCountMiddle, hiddenBoltCountInner],
    },
    seismic: {
      S: values.seismicS,
      site_class: values.seismicSiteClass,
      s5_bedrock_depth_unknown: values.seismicSiteClass === "S5" && values.s5BedrockDepthUnknown,
      Ip: values.seismicIp,
    },
    omega: hiddenOmega,
    anchor_capacity_kN: values.anchorCapacityKn,
    anchor_spacing_mm: values.anchorSpacingMm,
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
  const designCaseLabel = designCaseOptions.find((option) => option.value === values.designCase)?.label ?? values.designCase;
  const studAssembly = createStudAssembly(stud, values.studMethod);
  const fixedRearBoardThickness = fixedRearBoardThicknessForGroup(values.studGroup);
  const fixedRearBoardKind = fixedRearBoardKindForGroup(values.studGroup);
  const isOneSideFinish = isOneSideFinishMethod(values.studMethod);

  return {
    generatedAt: new Date().toISOString(),
    calculationMode: values.calculationMode,
    rearBoards:
      isOneSideFinish
        ? [
            reportBoardSlot("후면 3번(외측)", noneBoardValue, noThicknessValue, boards),
            reportBoardSlot("후면 2번(중간)", noneBoardValue, noThicknessValue, boards),
            reportBoardSlot("후면 1번(내측)", noneBoardValue, noThicknessValue, boards),
          ]
        : fixedRearBoardThickness === null
        ? [
            reportBoardSlot("후면 3번(외측)", values.rearBoardOuterKind, values.rearBoardOuterThickness, boards),
            reportBoardSlot("후면 2번(중간)", values.rearBoardMiddleKind, values.rearBoardMiddleThickness, boards),
            reportBoardSlot("후면 1번(내측)", values.rearBoardInnerKind, values.rearBoardInnerThickness, boards),
          ]
        : [
            reportBoardSlot("후면 3번(외측)", noneBoardValue, noThicknessValue, boards),
            reportBoardSlot("후면 2번(중간)", noneBoardValue, noThicknessValue, boards),
            reportBoardSlot(
              `후면 1번(${fixedRearBoardLabelForGroup(values.studGroup)})`,
              fixedRearBoardKind ?? values.rearBoardInnerKind,
              thicknessValue(fixedRearBoardThickness),
              boards,
            ),
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
      multiplier: studAssembly.multiplier,
      H: stud?.H ?? null,
      totalH: studAssembly.totalH,
      gapMm: studAssembly.gapMm,
      connectionInertiaFactor: studAssembly.connectionInertiaFactor,
      sectionModulusDepth: studAssembly.sectionModulusDepth,
      B: stud?.B ?? null,
      t: stud?.t ?? null,
      A: studAssembly.A,
      IxRaw: studAssembly.IxRaw,
      SxRaw: studAssembly.SxRaw,
      Ix: studAssembly.Ix,
      Sx: studAssembly.Sx,
    },
    geometry: {
      spacingMm: values.spacingMm,
      spanMm: values.spanMm,
      deflectionLimitDenom: values.deflectionLimitDenom,
      anchorSpacingMm: values.anchorSpacingMm,
      anchorCapacityKn: values.anchorCapacityKn,
    },
    loads: {
      designCaseLabel,
      liveLoadKnM2: values.liveLoadKnM2,
      verticalLoadKnM: values.verticalLoadKnM,
      seismicS: values.seismicS,
      seismicSiteClass: siteClassLabel,
      s5BedrockDepthUnknown: values.seismicSiteClass === "S5" && values.s5BedrockDepthUnknown,
      seismicIp: values.seismicIp,
    },
    bolts: {
      outerCount: hiddenBoltCountOuter,
      middleCount: hiddenBoltCountMiddle,
      innerCount: hiddenBoltCountInner,
      outerPitch: values.boltPitchOuter,
      middlePitch: values.boltPitchMiddle,
      innerPitch: values.boltPitchInner,
    },
    result,
  };
}

function studMultiplierForMethod(method: string) {
  return method.includes("맞댐") || isCentralJointMethod(method) ? 2.0 : 1.0;
}

function isCentralJointMethod(method: string) {
  return method.replace(/\s/g, "").includes("중앙부이음");
}

function createStudAssembly(stud: StudSection | undefined, method: string) {
  if (!stud) {
    return {
      multiplier: studMultiplierForMethod(method),
      totalH: null,
      gapMm: isCentralJointMethod(method) ? centralJointStudGapMm : null,
      connectionInertiaFactor: isCentralJointMethod(method) ? studConnectionInertiaFactor : null,
      sectionModulusDepth: null,
      A: null,
      IxRaw: null,
      SxRaw: null,
      Ix: null,
      Sx: null,
    };
  }

  if (isCentralJointMethod(method)) {
    const distance = stud.H + centralJointStudGapMm / 2;
    const Ix = 2 * (stud.A * distance ** 2 + stud.Ix);
    return {
      multiplier: 2,
      totalH: 2 * stud.H + centralJointStudGapMm,
      gapMm: centralJointStudGapMm,
      connectionInertiaFactor: studConnectionInertiaFactor,
      sectionModulusDepth: stud.H,
      A: 2 * stud.A,
      IxRaw: Ix,
      SxRaw: (Ix / stud.H) * 2,
      Ix,
      Sx: (Ix / stud.H) * 2,
    };
  }

  const multiplier = studMultiplierForMethod(method);
  return {
    multiplier,
    totalH: stud.H,
    gapMm: null,
    connectionInertiaFactor: null,
    sectionModulusDepth: stud.H,
    A: stud.A * multiplier,
    IxRaw: null,
    SxRaw: null,
    Ix: stud.Ix * multiplier,
    Sx: stud.Sx * multiplier,
  };
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
      Fu: null,
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
    Fu: board?.Fu ?? null,
    E_GPa: board?.E_GPa ?? null,
  };
}
