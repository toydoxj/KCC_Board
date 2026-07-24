"""계산엔진 입출력 모델."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BoardLayer:
  kind: str
  thickness: float
  order: int | None = None


@dataclass(frozen=True)
class StudInput:
  stud_type: str
  spec: str
  method: str | None = None


@dataclass(frozen=True)
class BoltInput:
  diameter: float
  # 피스 항복강도 Fy. 전단강도 Fv = 0.6 × Fy 로 유도해 전단식에 사용
  yield_strength: float
  pitch: tuple[float, ...]
  count: tuple[float, ...] = (2.0,)


@dataclass(frozen=True)
class SeismicInput:
  S: float
  Ip: float
  site_class: str = "S5"
  s5_bedrock_depth_unknown: bool = False
  Fa: float | None = None


@dataclass(frozen=True)
class WallCheckRequest:
  rear_boards: tuple[BoardLayer, ...]
  front_boards: tuple[BoardLayer, ...]
  stud: StudInput
  horizontal_load_kg_m2: float
  live_load_kN_m2: float
  vertical_load_kN_m: float
  spacing_mm: float
  span_mm: float
  deflection_limit_denom: int
  bolt: BoltInput
  seismic: SeismicInput
  design_case: str = "seismic"
  strength_check_mode: str = "composite"
  omega: float = 1.5
  anchor_capacity_kN: float = 0.4
  anchor_spacing_mm: float = 450.0


@dataclass(frozen=True)
class LayerResult:
  name: str
  layer_type: str
  y_centroid_mm: float
  transformed_area_mm2: float
  distance_to_neutral_axis_mm: float
  inertia_about_neutral_axis_mm4: float
  axial_strength_kN: float
  cumulative_shear_kN: float = 0.0


@dataclass(frozen=True)
class WallCheckResult:
  strength_check_mode: str
  design_case: str
  neutral_axis_mm: float
  I_full_mm4: float
  eta: float
  I_eff_mm4: float
  Mn_kNm: float
  Mu_kNm: float
  stress_ratio: float
  deflection_mm: float
  deflection_limit_mm: float
  seismic_moment_kNm: float
  deflection_verdict: str
  stress_verdict: str
  max_height_mm: float = 0.0
  anchor_max_height_mm: float = 0.0
  max_height_increment_mm: float = 50.0
  anchor_spacing_increment_mm: float = 50.0
  layers: tuple[LayerResult, ...] = field(default_factory=tuple)
  intermediate: dict[str, float] = field(default_factory=dict)
