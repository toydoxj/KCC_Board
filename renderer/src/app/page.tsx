"use client";

import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Printer } from "lucide-react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { CalculationReport, type CalculationReportData, type ReportBoardSlot } from "@/components/calculation-report";
import { StructurePreview } from "@/components/structure-preview";
import { InputWorkspace } from "@/components/input-workspace";
import { SummaryReport } from "@/components/summary-report";
import { governingHeight } from "@/lib/height-review";
import { ResultPanel } from "@/components/result-panel";
import { Button } from "@/components/ui/button";
import { Field, inputClassName } from "@/components/ui/field";
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
import { APP_VERSION } from "@/lib/app-info";
import { cn } from "@/lib/utils";
import { useCheckStore } from "@/store/check-store";

const noneBoardValue = "NONE";
const noThicknessValue = "";
const fallbackStudMethod = "기본";
const hiddenOmega = 1.5;
const hiddenBoltDiameter = 3.5;
// 피스 항복강도 Fy(전단강도 Fv = 0.6 × Fy). 제원 변경(2026-07): 480 → 340
const hiddenBoltYieldStrength = 340;
const hiddenBoltCountOuter = 2;
const hiddenBoltCountMiddle = 2;
const hiddenBoltCountInner = 1;
const gravity = 9.81;
const anchorSpacingMinMm = 150;
const anchorSpacingMaxMm = 600;
const anchorSpacingIncrementMm = 50;
const preferredDefaultBoardThicknessMm = 12.5;
const bilateralSinglePlyPitchMm = 300;
const centralJointStudGapMm = 25;
const studConnectionInertiaFactor = 1;
const chStudRearBoardThicknessMm = 25;
const chStudImprovedRearBoardThicknessMm = 12.5;
const doubleStudMethod = "이중스터드";
const oneSideFinishMethod = "일면마감";
const calculationModeOptions: Array<{ value: CalculationMode; label: string }> = [
  { value: "heightCheck", label: "높이검토" },
  { value: "maxHeight", label: "최대높이" },
  { value: "anchorHeight", label: "런너 고정못 간격" },
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
  boltPitchOuter: z.coerce.number().min(100,"100mm 이상 입력해야 합니다.").max(900,"900mm 이하로 입력해야 합니다."),
  boltPitchMiddle: z.coerce.number().min(100,"100mm 이상 입력해야 합니다.").max(900,"900mm 이하로 입력해야 합니다."),
  boltPitchInner: z.coerce.number().min(100,"100mm 이상 입력해야 합니다.").max(900,"900mm 이하로 입력해야 합니다."),
  seismicS: z.coerce.number().positive(),
  seismicSiteClass: z.enum(["S1", "S2", "S3", "S4", "S5"]),
  s5BedrockDepthUnknown: z.boolean(),
  seismicIp: z.coerce.number().positive(),
});

