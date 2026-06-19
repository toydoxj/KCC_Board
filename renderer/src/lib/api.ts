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
}

export interface StudMethod {
  stud_type: string;
  method: string | null;
}

export interface BoltMaterial {
  material: string;
  Fu: number;
}

export interface MaterialCatalog {
  boards: BoardProperty[];
  studs: StudSection[];
  studMethods: StudMethod[];
  bolts: BoltMaterial[];
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
  };
  omega: number;
  anchor_capacity_kN: number;
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
  max_height_mm: number;
  max_height_increment_mm: number;
  layers: LayerResult[];
  intermediate: Record<string, number>;
}

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function fetchCatalog(): Promise<MaterialCatalog> {
  const [boards, studs, studMethods, bolts] = await Promise.all([
    request<BoardProperty[]>("/api/db/boards"),
    request<StudSection[]>("/api/db/studs"),
    request<StudMethod[]>("/api/db/stud-methods"),
    request<BoltMaterial[]>("/api/db/bolts"),
  ]);
  return { boards, studs, studMethods, bolts };
}

export async function checkWall(payload: WallCheckPayload): Promise<WallCheckResult> {
  return request<WallCheckResult>("/api/check", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, init);
  const envelope = (await response.json()) as ApiEnvelope<T>;
  if (!envelope.success) {
    throw new Error(envelope.error.message);
  }
  return envelope.data;
}
