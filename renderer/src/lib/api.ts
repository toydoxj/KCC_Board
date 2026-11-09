export type ApiEnvelope<T> =
  | {
      success: true;
      data: T;
      error: null;
    }
  | {
      success: false;
      data: null;
      error: {
        code: string;
        message: string;
      };
    };

export interface BoardProperty {
  kind: string;
  thickness: number;
  mass_kg_m2: number | null;
  Fy: number | null;
  Fu: number | null;
  E_GPa: number | null;
  is_complete: boolean;
  missing_fields: string[];
  yield_ratio: number;
  yield_ratio_source: string;
}

export interface StudSection {
  group: string;
  name: string;
  H: number;
  B: number;
  t: number | null;
  A: number;
  cx: number;
  cy: number;
  Ix: number;
  Iy: number;
  Sx: number;
  Sy: number;
  rx: number;
  ry: number;
  section_class: string;
  Se: number | null;
  Se_basis_Fy_MPa: number | null;
  steel_grade: string | null;
  Fy: number | null;
  Fu: number | null;
  steel_status: string | null;
}

export interface StudMethod {
  stud_type: string;
  method: string | null;
}

export interface BoltMaterial {
  material: string;
  Fu: number;
}

// 런너 고정 앵커 제품 허용하중 표 행. concrete_fc_MPa가 null이면 콘크리트 강도 무관 행(제조사 권장하중)
export interface AnchorLoadRow {
  embedment_mm: number;
  concrete_fc_MPa: number | null;
  allowable_shear_N: number;
  allowable_tension_N: number;
  label: string | null;
}

// 런너 고정 앵커 제품(data/seed/anchor_product.json). family dx|gx|screw|custom, basis rec|asd|user
export interface AnchorProduct {
  anchor_id: string;
  maker: string;
  product: string;
  family: string;
  family_label: string;
  shank_diameter_mm: number | null;
  basis: string;
  basis_label: string;
  concrete_condition: string;
  min_concrete_thickness_mm: number | null;
  min_edge_mm: number | null;
  min_spacing_mm: number | null;
  min_fasteners_per_unit: number | null;
  approvals: string;
  source: string;
  is_default: boolean;
  default_embedment_mm: number | null;
  table: AnchorLoadRow[];
}

export interface AnchorProductCatalog {
  // 내진 시 런너 고정 앵커 허용 전단 상한(N/개). ICC-ES ESR 공통 90 lbf(400 N) — 국내 적용 확인 필요
  seismic_shear_cap_N: number;
  seismic_shear_cap_note: string;
  // 상한 적용 대상 제품군(dx·gx — ICC-ES PAF 평가서 §4.1 Item 2 전용). screw는 비적용(결정 2, 2026-11-09)
  seismic_shear_cap_families: string[];
  items: AnchorProduct[];
}

export interface MaterialCatalog {
  boards: BoardProperty[];
  studs: StudSection[];
  studMethods: StudMethod[];
  bolts: BoltMaterial[];
  anchorProducts: AnchorProductCatalog;
}

export interface BoardLayerPayload {
  kind: string;
  thickness: number;
}

export type SiteClass = "S1" | "S2" | "S3" | "S4" | "S5";
export type DesignCase = "seismic" | "non_seismic";
export type StrengthCheckMode = "composite" | "stud_only";

export interface WallCheckPayload {
  rear_boards: BoardLayerPayload[];
  front_boards: BoardLayerPayload[];
  stud: {
    stud_type: string;
    spec: string;
    method: string;
  };
  design_case: DesignCase;
  strength_check_mode: StrengthCheckMode;
  horizontal_load_kg_m2: number;
  live_load_kN_m2?: number;
  vertical_load_kN_m: number;
  spacing_mm: number;
  span_mm: number;
  deflection_limit_denom: number;
  bolt: {
    diameter: number;
    yield_strength: number;
    pitch: number[];
    count: number[];
  };
  seismic: {
    S: number;
    Ip: number;
    site_class: SiteClass;
    s5_bedrock_depth_unknown: boolean;
    Fa?: number;
    // 설치높이비 z/h (2차 심사의견 D-2). 0.0~1.0, 기본 1.0
    z_over_h?: number;
  };
  omega: number;
  anchor_capacity_kN: number;
  anchor_spacing_mm: number;
  screw_pull_through_nominal_N?: number;
  // 런너 고정못 허용내력 출처(제조사·제품명). 계산에 미사용, 계산서 표기 전용(2차 심사의견 D-1)
  anchor_capacity_source?: string;
  // 런너 고정 앵커 제품 선택. "custom"이면 anchor_capacity_kN 직접 입력값을 쓰고,
  // 제품이면 서버가 허용하중 표를 조회해 anchor_capacity_kN을 덮어쓴다
  anchor_product_id?: string;
  anchor_embedment_mm?: number;
  anchor_concrete_fc_MPa?: number | null;
  anchor_apply_seismic_cap?: boolean;
}

