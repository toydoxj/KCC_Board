"""API 요청·응답 스키마와 계산엔진 변환."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.engine.constants import (
  ANCHOR_SPACING_INCREMENT_MM,
  ANCHOR_SPACING_MAX_MM,
  ANCHOR_SPACING_MIN_MM,
  DEFAULT_ANCHOR_CAPACITY_KN,
  DEFAULT_ANCHOR_SPACING_MM,
  DEFAULT_DEFLECTION_LIMIT_DENOM,
  DEFAULT_HORIZONTAL_LOAD_KG_M2,
  DEFAULT_OMEGA,
  GRAVITY,
)
from backend.engine.models import (
  BoardLayer,
  BoltInput,
  LayerResult,
  SeismicInput,
  StudInput,
  WallCheckRequest,
  WallCheckResult,
)
from backend.engine.repository import BoardCatalogItem, BoltMaterial, StudMethod, StudSection
from backend.engine.seismic import SITE_CLASSES


class ApiModel(BaseModel):
  model_config = ConfigDict(extra="forbid")


class ErrorPayload(ApiModel):
  code: str
  message: str


class ErrorResponse(ApiModel):
  success: Literal[False] = False
  data: None = None
  error: ErrorPayload


class HealthData(ApiModel):
  status: Literal["ok"]


class HealthResponse(ApiModel):
  success: Literal[True] = True
  data: HealthData
  error: None = None


class BoardLayerPayload(ApiModel):
  kind: str = Field(min_length=1)
  thickness: float = Field(gt=0)
  order: int | None = Field(default=None, ge=1)

  def to_engine(self) -> BoardLayer:
    return BoardLayer(kind=self.kind, thickness=self.thickness, order=self.order)


class StudPayload(ApiModel):
  stud_type: str = Field(min_length=1)
  spec: str = Field(min_length=1)
  method: str | None = None

  def to_engine(self) -> StudInput:
    return StudInput(stud_type=self.stud_type, spec=self.spec, method=self.method)


class BoltPayload(ApiModel):
  diameter: float = Field(gt=0)
  yield_strength: float = Field(gt=0)
  pitch: list[float] = Field(min_length=1)
  count: float | list[float] = 2.0

  @model_validator(mode="before")
  @classmethod
  def normalize_legacy_strength(cls, data: object) -> object:
    if isinstance(data, dict) and "yield_strength" not in data and "fracture_strength" in data:
      normalized = dict(data)
      normalized["yield_strength"] = normalized.pop("fracture_strength")
      return normalized
    return data

  @field_validator("pitch")
  @classmethod
  def validate_pitch(cls, pitch: list[float]) -> list[float]:
    if any(value <= 0 for value in pitch):
      raise ValueError("볼트 간격은 모두 0보다 커야 합니다.")
    return pitch

  @field_validator("count")
  @classmethod
  def validate_count(cls, count: float | list[float]) -> float | list[float]:
    if isinstance(count, list):
      if not count:
        raise ValueError("볼트 개수는 최소 1개 이상 입력해야 합니다.")
      if any(value <= 0 for value in count):
        raise ValueError("볼트 개수는 모두 0보다 커야 합니다.")
      return count
    if count <= 0:
      raise ValueError("볼트 개수는 0보다 커야 합니다.")
    return count

  def to_engine(self) -> BoltInput:
    count = (self.count,) if isinstance(self.count, float) else tuple(self.count)
    return BoltInput(
      diameter=self.diameter,
      yield_strength=self.yield_strength,
      pitch=tuple(self.pitch),
      count=count,
    )


class SeismicPayload(ApiModel):
  S: float = Field(gt=0)
  Ip: float = Field(gt=0)
  site_class: Literal["S1", "S2", "S3", "S4", "S5"] = "S5"
  s5_bedrock_depth_unknown: bool = False
  Fa: float | None = Field(default=None, gt=0)

  def to_engine(self) -> SeismicInput:
    if self.site_class not in SITE_CLASSES:
      raise ValueError(f"자동 Fa 산정 대상이 아닌 지반등급입니다: {self.site_class}")
    return SeismicInput(
      S=self.S,
      Ip=self.Ip,
      site_class=self.site_class,
      s5_bedrock_depth_unknown=self.s5_bedrock_depth_unknown,
      Fa=self.Fa,
    )


class WallCheckRequestPayload(ApiModel):
  rear_boards: list[BoardLayerPayload] = Field(default_factory=list)
  front_boards: list[BoardLayerPayload] = Field(default_factory=list)
  stud: StudPayload
  design_case: Literal["seismic", "non_seismic"] = "seismic"
  strength_check_mode: Literal["composite", "stud_only"] = "composite"
  horizontal_load_kg_m2: float = Field(default=DEFAULT_HORIZONTAL_LOAD_KG_M2, gt=0)
  live_load_kN_m2: float | None = Field(default=None, ge=0)
  vertical_load_kN_m: float = Field(default=0.0, ge=0)
  spacing_mm: float = Field(gt=0)
  span_mm: float = Field(gt=0)
  deflection_limit_denom: int = Field(default=DEFAULT_DEFLECTION_LIMIT_DENOM, ge=1)
  bolt: BoltPayload
  seismic: SeismicPayload
  omega: float = Field(default=DEFAULT_OMEGA, gt=0)
  anchor_capacity_kN: float = Field(default=DEFAULT_ANCHOR_CAPACITY_KN, gt=0)
  anchor_spacing_mm: float = Field(
    default=DEFAULT_ANCHOR_SPACING_MM,
    ge=ANCHOR_SPACING_MIN_MM,
    le=ANCHOR_SPACING_MAX_MM,
  )

  @field_validator("anchor_spacing_mm")
  @classmethod
  def validate_anchor_spacing(cls, anchor_spacing_mm: float) -> float:
    quotient = anchor_spacing_mm / ANCHOR_SPACING_INCREMENT_MM
    if not quotient.is_integer():
      raise ValueError(f"앵커 간격은 {ANCHOR_SPACING_INCREMENT_MM:g}mm 단위로 입력해야 합니다.")
    return anchor_spacing_mm

  def to_engine(self) -> WallCheckRequest:
    live_load = self.live_load_kN_m2
    if live_load is None:
      live_load = self.horizontal_load_kg_m2 * GRAVITY / 1000.0
    return WallCheckRequest(
      rear_boards=tuple(board.to_engine() for board in self.rear_boards),
      front_boards=tuple(board.to_engine() for board in self.front_boards),
      stud=self.stud.to_engine(),
      design_case=self.design_case,
      strength_check_mode=self.strength_check_mode,
      horizontal_load_kg_m2=self.horizontal_load_kg_m2,
      live_load_kN_m2=live_load,
      vertical_load_kN_m=self.vertical_load_kN_m,
      spacing_mm=self.spacing_mm,
      span_mm=self.span_mm,
      deflection_limit_denom=self.deflection_limit_denom,
      bolt=self.bolt.to_engine(),
      seismic=self.seismic.to_engine(),
      omega=self.omega,
      anchor_capacity_kN=self.anchor_capacity_kN,
      anchor_spacing_mm=self.anchor_spacing_mm,
    )


class LayerResultData(ApiModel):
  name: str
  layer_type: str
  y_centroid_mm: float
  transformed_area_mm2: float
  distance_to_neutral_axis_mm: float
  inertia_about_neutral_axis_mm4: float
  axial_strength_kN: float
  cumulative_shear_kN: float

  @classmethod
  def from_engine(cls, result: LayerResult) -> "LayerResultData":
    return cls(
      name=result.name,
      layer_type=result.layer_type,
      y_centroid_mm=result.y_centroid_mm,
      transformed_area_mm2=result.transformed_area_mm2,
      distance_to_neutral_axis_mm=result.distance_to_neutral_axis_mm,
      inertia_about_neutral_axis_mm4=result.inertia_about_neutral_axis_mm4,
      axial_strength_kN=result.axial_strength_kN,
      cumulative_shear_kN=result.cumulative_shear_kN,
    )


class WallCheckResultData(ApiModel):
  strength_check_mode: Literal["composite", "stud_only"]
  design_case: Literal["seismic", "non_seismic"]
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
  max_height_mm: float
  anchor_max_height_mm: float
  max_height_increment_mm: float
  anchor_spacing_increment_mm: float
  layers: list[LayerResultData]
  intermediate: dict[str, float]

  @classmethod
  def from_engine(cls, result: WallCheckResult) -> "WallCheckResultData":
    return cls(
      strength_check_mode=result.strength_check_mode,  # type: ignore[arg-type]
      design_case=result.design_case,  # type: ignore[arg-type]
      neutral_axis_mm=result.neutral_axis_mm,
      I_full_mm4=result.I_full_mm4,
      eta=result.eta,
      I_eff_mm4=result.I_eff_mm4,
      Mn_kNm=result.Mn_kNm,
      Mu_kNm=result.Mu_kNm,
      stress_ratio=result.stress_ratio,
      deflection_mm=result.deflection_mm,
      deflection_limit_mm=result.deflection_limit_mm,
      seismic_moment_kNm=result.seismic_moment_kNm,
      deflection_verdict=result.deflection_verdict,
      stress_verdict=result.stress_verdict,
      max_height_mm=result.max_height_mm,
      anchor_max_height_mm=result.anchor_max_height_mm,
      max_height_increment_mm=result.max_height_increment_mm,
      anchor_spacing_increment_mm=result.anchor_spacing_increment_mm,
      layers=[LayerResultData.from_engine(layer) for layer in result.layers],
      intermediate=result.intermediate,
    )


class WallCheckResponse(ApiModel):
  success: Literal[True] = True
  data: WallCheckResultData
  error: None = None


class BoardPropertyData(ApiModel):
  kind: str
  thickness: float
  mass_kg_m2: float | None
  Fy: float | None
  Fu: float | None
  E_GPa: float | None
  is_complete: bool
  missing_fields: list[str]

  @classmethod
  def from_repository(cls, board: BoardCatalogItem) -> "BoardPropertyData":
    return cls(
      kind=board.kind,
      thickness=board.thickness,
      mass_kg_m2=board.mass_kg_m2,
      Fy=board.Fy,
      Fu=board.Fu,
      E_GPa=board.E_GPa,
      is_complete=board.is_complete,
      missing_fields=list(board.missing_fields),
    )


class StudSectionData(ApiModel):
  group: str
  name: str
  H: float
  B: float
  t: float | None
  A: float
  cx: float
  cy: float
  Ix: float
  Iy: float
  Sx: float
  Sy: float
  rx: float
  ry: float
  section_class: str

  @classmethod
  def from_repository(cls, stud: StudSection) -> "StudSectionData":
    return cls(
      group=stud.group,
      name=stud.name,
      H=stud.H,
      B=stud.B,
      t=stud.t,
      A=stud.A,
      cx=stud.cx,
      cy=stud.cy,
      Ix=stud.Ix,
      Iy=stud.Iy,
      Sx=stud.Sx,
      Sy=stud.Sy,
      rx=stud.rx,
      ry=stud.ry,
      section_class=stud.section_class,
    )


class StudMethodData(ApiModel):
  stud_type: str
  method: str | None

  @classmethod
  def from_repository(cls, stud_method: StudMethod) -> "StudMethodData":
    return cls(stud_type=stud_method.stud_type, method=stud_method.method)


class BoltMaterialData(ApiModel):
  material: str
  Fu: float

  @classmethod
  def from_repository(cls, bolt: BoltMaterial) -> "BoltMaterialData":
    return cls(material=bolt.material, Fu=bolt.Fu)


class BoardListResponse(ApiModel):
  success: Literal[True] = True
  data: list[BoardPropertyData]
  error: None = None


class StudListResponse(ApiModel):
  success: Literal[True] = True
  data: list[StudSectionData]
  error: None = None


class StudMethodListResponse(ApiModel):
  success: Literal[True] = True
  data: list[StudMethodData]
  error: None = None


class BoltListResponse(ApiModel):
  success: Literal[True] = True
  data: list[BoltMaterialData]
  error: None = None