export type CheckFormValues = z.infer<typeof formSchema>;
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
  calculationMode: "anchorHeight",
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
  studMethod: "기본",
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
  const selectedHasFixedRearBoard = selectedFixedRearBoardThickness !== null || isIStudGroup(selectedStudGroup);
  const selectedIsOneSideReview = isOneSideReviewMethod(selectedStudMethod);
  const selectedRearBoardInputsDisabled = selectedHasFixedRearBoard || selectedIsOneSideReview;
  const selectedRearBoards = useMemo(
    () =>
      compactBoards(
        catalog?.boards ?? [],
        selectedIsOneSideReview
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
      selectedIsOneSideReview,
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
  const bilateralSinglePly = selectedFrontBoards.length === 1 && selectedRearBoards.length === 1;
  // Keep independent defaults and user-selected values for single- and multi-ply contexts.
  const innerPitchContexts = useRef({ singleMode: false, single: bilateralSinglePlyPitchMm, multi: defaultValues.boltPitchInner });
  useEffect(() => {
    const saved = innerPitchContexts.current;
    if (saved.singleMode === bilateralSinglePly) return;
    const current = Number(getValues("boltPitchInner"));
    if (saved.singleMode) saved.single = current;
    else saved.multi = current;
    saved.singleMode = bilateralSinglePly;
    setValue("boltPitchInner", bilateralSinglePly ? saved.single : saved.multi, { shouldDirty: true, shouldValidate: true });
  }, [bilateralSinglePly, getValues, setValue]);

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
        ? "런너 고정못 산정 기준높이 mm"
        : "산정 높이 mm";
  const submitButtonLabel =
    selectedCalculationMode === "heightCheck"
      ? "높이 검토"
      : selectedCalculationMode === "anchorHeight"
        ? "런너 고정못 간격 산정"
        : "최대높이 산정";
  const calculationModeRegister = register("calculationMode");
  const studGroupRegister = register("studGroup");
  const [reportData, setReportData] = useState<CalculationReportData | null>(null);
  const [savingPdf, setSavingPdf] = useState(false);
  const [mirrorRear, setMirrorRear] = useState(false);
  const [pdfMessage, setPdfMessage] = useState<string | null>(null);
  const calculationSequence = useRef(0);
  const calculationAbort = useRef<AbortController | null>(null);

  useEffect(() => {
    if (selectedRearBoardInputsDisabled) { setMirrorRear(false); return; }
    if (!mirrorRear) return;
    const pairs = [
      ["frontBoardInnerKind","rearBoardInnerKind"],
      ["frontBoardInnerThickness","rearBoardInnerThickness"],
      ["frontBoardMiddleKind","rearBoardMiddleKind"],
      ["frontBoardMiddleThickness","rearBoardMiddleThickness"],
      ["frontBoardOuterKind","rearBoardOuterKind"],
      ["frontBoardOuterThickness","rearBoardOuterThickness"],
    ] as const;
    for (const [front,rear] of pairs) {
      const value = formValues[front] ?? "";
      if (getValues(rear) !== value) setValue(rear,value,{shouldDirty:true,shouldValidate:true});
    }
  },[mirrorRear,selectedRearBoardInputsDisabled,formValues.frontBoardInnerKind,formValues.frontBoardInnerThickness,formValues.frontBoardMiddleKind,formValues.frontBoardMiddleThickness,formValues.frontBoardOuterKind,formValues.frontBoardOuterThickness,getValues,setValue]);

  useEffect(() => {
    if (selectedIsOneSideReview) {
      setRearBoardValue("rearBoardOuterKind", noneBoardValue, formValues.rearBoardOuterKind);
      setRearBoardValue("rearBoardOuterThickness", noThicknessValue, formValues.rearBoardOuterThickness);
      setRearBoardValue("rearBoardMiddleKind", noneBoardValue, formValues.rearBoardMiddleKind);
      setRearBoardValue("rearBoardMiddleThickness", noThicknessValue, formValues.rearBoardMiddleThickness);
      setRearBoardValue("rearBoardInnerKind", noneBoardValue, formValues.rearBoardInnerKind);
      setRearBoardValue("rearBoardInnerThickness", noThicknessValue, formValues.rearBoardInnerThickness);
      return;
    }

    if (isIStudGroup(selectedStudGroup)) {
      setRearBoardValue("rearBoardOuterKind", noneBoardValue, formValues.rearBoardOuterKind);
      setRearBoardValue("rearBoardOuterThickness", noThicknessValue, formValues.rearBoardOuterThickness);
      setRearBoardValue("rearBoardMiddleKind", noneBoardValue, formValues.rearBoardMiddleKind);
      setRearBoardValue("rearBoardMiddleThickness", noThicknessValue, formValues.rearBoardMiddleThickness);
      if (catalog && (!formValues.rearBoardInnerKind || formValues.rearBoardInnerKind === noneBoardValue)) {
        setRearBoardValue("rearBoardInnerKind", "방화", formValues.rearBoardInnerKind);
        setRearBoardValue("rearBoardInnerThickness", defaultCompleteThicknessValue(catalog.boards,"방화"), formValues.rearBoardInnerThickness);
      }
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
    selectedIsOneSideReview,
    selectedStudGroup,
    setErrorMessage,
    setValue,
  ]);

  async function onSubmit(values: CheckFormValues) {
    calculationAbort.current?.abort();
    const abortController = new AbortController();
    calculationAbort.current = abortController;
    const sequence = calculationSequence.current + 1;
    calculationSequence.current = sequence;
    const submittedValues = structuredClone(values);

    setChecking(true);
    setResult(null);
    setReportData(null);
    setErrorMessage(null);
    setPdfMessage(null);
    try {
      let nextValues = submittedValues;
      let nextResult = await checkWall(buildPayload(submittedValues), abortController.signal);

      const nextTargetHeight =
        governingHeight(nextResult);
      if (
        submittedValues.calculationMode !== "heightCheck"
        && nextTargetHeight > 0
        && nextTargetHeight !== submittedValues.spanMm
      ) {
        nextValues = {
          ...submittedValues,
          spanMm: nextTargetHeight,
        };
        nextResult = await checkWall(buildPayload(nextValues), abortController.signal);
        if (sequence !== calculationSequence.current) return;
        setValue("spanMm", nextValues.spanMm, {
          shouldDirty: true,
          shouldValidate: true,
        });
      }

      if (sequence !== calculationSequence.current) return;
      setResult(nextResult);
      setReportData(createReportData(nextValues, nextResult, catalog?.boards ?? [], catalog?.studs ?? []));
    } catch (error: unknown) {
      if (abortController.signal.aborted || sequence !== calculationSequence.current) return;
      setResult(null);
      setReportData(null);
      setErrorMessage(error instanceof Error ? error.message : "계산을 완료하지 못했습니다.");
    } finally {
      if (sequence === calculationSequence.current) {
        setChecking(false);
        calculationAbort.current = null;
      }
    }
  }

  function handleReset() {
    innerPitchContexts.current = { singleMode: false, single: bilateralSinglePlyPitchMm, multi: defaultValues.boltPitchInner };
    setMirrorRear(false);
    reset(defaultValues);
    setResult(null);
    setReportData(null);
    setErrorMessage(null);
    setPdfMessage(null);
  }

  async function handlePrintReport(kind: "detail" | "summary" = "detail") {
    if (!reportData) {
      return;
    }
    setSavingPdf(true);
    setPdfMessage(null);
    document.documentElement.dataset.printKind = kind;
    try {
      if (window.kccBoard?.saveReportPdf) {
        const response = await window.kccBoard.saveReportPdf({
          suggestedFileName: kind === "summary" ? `요약_${createPdfFileName(reportData)}` : createPdfFileName(reportData),
        });
        if (!response.success) {
          throw new Error(response.error ?? "PDF 저장을 완료하지 못했습니다.");
        }
        if (!response.canceled) {
          setPdfMessage(`PDF 저장 완료: ${response.path ?? "선택한 경로"}`);
        }
      } else {
        window.print();
      }
    } catch (error: unknown) {
      setPdfMessage(error instanceof Error ? error.message : "PDF 저장 중 오류가 발생했습니다.");
    } finally {
      delete document.documentElement.dataset.printKind;
      setSavingPdf(false);
    }
  }

  function clearCalculationResult() {
    calculationAbort.current?.abort();
    calculationAbort.current = null;
    calculationSequence.current += 1;
    setChecking(false);
    setResult(null);
    setReportData(null);
    setPdfMessage(null);
  }

  function handleCalculationModeChange(event: ChangeEvent<HTMLInputElement>) {
    calculationModeRegister.onChange(event);
    if (event.target.value !== "heightCheck" && !(Number(getValues("spanMm")) > 0)) {
      setValue("spanMm",defaultValues.spanMm,{shouldValidate:true});
    }
    clearCalculationResult();
  }

  function renderBoardSlot(
    label: string,
    kindField: BoardKindField,
    thicknessField: BoardThicknessField,
    options: { disabled?: boolean; fixedThickness?: number; required?: boolean } = {},
  ) {
    const kindRegister = register(kindField);
    const selectedKind = (formValues[kindField] as string | undefined) ?? noneBoardValue;
    const selectedThickness = (formValues[thicknessField] as string | undefined) ?? noThicknessValue;
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
                  ? defaultCompleteThicknessValue(catalog?.boards ?? [], event.target.value)
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
            value={selectedThickness}
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
            <h1 className="text-xl font-semibold tracking-normal">KCC Board 구조검토 프로그램</h1>
            <p className="mt-1 text-sm text-muted-foreground">v{APP_VERSION}</p>
          </div>
          <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:flex-nowrap sm:justify-end">
            <div className="shrink-0 whitespace-nowrap rounded-md border border-border px-3 py-2 text-sm font-medium">
              API {catalogLoading ? "확인 중" : catalog ? "연결됨" : "대기"}
            </div>
          </div>
        </div>
      </div>

      <div className="review-workspace mx-auto grid max-w-[1600px] gap-6 px-5 py-7 2xl:grid-cols-[minmax(0,1fr)_380px]">
        <form onSubmit={handleSubmit(onSubmit)} onChange={clearCalculationResult} className="min-w-0">
          <InputWorkspace
            register={register} setValue={setValue} values={formValues} errors={errors}
            groups={studGroupOptions(catalog?.studs)}
            methods={studMethodOptions(catalog?.studMethods,selectedStudGroup)}
            specs={studSpecOptions(catalog?.studs,selectedStudGroup)} stud={selectedStud}
            siteClasses={siteClassOptions}
            onStudGroupChange={(event)=>{
              studGroupRegister.onChange(event);
              setMirrorRear(false);
              setValue("studMethod",firstStudMethodValue(catalog?.studMethods??[],event.target.value),{shouldDirty:true,shouldValidate:true});
              setValue("studSpec",firstStudSpecValue(catalog?.studs??[],event.target.value),{shouldDirty:true,shouldValidate:true});
            }}
            onModeChange={handleCalculationModeChange} onReset={handleReset}
            busy={checking||catalogLoading} submitLabel={submitButtonLabel}
            mirrorRear={mirrorRear} onMirrorChange={setMirrorRear} canMirror={!selectedRearBoardInputsDisabled}
            notice={<>
              {errorMessage&&<div role="alert" className="input-error">{errorMessage}</div>}
              {Object.keys(errors).length>0&&<div role="alert" className="input-error">입력값을 확인해 주세요. {Object.values(errors).map(e=>e.message).filter(Boolean).join(" ")}</div>}
            </>}
            frontSlots={[
              renderBoardSlot("1-1P","frontBoardInnerKind","frontBoardInnerThickness"),
              renderBoardSlot("1-2P","frontBoardMiddleKind","frontBoardMiddleThickness"),
              renderBoardSlot("1-3P","frontBoardOuterKind","frontBoardOuterThickness"),
            ]}
            rearSlots={[
              renderBoardSlot("2-1P","rearBoardInnerKind","rearBoardInnerThickness",{disabled:selectedIsOneSideReview,fixedThickness:selectedIsOneSideReview?undefined:selectedFixedRearBoardThickness??undefined,required:selectedHasFixedRearBoard&&!selectedIsOneSideReview}),
              renderBoardSlot("2-2P","rearBoardMiddleKind","rearBoardMiddleThickness",{disabled:selectedRearBoardInputsDisabled}),
              renderBoardSlot("2-3P","rearBoardOuterKind","rearBoardOuterThickness",{disabled:selectedRearBoardInputsDisabled}),
            ]}
            frontCount={selectedFrontBoards.length} rearCount={selectedRearBoards.length}
            preview={<StructurePreview rearBoards={selectedRearBoards} frontBoards={selectedFrontBoards} stud={selectedStud} studMethod={selectedStudMethod}/>}
          />
        </form>

        <aside className="grid content-start gap-5">
          <section className="rounded-md border border-border bg-white p-5 shadow-panel">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-semibold">결과</h2>
              <div className="flex flex-wrap gap-2">
              <Button type="button" variant="secondary" disabled={!reportData || checking} onClick={()=>document.getElementById("summary-preview")?.scrollIntoView({behavior:"smooth",block:"start"})}>요약페이지 미리보기</Button>
              <Button type="button" variant="secondary" disabled={!reportData || savingPdf || checking} onClick={()=>handlePrintReport("summary")} title="요약페이지 PDF 저장">요약페이지 PDF 저장</Button>
              <Button type="button" variant="secondary" disabled={!reportData || savingPdf || checking} onClick={()=>handlePrintReport()} title="계산서 PDF 저장">
                <Printer className="h-4 w-4 shrink-0" aria-hidden="true" />
                {savingPdf ? "PDF 저장 중" : "계산서PDF저장"}
              </Button>
              </div>
            </div>
            <ResultPanel result={result} mode={selectedCalculationMode} spanMm={reportData?.geometry.spanMm} />
          </section>
        </aside>
      </div>
      {reportData ? (
        <div className="screen-report mx-auto max-w-7xl px-5 pb-8">
          <section id="summary-preview" className="mb-5 rounded-md border border-border bg-white p-5 shadow-panel">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-semibold">요약페이지 미리보기</h2>
              <Button type="button" variant="secondary" disabled={savingPdf || checking} onClick={()=>handlePrintReport("summary")}>요약페이지 PDF 저장</Button>
            </div>
            <div className="summary-preview-scroll"><SummaryReport data={reportData}/></div>
          </section>
          <section className="rounded-md border border-border bg-white p-5 shadow-panel">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold">계산서 미리보기</h2>
              <Button type="button" disabled={savingPdf || checking} onClick={()=>handlePrintReport()} title="계산서 PDF 저장">
                <Printer className="h-4 w-4 shrink-0" aria-hidden="true" />
                {savingPdf ? "PDF 저장 중" : "계산서PDF저장"}
              </Button>
            </div>
            {pdfMessage ? <p className="mb-4 text-sm text-muted-foreground">{pdfMessage}</p> : null}
            <CalculationReport data={reportData} className="rounded-md border border-slate-200 p-6" />
          </section>
        </div>
      ) : null}
      {reportData ? (
        <div className="print-summary"><SummaryReport data={reportData}/></div>
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

function boardKindOptions(boards: BoardProperty[] | undefined, requiredThickness?: number, includeNone = true) {
  const source =
    boards && boards.length > 0
      ? boards
      : [{ kind: "방화", thickness: 19, mass_kg_m2: 16.1, Fy: 0, Fu: 0, E_GPa: 0, is_complete: true, missing_fields: [], yield_ratio: 0.65, yield_ratio_source: "시험" }];
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

function defaultCompleteThicknessValue(boards: BoardProperty[], kind: string) {
  if (kind === noneBoardValue) {
    return noThicknessValue;
  }
  const completeBoards = boards
    .filter((item) => item.kind === kind && item.is_complete)
    .sort((left, right) => left.thickness - right.thickness);
  const board =
    completeBoards.find((item) => isSameThickness(item.thickness, preferredDefaultBoardThicknessMm))
    ?? completeBoards[0];
  return board ? thicknessValue(board.thickness) : noThicknessValue;
}

function normalizeAnchorSpacing(value: number, warnings: string[]) {
  const rounded = Math.round(value / anchorSpacingIncrementMm) * anchorSpacingIncrementMm;
  const limited = Math.min(anchorSpacingMaxMm, Math.max(anchorSpacingMinMm, rounded));
  if (limited !== value) {
    warnings.push(`런너 고정못 간격은 ${anchorSpacingMinMm}~${anchorSpacingMaxMm}mm 범위의 50mm 단위로 보정했습니다.`);
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

function isOneSideReviewMethod(method: string | undefined) {
  const normalized = (method ?? "").replace(/\s/g, "");
  return normalized === oneSideFinishMethod || normalized === doubleStudMethod;
}

function fixedRearBoardThicknessForGroup(group: string) {
  if (!isChStudGroup(group)) {
    return null;
  }
  return group.includes("개량형") ? chStudImprovedRearBoardThicknessMm : chStudRearBoardThicknessMm;
}

function fixedRearBoardKindForGroup(group: string) {
  return null;
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
  if (isOneSideReviewMethod(values.studMethod)) {
    return [];
  }
  if (isIStudGroup(values.studGroup)) {
    return compactBoardPayloads([boardSelection(values.rearBoardInnerKind, values.rearBoardInnerThickness)]);
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

function createPdfFileName(report: CalculationReportData) {
  const date = new Date().toISOString().slice(0, 10).replaceAll("-", "");
  const stud = `${report.stud.group}_${report.stud.spec}`.replace(/[\\/:*?"<>|]/g, "_");
  return `KCC_구조검토계산서_${stud}_${date}.pdf`;
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
  const isOneSideReview = isOneSideReviewMethod(values.studMethod);

  return {
    generatedAt: new Date().toISOString(),
    calculationMode: values.calculationMode,
    rearBoards:
      isOneSideReview
        ? [
            reportBoardSlot("후면 3번(외측)", noneBoardValue, noThicknessValue, boards),
            reportBoardSlot("후면 2번(중간)", noneBoardValue, noThicknessValue, boards),
            reportBoardSlot("후면 1번(내측)", noneBoardValue, noThicknessValue, boards),
          ]
        : isIStudGroup(values.studGroup)
        ? [
            reportBoardSlot("후면 3번(외측)", noneBoardValue, noThicknessValue, boards),
            reportBoardSlot("후면 2번(중간)", noneBoardValue, noThicknessValue, boards),
            reportBoardSlot("후면 1번(I 연결)", values.rearBoardInnerKind, values.rearBoardInnerThickness, boards),
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
    const distance = stud.H + centralJointStudGapMm / 2 - stud.cy;
    const extremeFiber = stud.H + centralJointStudGapMm / 2;
    const Ix = 2 * (stud.A * distance ** 2 + stud.Ix);
    return {
      multiplier: 2,
      totalH: 2 * stud.H + centralJointStudGapMm,
      gapMm: centralJointStudGapMm,
      connectionInertiaFactor: studConnectionInertiaFactor,
      sectionModulusDepth: extremeFiber,
      A: 2 * stud.A,
      IxRaw: Ix,
      SxRaw: Ix / extremeFiber,
      Ix,
      Sx: Ix / extremeFiber,
    };
  }

  const multiplier = studMultiplierForMethod(method);
  return {
    multiplier,
    totalH: stud.H,
    gapMm: null,
    connectionInertiaFactor: null,
    sectionModulusDepth: Math.max(stud.cy, stud.H - stud.cy),
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
      yieldRatio: null,
      yieldRatioSource: null,
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
    yieldRatio: board?.yield_ratio ?? null,
    yieldRatioSource: board?.yield_ratio_source ?? null,
  };
}