export interface LayerResult {
  name: string;
  layer_type: string;
  y_centroid_mm: number;
  transformed_area_mm2: number;
  distance_to_neutral_axis_mm: number;
  inertia_about_neutral_axis_mm4: number;
  axial_strength_kN: number;
  cumulative_shear_kN: number;
  strength_shear_kN: number;
}

export interface WallCheckResult {
  strength_check_mode: StrengthCheckMode;
  design_case: DesignCase;
  neutral_axis_mm: number;
  I_full_mm4: number;
  eta: number;
  I_eff_mm4: number;
  Mn_kNm: number;
  Mu_kNm: number;
  stress_ratio: number;
  deflection_mm: number;
  deflection_limit_mm: number;
  seismic_moment_kNm: number;
  deflection_verdict: string;
  stress_verdict: string;
  screw_tension_verdict: string;
  notices: string[];
  max_height_mm: number;
  anchor_max_height_mm: number;
  max_height_increment_mm: number;
  anchor_spacing_increment_mm: number;
  layers: LayerResult[];
  intermediate: Record<string, number>;
  // 시험 시편 구성과 다른 항목 키(2차 심사의견 A-1). 일치하면 빈 배열
  tested_configuration_mismatch_fields?: string[];
  // 앵커 제품 조회 요약 "{maker} {product} / hET … / f'c … / {basis_label} / {source}". 사용자 정의면 null
  anchor_product_summary?: string | null;
  // 서버 조회값이 클라이언트 anchor_capacity_kN과 달라 덮어썼는지
  anchor_capacity_overridden?: boolean;
}

// 브라우저 개발 모드 기본 주소. Electron에서는 메인 프로세스가 할당한 동적 포트를 preload로 조회한다(2차 심사의견 E-3)
const fallbackApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
let apiBaseUrlPromise: Promise<string> | null = null;

export function getApiBaseUrl(): Promise<string> {
  if (apiBaseUrlPromise === null) {
    const lookup = typeof window !== "undefined" ? window.kccBoard?.getApiBaseUrl : undefined;
    apiBaseUrlPromise = lookup
      ? lookup().catch((error: unknown) => {
          // 실패한 조회는 캐시하지 않고 다음 요청에서 다시 조회한다
          apiBaseUrlPromise = null;
          throw new Error(`API 주소를 조회하지 못했습니다: ${error instanceof Error ? error.message : String(error)}`);
        })
      : Promise.resolve(fallbackApiBaseUrl);
  }
  return apiBaseUrlPromise;
}

export async function fetchCatalog(): Promise<MaterialCatalog> {
  const [boards, studs, studMethods, bolts, anchorProducts] = await Promise.all([
    request<BoardProperty[]>("/api/db/boards"),
    request<StudSection[]>("/api/db/studs"),
    request<StudMethod[]>("/api/db/stud-methods"),
    request<BoltMaterial[]>("/api/db/bolts"),
    request<AnchorProductCatalog>("/api/db/anchor-products"),
  ]);
  return { boards, studs, studMethods, bolts, anchorProducts };
}

export async function checkWall(payload: WallCheckPayload, signal?: AbortSignal): Promise<WallCheckResult> {
  return request<WallCheckResult>("/api/check", {
    method: "POST",
    signal,
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const apiBaseUrl = await getApiBaseUrl();
  const response = await fetch(`${apiBaseUrl}${path}`, init);
  const envelope = (await response.json()) as ApiEnvelope<T>;
  if (!envelope.success) {
    throw new Error(envelope.error.message);
  }
  return envelope.data;
}
