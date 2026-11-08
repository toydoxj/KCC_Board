"""계산엔진 입출력 모델."""

from dataclasses import dataclass, field

from backend.engine.constants import (
  DEFAULT_SCREW_PULL_THROUGH_NOMINAL_N,
  DEFAULT_SEISMIC_Z_OVER_H,
  STANDARD_SCREW_COUNT,
)


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
  # [외측, 중간, 내측] 층별 피치당 개수
  count: tuple[float, ...] = STANDARD_SCREW_COUNT


@dataclass(frozen=True)
class SeismicInput:
  S: float
  Ip: float
  site_class: str = "S5"
  s5_bedrock_depth_unknown: bool = False
  Fa: float | None = None
  # 설치높이비 z/h (2차 심사의견 D-2). 0.0~1.0, 기본 1.0(최상층, 안전측)
  z_over_h: float = DEFAULT_SEISMIC_Z_OVER_H


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
  # 런너 고정못 허용내력 출처(제조사·제품명). 계산에 미사용, 계산서 표기 전용(2차 심사의견 D-1)
  anchor_capacity_source: str | None = None
  # 석고보드 풀스루 공칭강도(N/개) — 시험값 확보 전 입력값
  screw_pull_through_nominal_N: float = DEFAULT_SCREW_PULL_THROUGH_NOMINAL_N
  # 런너 고정 앵커 제품 선택(anchor_product.json). 엔진은 이 필드로 계산하지 않는다 —
  # API 계층이 제품·매입깊이·콘크리트 강도로 허용 전단을 조회해 anchor_capacity_kN에 채운 뒤 넘긴다.
  # None(또는 'custom')이면 사용자 정의 입력값을 그대로 쓴다. 계산서 표기용으로만 보존한다.
  anchor_product_id: str | None = None
  anchor_embedment_mm: float | None = None
  anchor_concrete_fc_MPa: float | None = None
  anchor_apply_seismic_cap: bool = True


@dataclass(frozen=True)
class AnchorLoadRow:
  """앵커 제품 허용하중 표의 한 행. concrete_fc_MPa가 None이면 콘크리트 강도 무관 행이다."""

  embedment_mm: float
  concrete_fc_MPa: float | None
  allowable_shear_N: float
  allowable_tension_N: float
  label: str | None = None


@dataclass(frozen=True)
class AnchorSeismicCap:
  """내진 시 런너 고정 앵커 허용 전단 상한(anchor_product.json 최상위 seismic_shear_cap_N·note).

  ICC-ES ESR 공통: SDC D·E·F에서 콘크리트 런너 고정 시 허용 전단 ≤ 90 lbf(400 N)/개. 국내 적용 타당성 확인 필요.
  """

  cap_N: float
  note: str


@dataclass(frozen=True)
class AnchorProduct:
  """런너 고정 앵커 제품(data/seed/anchor_product.json items[] 1건)."""

  anchor_id: str
  maker: str
  product: str
  # dx(화약식 타정못) | gx(가스식 핀) | screw(콘크리트 스크류) | custom(사용자 정의)
  family: str
  family_label: str
  shank_diameter_mm: float | None
  # rec(제조사 권장하중) | asd(ICC-ES 허용하중) | user(사용자 입력)
  basis: str
  basis_label: str
  concrete_condition: str
  min_concrete_thickness_mm: float | None
  min_edge_mm: float | None
  min_spacing_mm: float | None
  min_fasteners_per_unit: float | None
  approvals: str
  source: str
  is_default: bool
  default_embedment_mm: float | None
  table: tuple[AnchorLoadRow, ...] = field(default_factory=tuple)


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
  # Mn(강도)용 전단 누계 — 석고보드 피스 설계강도 상한 적용
  strength_shear_kN: float = 0.0


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
  screw_tension_verdict: str = "O.K"
  max_height_mm: float = 0.0
  anchor_max_height_mm: float = 0.0
  max_height_increment_mm: float = 50.0
  anchor_spacing_increment_mm: float = 50.0
  layers: tuple[LayerResult, ...] = field(default_factory=tuple)
  intermediate: dict[str, float] = field(default_factory=dict)
  # 판정에 영향하지 않는 입력 경고(표준 외 피스 간격 등)
  notices: tuple[str, ...] = field(default_factory=tuple)
  # 시험 시편 구성 대조(2차 심사의견 A-1·F-2): 가장 가까운 시편과 다른 항목 키. 일치하면 빈 값
  tested_configuration_mismatch_fields: tuple[str, ...] = field(default_factory=tuple)
