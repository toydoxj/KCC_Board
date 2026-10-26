"""석고보드·스터드 부분합성 단면 계산엔진."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from backend.engine.constants import (
  ANCHOR_SPACING_INCREMENT_MM,
  ANCHOR_SPACING_MAX_MM,
  ANCHOR_SPACING_MIN_MM,
  ASD_COMBINED_LIVE_FACTOR,
  ASD_COMBINED_SEISMIC_FACTOR,
  ASD_SEISMIC_FACTOR,
  ANCHOR_SEISMIC_OVERSTRENGTH_FACTOR,
  BOARD_ORDER_LABELS,
  BILATERAL_SINGLE_PLY_SCREW_PITCH_MM,
  BOLT_SHEAR_TO_YIELD_RATIO,
  DEFAULT_ANCHOR_CAPACITY_KN,
  DEFAULT_ANCHOR_SPACING_MM,
  DEFAULT_DEFLECTION_LIMIT_DENOM,
  DEFAULT_HORIZONTAL_LOAD_KG_M2,
  DEFAULT_OMEGA,
  FIXED_REAR_BOARD_SCREW_COUNT,
  FIXED_REAR_BOARD_SCREW_PITCH_MM,
  GRAVITY,
  GYPSUM_SCREW_STRENGTH_DIVISOR,
  GYPSUM_SCREW_ULTIMATE_SHEAR_N,
  SCREW_PULLOUT_COEFFICIENT,
  SCREW_SHEAR_OMEGA,
  SCREW_STUD_BEARING_COEFFICIENT,
  SCREW_TENSION_OMEGA,
  SCREW_TILTING_COEFFICIENT,
  SEISMIC_FP_COEFFICIENT,
  STANDARD_SCREW_PITCH_MM,
  STEEL_DENSITY_KG_M3,
  EFFECTIVE_INERTIA_CORRECTION_BY_TYPE,
  STIFFNESS_CURVE_EXPONENT_BY_TYPE,
  STIFFNESS_CURVE_EXPONENT_C_BUTT_JOINT,
  STIFFNESS_REF_SCREW_PITCH_MM,
  STIFFNESS_REF_MOMENT_KNM_BY_TYPE,
  STIFFNESS_REF_SUPPORT_SHEAR_N_BY_TYPE,
  STIFFNESS_TYPE_C,
  STIFFNESS_TYPE_C_CENTRAL_JOINT,
  STIFFNESS_TYPE_C_FRONT_ONLY,
  STIFFNESS_TYPE_CH,
  STIFFNESS_TYPE_HR,
  STIFFNESS_TYPE_I,
  STIFFNESS_TYPE_MP,
  STIFFNESS_TYPE_R,
  STIFFNESS_TYPE_RV,
  STIFFNESS_TYPE_T_SILENT,
  STUD_ELASTIC_MODULUS,
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
from backend.engine.repository import BoardProperty, JsonSeedRepository, MaterialRepository, StudSection, StudSteel
from backend.engine.seismic import calculate_fa

MAX_HEIGHT_INCREMENT_MM = 50
MAX_HEIGHT_SEARCH_LIMIT_MM = 30000
CENTRAL_JOINT_STUD_GAP_MM = 25.0
CH_STUD_REAR_BOARD_THICKNESS_MM = 25.0
CH_STUD_IMPROVED_REAR_BOARD_THICKNESS_MM = 12.5
R_STUD_BOARD_STUD_CLEAR_GAP_MM = 12.0
# 한쪽 면만 검토하는 C-STUD 공법명(stud_method.json, 공백 제거 비교)
C_STUD_ONE_SIDE_FINISH_METHOD = "일면마감"
C_STUD_DOUBLE_STUD_METHOD = "이중스터드"
DESIGN_CASE_SEISMIC = "seismic"
DESIGN_CASE_NON_SEISMIC = "non_seismic"
DESIGN_CASES = {DESIGN_CASE_SEISMIC, DESIGN_CASE_NON_SEISMIC}
STRENGTH_CHECK_COMPOSITE = "composite"
STRENGTH_CHECK_STUD_ONLY = "stud_only"
STRENGTH_CHECK_MODES = {STRENGTH_CHECK_COMPOSITE, STRENGTH_CHECK_STUD_ONLY}


@dataclass(frozen=True)
class _Layer:
  name: str
  layer_type: str
  order: int
  thickness_mm: float
  y_centroid_mm: float
  transformed_area_mm2: float
  self_inertia_mm4: float
  axial_strength_kN: float
  mass_kN: float
  board_property: BoardProperty | None = None
  # 피스 간격·개수 고정값(CH·I-STUD 고정 후면 보드). None이면 bolt 입력(층 순서별)을 따른다.
  connection_pitch_mm: float | None = None
  connection_count: float | None = None
  # 비대칭 단독 1P의 마감행 간격 기준. 개수는 connection_count로 별도 지정 가능.
  connection_order: int | None = None


@dataclass(frozen=True)
class _Section:
  layers: tuple[_Layer, ...]
  stud_layer: _Layer
  stud_section: StudSection
  stud_multiplier: float
  stud_unfactored_self_inertia_mm4: float
  stud_connection_inertia_factor: float
  stud_assembly: "_StudAssembly"


@dataclass(frozen=True)
class _StudAssembly:
  area_mm2: float
  height_mm: float
  centroid_mm: float
  self_inertia_mm4: float
  unfactored_self_inertia_mm4: float
  connection_inertia_factor: float
  multiplier: float
  # 유효단면계수비 Se/Sx (AISI S100-16 부록 1, f = Fy) — 스터드 휨강도 항에 적용
  effective_section_ratio: float


@dataclass(frozen=True)
class _ReactionResult:
  live_kN_per_m: float
  seismic_kN_per_m: float
  load_combination_L_kN_per_m: float
  load_combination_0_7E_kN_per_m: float
  load_combination_0_75L_0_525E_kN_per_m: float
  required_kN_per_m: float
  anchor_capacity_kN: float
  anchor_spacing_mm: float
  anchor_allowable_spacing_mm: float
  anchor_capacity_kN_per_m: float
  anchor_utilization: float


def calculate_wall_check(
  request: WallCheckRequest,
  repository: MaterialRepository | None = None,
) -> WallCheckResult:
  repo = repository or JsonSeedRepository()
  result = _calculate_wall_check_once(request, repo)
  max_height = _maximum_allowable_height_mm(request, repo)
  anchor_max_height = _maximum_anchor_allowable_height_mm(request, repo)
  return replace(
    result,
    max_height_mm=max_height,
    anchor_max_height_mm=anchor_max_height,
    max_height_increment_mm=float(MAX_HEIGHT_INCREMENT_MM),
    anchor_spacing_increment_mm=float(ANCHOR_SPACING_INCREMENT_MM),
  )


def _calculate_wall_check_once(
  request: WallCheckRequest,
  repository: MaterialRepository,
) -> WallCheckResult:
  _validate_design_case(request.design_case)
  _validate_strength_check_mode(request.strength_check_mode)
  _validate_anchor_spacing(request.anchor_spacing_mm)
  _validate_pull_through(request.screw_pull_through_nominal_N)
  repo = repository
  section = _build_section(request, repo)
  neutral_axis = _neutral_axis(section.layers)
  neutral_axis_notices = _neutral_axis_notices(section, neutral_axis)
  layer_results = _layer_results(section.layers, neutral_axis)
  I_full = sum(layer.inertia_about_neutral_axis_mm4 for layer in layer_results)
  stud_result = next(layer for layer in layer_results if layer.layer_type == "stud")

  shear_by_name = _shear_connection_by_layer(section, request)
  eta = _composite_ratio(section.layers, shear_by_name)
  group, method = _parse_stud_type(request.stud)
  I_eff_raw = stud_result.inertia_about_neutral_axis_mm4 + math.sqrt(eta) * (
    I_full - stud_result.inertia_about_neutral_axis_mm4
  )
  I_eff_correction_factor = _effective_inertia_correction_factor(
    group,
    method,
    has_rear_board=bool(request.rear_boards),
  )
  # 하한: 부분합성 강성은 스터드 단독 강성(자체 도심 기준) 이상
  I_eff_lower_bound = section.stud_assembly.self_inertia_mm4
  stiffness_load = _stiffness_load_factor(request, section, group, method)
  stiffness_load_factor = stiffness_load.load_factor
  I_eff = max(I_eff_raw * I_eff_correction_factor * stiffness_load_factor, I_eff_lower_bound)
  stud_assembly = section.stud_assembly
  S_stud_composite, c_stud_composite = _stud_section_modulus(stud_result, stud_assembly, composite=True)
  S_stud_only, c_stud_only = _stud_section_modulus(stud_result, stud_assembly, composite=False)
  strength_shear_by_name = _shear_connection_by_layer(section, request, for_strength=True)
  stud_steel = _stud_steel(section.stud_section)
  Mn_composite = _nominal_moment(layer_results, strength_shear_by_name, S_stud_composite, stud_steel.Fy)
  Mn_stud_only = _nominal_moment(
    layer_results,
    shear_by_name,
    S_stud_only,
    stud_steel.Fy,
    include_board_layers=False,
  )
  Mn = _strength_check_nominal_moment(request.strength_check_mode, Mn_composite, Mn_stud_only)
  deflection = _deflection_mm(request, I_eff)
  deflection_limit = request.span_mm / request.deflection_limit_denom
  seismic_moment, seismic_weight, sds, fp = _seismic_moment_kNm(request, section.layers)
  live_moment = _live_moment_kNm(request)
  reaction = _reaction_result_kN_per_m(request, fp)
  Mu = _required_moment_kNm(request, live_moment, seismic_moment)
  stress_ratio = request.omega * Mu / Mn
  screw_tension = _screw_tension_result(request, section, sds)

  enriched_layers = tuple(
    LayerResult(
      name=layer.name,
      layer_type=layer.layer_type,
      y_centroid_mm=layer.y_centroid_mm,
      transformed_area_mm2=layer.transformed_area_mm2,
      distance_to_neutral_axis_mm=layer.distance_to_neutral_axis_mm,
      inertia_about_neutral_axis_mm4=layer.inertia_about_neutral_axis_mm4,
      axial_strength_kN=layer.axial_strength_kN,
      cumulative_shear_kN=shear_by_name.get(layer.name, 0.0),
      strength_shear_kN=strength_shear_by_name.get(layer.name, 0.0),
    )
    for layer in layer_results
  )

  return WallCheckResult(
    strength_check_mode=request.strength_check_mode,
    design_case=request.design_case,
    neutral_axis_mm=neutral_axis,
    I_full_mm4=I_full,
    eta=eta,
    I_eff_mm4=I_eff,
    Mn_kNm=Mn,
    Mu_kNm=Mu,
    stress_ratio=stress_ratio,
    deflection_mm=deflection,
    deflection_limit_mm=deflection_limit,
    seismic_moment_kNm=seismic_moment,
    deflection_verdict="O.K" if deflection <= deflection_limit else "N.G",
    stress_verdict="O.K" if stress_ratio <= 1.0 else "N.G",
    screw_tension_verdict="O.K" if screw_tension["screw_tension_utilization"] <= 1.0 else "N.G",
    layers=enriched_layers,
    notices=neutral_axis_notices + _screw_pitch_notices(section, request.bolt),
    intermediate={
      "stud_I_mm4": stud_result.inertia_about_neutral_axis_mm4,
      "stud_I_unfactored_mm4": section.stud_unfactored_self_inertia_mm4,
      "stud_section_height_mm": section.stud_layer.thickness_mm,
      "stud_self_inertia_mm4": stud_assembly.self_inertia_mm4,
      "stud_yield_strength_MPa": stud_steel.Fy,
      "stud_tensile_strength_MPa": stud_steel.Fu,
      "stud_effective_section_ratio": stud_assembly.effective_section_ratio,
      "stud_extreme_fiber_composite_mm": c_stud_composite,
      "stud_extreme_fiber_stud_only_mm": c_stud_only,
      "stud_Se_composite_mm3": S_stud_composite,
      "stud_Se_stud_only_mm3": S_stud_only,
      "stud_connection_inertia_factor": section.stud_connection_inertia_factor,
      "Mn_composite_kNm": Mn_composite,
      "Mn_stud_only_kNm": Mn_stud_only,
      "I_eff_raw_mm4": I_eff_raw,
      "I_eff_correction_factor": I_eff_correction_factor,
      "I_eff_lower_bound_mm4": I_eff_lower_bound,
      "screw_utilization_ratio": stiffness_load.utilization_ratio,
      "service_moment_kNm": stiffness_load.service_moment_kNm,
      "reference_moment_kNm": stiffness_load.reference_moment_kNm,
      "moment_utilization_ratio": stiffness_load.moment_utilization_ratio,
      "shear_utilization_ratio": stiffness_load.shear_utilization_ratio,
      # 1.0 = 모멘트 기준 지배, 0.0 = 피스력 기준 지배 (intermediate는 숫자만 허용)
      "stiffness_load_basis_moment": 1.0 if stiffness_load.moment_governs else 0.0,
      "screw_stud_side_shear_N": _screw_stud_side_shear_N(_stud_thickness_mm(section), request.bolt.diameter, stud_steel.Fu),
      "stiffness_curve_exponent_m": stiffness_load.curve_exponent,
      "stiffness_load_factor": stiffness_load_factor,
      "I_eff_lower_bound_governs": 1.0
      if I_eff_raw * I_eff_correction_factor * stiffness_load_factor < I_eff_lower_bound
      else 0.0,
      "live_moment_kNm": live_moment,
      "moment_L_kNm": live_moment,
      "moment_0_7E_kNm": ASD_SEISMIC_FACTOR * seismic_moment,
      "moment_0_75L_0_525E_kNm": _combined_live_seismic(live_moment, seismic_moment),
      "vertical_load_kN_m": request.vertical_load_kN_m,
      "seismic_weight_kN": seismic_weight,
      "Fa": _seismic_fa(request),
      "Sds": sds,
      "Fp_kN": fp,
      "reaction_live_kN_per_m": reaction.live_kN_per_m,
      "reaction_seismic_kN_per_m": reaction.seismic_kN_per_m,
      **({
        "fixed_rear_board_screw_pitch_mm": FIXED_REAR_BOARD_SCREW_PITCH_MM,
        "fixed_rear_board_screw_count": FIXED_REAR_BOARD_SCREW_COUNT,
      } if _fixed_rear_board_for_group(group) is not None else {}),
      **_reaction_intermediate(request, reaction),
      **screw_tension,
    },
  )


def request_from_golden_case(case: dict[str, object]) -> WallCheckRequest:
  inputs = case["inputs"]
  if not isinstance(inputs, dict):
    raise ValueError("골든 케이스 inputs 형식이 올바르지 않습니다.")

  boards_raw = inputs["boards"]
  if not isinstance(boards_raw, list):
    raise ValueError("골든 케이스 boards 형식이 올바르지 않습니다.")

  rear: list[BoardLayer] = []
  front: list[BoardLayer] = []
  for board in boards_raw:
    if not isinstance(board, dict):
      raise ValueError("골든 케이스 board 형식이 올바르지 않습니다.")
    if board["kind"] == "----" or float(board["thickness"]) <= 0:
      continue
    layer = BoardLayer(
      kind=str(board["kind"]),
      thickness=float(board["thickness"]),
      order=int(board["order"]),
    )
    col = str(board["col"])
    if col in {"G", "H", "I"}:
      rear.append(layer)
    elif col in {"K", "L", "M"}:
      front.append(layer)

  seismic_raw = inputs["seismic"]
  if not isinstance(seismic_raw, dict):
    raise ValueError("골든 케이스 seismic 형식이 올바르지 않습니다.")

  pitch_raw = inputs["bolt_pitch"]
  if not isinstance(pitch_raw, list):
    raise ValueError("골든 케이스 bolt_pitch 형식이 올바르지 않습니다.")
  yield_strength_raw = inputs.get("bolt_yield_strength")
  if yield_strength_raw is None:
    raise ValueError("골든 케이스 bolt_yield_strength 형식이 올바르지 않습니다.")

  return WallCheckRequest(
    rear_boards=tuple(rear),
    front_boards=tuple(front),
    stud=StudInput(stud_type=str(inputs["stud_type"]), spec=str(inputs["stud_spec"])),
    horizontal_load_kg_m2=float(inputs.get("horizontal_load_kg_m2", DEFAULT_HORIZONTAL_LOAD_KG_M2)),
    live_load_kN_m2=float(
      inputs.get(
        "live_load_kN_m2",
        float(inputs.get("horizontal_load_kg_m2", DEFAULT_HORIZONTAL_LOAD_KG_M2)) * GRAVITY / 1000.0,
      )
    ),
    vertical_load_kN_m=float(inputs.get("vertical_load_kN_m", 0.0)),
    spacing_mm=float(inputs["spacing_mm"]),
    span_mm=float(inputs["span_mm"]),
    deflection_limit_denom=int(inputs.get("deflection_limit_denom", DEFAULT_DEFLECTION_LIMIT_DENOM)),
    bolt=BoltInput(
      diameter=float(inputs["bolt_diameter"]),
      yield_strength=float(yield_strength_raw),
      pitch=bolt_values_from_ply_order(tuple(float(value) for value in pitch_raw)),
    ),
    seismic=SeismicInput(
      S=float(seismic_raw["S"]),
      Ip=float(seismic_raw["Ip"]),
      Fa=float(seismic_raw["Fa"]),
    ),
    design_case=str(inputs.get("design_case", DESIGN_CASE_SEISMIC)),
    strength_check_mode=str(inputs.get("strength_check_mode", STRENGTH_CHECK_COMPOSITE)),
    omega=DEFAULT_OMEGA,
    anchor_capacity_kN=float(inputs.get("anchor_capacity_kN", DEFAULT_ANCHOR_CAPACITY_KN)),
    anchor_spacing_mm=float(inputs.get("anchor_spacing_mm", DEFAULT_ANCHOR_SPACING_MM)),
  )


def _build_section(request: WallCheckRequest, repo: MaterialRepository) -> _Section:
  group, method = _parse_stud_type(request.stud)
  if _is_i_stud_group(group) and "".join(method.split()) == "일면마감":
    raise ValueError("I-STUD 일면마감은 지원하지 않습니다. 후면 보드 1장을 포함한 기본 형식을 사용하십시오.")
  stud = repo.get_stud(group, request.stud.spec)
  _stud_steel(stud)
  stud_assembly = _stud_assembly(stud, method)
  fixed_rear_board = _fixed_rear_board_for_group(group)
  if fixed_rear_board is not None:
    _validate_fixed_rear_boards(group, request.rear_boards, fixed_rear_board)
  _validate_one_side_review_rear_boards(group, method, request.rear_boards)
  layers: list[_Layer] = []
  y_cursor = 0.0
  rear_boards = _assign_rear_orders(request.rear_boards)
  front_boards = _assign_front_orders(request.front_boards)
  r_stud_board_gap = R_STUD_BOARD_STUD_CLEAR_GAP_MM if _is_r_stud_group(group) else 0.0

  for board in rear_boards:
    layer, next_y_cursor = _board_layer(
      board,
      y_cursor,
      request,
      repo,
      fixed_rear_board=fixed_rear_board is not None,
    )
    layers.append(layer)
    if fixed_rear_board is None:
      y_cursor = next_y_cursor

  if rear_boards and r_stud_board_gap > 0.0:
    y_cursor += r_stud_board_gap

  stud_layer = _stud_layer(stud, y_cursor, request, stud_assembly)
  layers.append(stud_layer)
  y_cursor += stud_layer.thickness_mm

  if front_boards and r_stud_board_gap > 0.0:
    y_cursor += r_stud_board_gap

  for board in front_boards:
    layer, y_cursor = _board_layer(board, y_cursor, request, repo)
    layers.append(layer)

  active_count = max(len(rear_boards), len(front_boards))
  layers = [
    # 2026-10-26 승인: 2P/3P+1P의 단독 1P는 마감층 간격만 따르고,
    # 개수는 원래 1P 값을 유지한다(UI 기본 1개). 반대 방향에도 동일 적용.
    replace(
      layer,
      connection_order=active_count,
      connection_count=_count_for_order(request.bolt.count, layer.order)
      if active_count in (2, 3) else layer.connection_count,
    )
    if layer.layer_type == "board"
    and layer.connection_pitch_mm is None
    and ((index < len(rear_boards) and len(rear_boards) == 1)
         or (index > len(rear_boards) and len(front_boards) == 1))
    else layer
    for index, layer in enumerate(layers)
  ]

  return _Section(
    layers=tuple(layers),
    stud_layer=stud_layer,
    stud_section=stud,
    stud_multiplier=stud_assembly.multiplier,
    stud_unfactored_self_inertia_mm4=stud_assembly.unfactored_self_inertia_mm4,
    stud_connection_inertia_factor=stud_assembly.connection_inertia_factor,
    stud_assembly=stud_assembly,
  )


def _assign_rear_orders(boards: tuple[BoardLayer, ...]) -> tuple[BoardLayer, ...]:
  total = len(boards)
  return tuple(
    board if board.order is not None else BoardLayer(board.kind, board.thickness, total - index)
    for index, board in enumerate(boards)
  )


def _assign_front_orders(boards: tuple[BoardLayer, ...]) -> tuple[BoardLayer, ...]:
  return tuple(
    board if board.order is not None else BoardLayer(board.kind, board.thickness, index + 1)
    for index, board in enumerate(boards)
  )


def _board_layer(
  board: BoardLayer,
  y_bottom: float,
  request: WallCheckRequest,
  repo: MaterialRepository,
  fixed_rear_board: bool = False,
) -> tuple[_Layer, float]:
  prop = repo.get_board(board.kind, board.thickness)
  elastic_ratio = prop.E_GPa * 1000.0 / STUD_ELASTIC_MODULUS
  transformed_width = elastic_ratio * request.spacing_mm
  area = transformed_width * board.thickness
  self_i = transformed_width * board.thickness**3 / 12.0
  y_centroid = y_bottom + board.thickness / 2.0
  axial = prop.Fy * request.spacing_mm * board.thickness * 1e-3
  mass = prop.mass_kg_m2 * (request.spacing_mm / 1000.0) * (request.span_mm / 1000.0) * GRAVITY / 1000.0
  name = f"{board.kind}-{board.thickness:g}-{y_bottom:g}"
  return (
    _Layer(
      name=name,
      layer_type="board",
      order=board.order or 1,
      thickness_mm=board.thickness,
      y_centroid_mm=y_centroid,
      transformed_area_mm2=area,
      self_inertia_mm4=self_i,
      axial_strength_kN=axial,
      mass_kN=mass,
      board_property=prop,
      connection_pitch_mm=FIXED_REAR_BOARD_SCREW_PITCH_MM if fixed_rear_board else None,
      connection_count=FIXED_REAR_BOARD_SCREW_COUNT if fixed_rear_board else None,
    ),
    y_bottom + board.thickness,
  )


def _stud_layer(
  stud: StudSection,
  y_bottom: float,
  request: WallCheckRequest,
  assembly: _StudAssembly,
) -> _Layer:
  mass = assembly.area_mm2 * request.span_mm * 1e-9 * STEEL_DENSITY_KG_M3 * GRAVITY / 1000.0
  return _Layer(
    name=f"{stud.group}-{stud.name}",
    layer_type="stud",
    order=0,
    thickness_mm=assembly.height_mm,
    y_centroid_mm=y_bottom + assembly.centroid_mm,
    transformed_area_mm2=assembly.area_mm2,
    self_inertia_mm4=assembly.self_inertia_mm4,
    axial_strength_kN=assembly.area_mm2 * _stud_steel(stud).Fy * 1e-3,
    mass_kN=mass,
  )


def _stud_steel(stud: StudSection) -> StudSteel:
  """스터드 강재(Fy·Fu)를 반환한다(심사의견 B-8). Se가 다른 Fy 기준으로 산정되었으면 계산을 차단한다."""
  label = f"{stud.group} {stud.name}"
  if stud.steel is None:
    raise ValueError(f"스터드 {label}에 강재(Fy·Fu)가 연결되지 않았습니다. init_db를 다시 실행하십시오.")
  if stud.Se is not None:
    if stud.Se_basis_Fy_MPa is None:
      raise ValueError(f"스터드 {label}의 Se 산정 기준 Fy(Se_basis_Fy_MPa)가 없습니다. init_db를 다시 실행하십시오.")
    if not math.isclose(stud.Se_basis_Fy_MPa, stud.steel.Fy):
      raise ValueError(
        f"스터드 {label}의 Se는 Fy {stud.Se_basis_Fy_MPa:g} MPa 기준 값이나 연결 강재 {stud.steel.steel_grade}의 Fy는 "
        f"{stud.steel.Fy:g} MPa입니다. Se를 재산정하십시오."
      )
  return stud.steel


def _stud_effective_section_ratio(stud: StudSection) -> float:
  if stud.Se is None:
    raise ValueError(
      f"스터드 유효단면계수 Se가 등록되지 않았습니다: {stud.group} {stud.name} "
      "(자재 DB를 data/seed 기준으로 재초기화(init_db)해야 합니다.)",
    )
  if stud.Sx <= 0.0:
    raise ValueError(f"스터드 단면계수 Sx가 0 이하입니다: {stud.group} {stud.name}")
  return min(1.0, stud.Se / stud.Sx)


def _stud_assembly(stud: StudSection, method: str) -> _StudAssembly:
  effective_section_ratio = _stud_effective_section_ratio(stud)
  if _is_central_joint_method(method):
    # 두 스터드를 깊이 방향으로 간격 g만큼 띄워 배치: 조립 도심 ~ 각 스터드 도심 거리 = H + g/2 - cy
    distance = stud.H + CENTRAL_JOINT_STUD_GAP_MM / 2.0 - stud.cy
    self_inertia = 2.0 * (stud.A * distance**2 + stud.Ix)
    return _StudAssembly(
      area_mm2=2.0 * stud.A,
      height_mm=2.0 * stud.H + CENTRAL_JOINT_STUD_GAP_MM,
      centroid_mm=(2.0 * stud.H + CENTRAL_JOINT_STUD_GAP_MM) / 2.0,
      self_inertia_mm4=self_inertia,
      unfactored_self_inertia_mm4=self_inertia,
      connection_inertia_factor=1.0,
      multiplier=2.0,
      effective_section_ratio=effective_section_ratio,
    )

  multiplier = 2.0 if "맞댐" in method else 1.0
  return _StudAssembly(
    area_mm2=stud.A * multiplier,
    height_mm=stud.H,
    centroid_mm=stud.cy,
    self_inertia_mm4=stud.Ix * multiplier,
    unfactored_self_inertia_mm4=stud.Ix * multiplier,
    connection_inertia_factor=1.0,
    multiplier=multiplier,
    effective_section_ratio=effective_section_ratio,
  )


def _is_central_joint_method(method: str) -> bool:
  normalized = method.replace(" ", "")
  return "중앙부이음" in normalized or "중앙부연결" in normalized


def _is_one_side_review_method(method: str) -> bool:
  """일면마감·이중스터드: 한쪽 면만 검토하는 C-STUD 공법(후면 보드 없음).

  모든 공백 문자를 제거하고 부분 일치로 판정한다(복합 형식명 "C-STUD(이중스터드)" 포함).
  """
  normalized = "".join(method.split())
  return C_STUD_ONE_SIDE_FINISH_METHOD in normalized or C_STUD_DOUBLE_STUD_METHOD in normalized


def _is_c_stud_group(group: str) -> bool:
  return group.replace(".", "-").replace(" ", "").upper() == "C-STUD"


def _validate_one_side_review_rear_boards(group: str, method: str, rear_boards: tuple[BoardLayer, ...]) -> None:
  if _is_c_stud_group(group) and _is_one_side_review_method(method) and rear_boards:
    raise ValueError("이중스터드·일면마감은 한쪽 면만 검토하므로 후면 석고보드를 입력할 수 없습니다.")


def _stiffness_calibration_type(group: str, method: str, has_rear_board: bool = True) -> str | None:
  """시험 보정계수 R·E-8 기준 피스력의 형식 분류(시험 시편 11종 기준). 미등록 형식은 None.

  C-STUD: 중앙부 이음 → 중앙부이음, 후면 보드 없음 → 기본 일면(공법 무관, 2026-10-24), 그 외 → C.
  """
  normalized_group = group.replace(".", "-").replace(" ", "").upper()
  if normalized_group == "C-STUD":
    if _is_central_joint_method(method):
      return STIFFNESS_TYPE_C_CENTRAL_JOINT
    if not has_rear_board:
      return STIFFNESS_TYPE_C_FRONT_ONLY
    return STIFFNESS_TYPE_C
  if normalized_group.startswith("CH-STUD"):
    return STIFFNESS_TYPE_CH
  if normalized_group in {"T-SILENT", "T-SILENT-STUD"}:
    return STIFFNESS_TYPE_T_SILENT
  if normalized_group == "R-STUD":
    return STIFFNESS_TYPE_R
  if normalized_group == "I-STUD":
    return STIFFNESS_TYPE_I
  if normalized_group == "HR-STUD":
    return STIFFNESS_TYPE_HR
  if normalized_group == "RV-STUD":
    return STIFFNESS_TYPE_RV
  if normalized_group == "MP-STUD":
    return STIFFNESS_TYPE_MP
  return None


def _require_calibration_type(group: str, method: str, has_rear_board: bool = True) -> str:
  """시험 형식 분류를 반환한다. 시험 보정계수 R이 없는 형식은 적용 범위 밖이므로 ValueError."""
  calibration_type = _stiffness_calibration_type(group, method, has_rear_board)
  if calibration_type is None:
    raise ValueError(
      f"{group}({method})은(는) 시험 보정계수 R이 산정되지 않은 형식으로 적용 범위 밖입니다. "
      "시험 형식(C·CH·T.silent·R·I·HR·RV·MP-STUD)만 계산할 수 있습니다."
    )
  return calibration_type


def _effective_inertia_correction_factor(
  group: str,
  method: str,
  has_rear_board: bool = True,
) -> float:
  # 시험 보정계수 R(E-11, 2026-10-24): 허용처짐(H/240) 상태 사용하중 모멘트 M_L에서의
  # 실측 할선강성 / 엔진 Ieff,raw(L = 2,400). 값은 constants 표(backend/tools/r_calibration.py 산정).
  return EFFECTIVE_INERTIA_CORRECTION_BY_TYPE[_require_calibration_type(group, method, has_rear_board)]


def _stiffness_reference_shear_N(group: str, method: str, has_rear_board: bool = True) -> float:
  """E-8 형식별 기준 피스력 V*(N)."""
  return STIFFNESS_REF_SUPPORT_SHEAR_N_BY_TYPE[_require_calibration_type(group, method, has_rear_board)]


def _stiffness_curve_exponent(group: str, method: str, has_rear_board: bool = True) -> float:
  """실측 M–δ 곡선 δ = c·M^m 의 형식별 지수 m. C-STUD 맞댐이음은 분류명이 같아 공법으로 구분한다."""
  calibration_type = _require_calibration_type(group, method, has_rear_board)
  if calibration_type in {STIFFNESS_TYPE_C, STIFFNESS_TYPE_C_FRONT_ONLY} and "맞댐" in method:
    return STIFFNESS_CURVE_EXPONENT_C_BUTT_JOINT
  return STIFFNESS_CURVE_EXPONENT_BY_TYPE[calibration_type]


@dataclass(frozen=True)
class _StiffnessLoad:
  utilization_ratio: float
  curve_exponent: float
  load_factor: float
  service_moment_kNm: float
  reference_moment_kNm: float
  moment_utilization_ratio: float
  shear_utilization_ratio: float
  moment_governs: bool


def _stiffness_load_factor(
  request: WallCheckRequest,
  section: _Section,
  group: str,
  method: str,
) -> _StiffnessLoad:
  """하중 수준 기준 단방향 강성 보정계수 k_L = min[1, (u/u_ref)^(1−m)] (v0.7.4, 심사의견 E-3·E-8).

  u/u_ref = max(M_L / M*, V_d / V*) × (p / p_ref)_max
  - M_L: 처짐 검토 하중(활하중)에 의한 최대모멘트 = q·s·L²/8
  - M*: 형식별 기준 모멘트(실측 할선강성비가 적용 R과 같아지는 모멘트)
  - V_d: 스터드 1개당 지점 전단력 = q·s·L/2, V*: 형식별 R 보정점의 시험 피스 전단력
  - p/p_ref: 층별 피스 간격 / 시험 피스 간격(피스 1개당 전단력 ∝ 간격)
  두 기준 중 불리한(큰) 활용도를 쓴다. u ≤ u_ref이면 1.0(현행 R 유지), 초과 시에만 강성을 저감한다.
  """
  has_rear_board = bool(request.rear_boards)
  service_moment_kNm = request.live_load_kN_m2 * (request.spacing_mm / 1000.0) * (request.span_mm / 1000.0) ** 2 / 8.0
  reference_moment_kNm = STIFFNESS_REF_MOMENT_KNM_BY_TYPE[_require_calibration_type(group, method, has_rear_board)]
  support_shear_N = request.live_load_kN_m2 * 1e-3 * request.spacing_mm * request.span_mm / 2.0
  pitch_ratio = max(
    (
      _layer_pitch_count(layer, request.bolt)[0] / _pitch_for_order(STIFFNESS_REF_SCREW_PITCH_MM, layer.connection_order or layer.order)
      for layer in section.layers
      if layer.layer_type == "board"
    ),
    default=1.0,
  )
  reference_shear_N = _stiffness_reference_shear_N(group, method, has_rear_board=has_rear_board)
  moment_ratio = service_moment_kNm / reference_moment_kNm
  shear_ratio = support_shear_N / reference_shear_N
  moment_governs = moment_ratio > shear_ratio
  utilization_ratio = max(moment_ratio, shear_ratio) * pitch_ratio
  exponent = _stiffness_curve_exponent(group, method, has_rear_board=has_rear_board)
  load_factor = 1.0 if utilization_ratio <= 1.0 else utilization_ratio ** (1.0 - exponent)
  return _StiffnessLoad(
    utilization_ratio=utilization_ratio,
    curve_exponent=exponent,
    load_factor=load_factor,
    service_moment_kNm=service_moment_kNm,
    reference_moment_kNm=reference_moment_kNm,
    moment_utilization_ratio=moment_ratio,
    shear_utilization_ratio=shear_ratio,
    moment_governs=moment_governs,
  )


def _parse_stud_type(stud: StudInput) -> tuple[str, str]:
  if stud.stud_type.startswith("C-STUD("):
    group = stud.stud_type.split("(", maxsplit=1)[0]
  else:
    group = stud.stud_type
  method = stud.method or stud.stud_type
  return group, method


def _fixed_rear_board_for_group(group: str) -> tuple[str | None, float | None] | None:
  if _is_ch_stud_group(group):
    if "개량형" in group:
      return (None, CH_STUD_IMPROVED_REAR_BOARD_THICKNESS_MM)
    return (None, CH_STUD_REAR_BOARD_THICKNESS_MM)
  if _is_i_stud_group(group):
    # 후면 한 장 끼움 구성은 유지하되 종류·두께는 사용자 선택 물성을 적용한다.
    return (None, None)
  return None


def _is_ch_stud_group(group: str) -> bool:
  return group.replace(" ", "").upper().startswith("CH-STUD")


def _is_i_stud_group(group: str) -> bool:
  return group.replace(" ", "").upper() == "I-STUD"


def _is_r_stud_group(group: str) -> bool:
  return group.replace(".", "-").replace(" ", "").upper() == "R-STUD"


def _validate_fixed_rear_boards(
  group: str,
  rear_boards: tuple[BoardLayer, ...],
  fixed_rear_board: tuple[str | None, float | None],
) -> None:
  required_kind, required_thickness_mm = fixed_rear_board
  if required_thickness_mm is None:
    if len(rear_boards) != 1:
      raise ValueError(f"{group}는 선택한 종류·두께의 후면 석고보드 1장이 필요합니다.")
    return
  required_label = (
    f"{required_kind} {required_thickness_mm:g}T"
    if required_kind is not None
    else f"{required_thickness_mm:g}T"
  )
  if len(rear_boards) != 1:
    raise ValueError(
      f"{group}는 후면 석고보드 1장만 허용되며 {required_label}로 고정입니다.",
    )
  board = rear_boards[0]
  if required_kind is not None and board.kind != required_kind:
    raise ValueError(
      f"{group} 후면 석고보드는 {required_label}로 고정입니다.",
    )
  if not math.isclose(board.thickness, required_thickness_mm, rel_tol=0.0, abs_tol=1e-6):
    raise ValueError(
      f"{group} 후면 석고보드는 {required_label}로 고정입니다.",
    )


def _neutral_axis(layers: tuple[_Layer, ...]) -> float:
  total_area = sum(layer.transformed_area_mm2 for layer in layers)
  if total_area <= 0:
    raise ValueError("환산단면적 합계가 0 이하입니다.")
  return sum(layer.transformed_area_mm2 * layer.y_centroid_mm for layer in layers) / total_area


def _neutral_axis_notices(section: _Section, neutral_axis: float) -> tuple[str, ...]:
  """중립축 위치 검사(심사의견 E-9). 전단 누계(외측→스터드)·Mn 보드항은 중립축이 스터드 안에 있다는 전제에 기반한다.

  - 스터드 범위 안: 안내 없음
  - 스터드와 1번 보드 사이 이격 간극(R-STUD 등) 안: 경고(보드는 모두 중립축 한쪽 — 판정 불변)
  - 스터드에 가장 가까운 1번 보드 두께 안: 경고(판정 불변)
  - 1번 보드를 넘음: 적용 범위 밖으로 보고 계산을 거부(ValueError)
  """
  stud = section.stud_layer
  bottom = stud.y_centroid_mm - section.stud_assembly.centroid_mm
  top = bottom + section.stud_assembly.height_mm
  if bottom <= neutral_axis <= top:
    return ()
  boards = [layer for layer in section.layers if layer.layer_type == "board"]
  if neutral_axis > top:
    side, excess = "전면", neutral_axis - top
    inner = min((layer for layer in boards if layer.y_centroid_mm > top), key=lambda layer: layer.y_centroid_mm, default=None)
    # 스터드 쪽 경계(near)와 반대쪽 경계(far)까지의 거리(중립축 기준, 스터드에서 멀어지는 방향 +)
    near = None if inner is None else inner.y_centroid_mm - inner.thickness_mm / 2.0 - neutral_axis
    far = None if inner is None else inner.y_centroid_mm + inner.thickness_mm / 2.0 - neutral_axis
  else:
    side, excess = "후면", bottom - neutral_axis
    inner = max((layer for layer in boards if layer.y_centroid_mm < bottom), key=lambda layer: layer.y_centroid_mm, default=None)
    near = None if inner is None else neutral_axis - (inner.y_centroid_mm + inner.thickness_mm / 2.0)
    far = None if inner is None else neutral_axis - (inner.y_centroid_mm - inner.thickness_mm / 2.0)
  location = f"중립축({neutral_axis:.1f} mm)이 스터드 범위({bottom:.1f}~{top:.1f} mm)를 {side} 보드 쪽으로 {excess:.1f} mm 벗어남"
  if near is not None and near > 0.0:
    return (f"{location} — 스터드와 {side} 1번(내측) 보드 사이 이격 간극 안이므로 계산하나, 결과 적용에 유의할 것",)
  if far is not None and far >= 0.0:
    return (f"{location} — {side} 1번(내측) 보드 두께 안이므로 계산하나, 부분합성 전단 누계 전제와 차이가 있어 결과 적용에 유의할 것",)
  raise ValueError(
    f"{location}. {side} 1번(내측) 보드도 넘어 부분합성 전단 누계 전제가 성립하지 않는 적용 범위 밖 구성입니다. "
    f"{side} 보드를 줄이거나 반대면 보드를 추가하십시오."
  )


def _layer_results(layers: tuple[_Layer, ...], neutral_axis: float) -> tuple[LayerResult, ...]:
  results: list[LayerResult] = []
  for layer in layers:
    distance = layer.y_centroid_mm - neutral_axis
    results.append(
      LayerResult(
        name=layer.name,
        layer_type=layer.layer_type,
        y_centroid_mm=layer.y_centroid_mm,
        transformed_area_mm2=layer.transformed_area_mm2,
        distance_to_neutral_axis_mm=distance,
        inertia_about_neutral_axis_mm4=layer.transformed_area_mm2 * distance**2 + layer.self_inertia_mm4,
        axial_strength_kN=layer.axial_strength_kN,
      )
    )
  return tuple(results)


def _shear_connection_by_layer(
  section: _Section,
  request: WallCheckRequest,
  for_strength: bool = False,
) -> dict[str, float]:
  """외곽→내측 피스 전단 누계. for_strength=True이면 Mn용(석고보드 피스 설계강도 상한 적용)."""
  layers = section.layers
  stud_thickness_mm = _stud_thickness_mm(section)
  stud_fu = _stud_steel(section.stud_section).Fu
  result: dict[str, float] = {}
  stud_index = next(index for index, layer in enumerate(layers) if layer.layer_type == "stud")
  rear_layers = tuple(layer for layer in layers[:stud_index] if layer.layer_type == "board")
  front_layers = tuple(layer for layer in layers[stud_index + 1 :] if layer.layer_type == "board")

  for layer, value in _side_cumulative_shear(rear_layers, request, stud_thickness_mm, stud_fu, for_strength).items():
    result[layer] = value
  for layer, value in _side_cumulative_shear(
    tuple(reversed(front_layers)), request, stud_thickness_mm, stud_fu, for_strength
  ).items():
    result[layer] = value
  return result


def _side_cumulative_shear(
  layers_outer_to_inner: tuple[_Layer, ...],
  request: WallCheckRequest,
  stud_thickness_mm: float,
  stud_tensile_strength: float,
  for_strength: bool = False,
) -> dict[str, float]:
  cumulative = 0.0
  result: dict[str, float] = {}
  for layer in layers_outer_to_inner:
    capacity = _connection_capacity_kN(
      layer, request.bolt, request.span_mm, stud_thickness_mm=stud_thickness_mm,
      stud_tensile_strength=stud_tensile_strength,
      for_strength=for_strength,
    )
    cumulative += min(layer.axial_strength_kN, capacity)
    result[layer.name] = cumulative
  return result


def _gypsum_screw_design_shear_N(board_thickness_mm: float) -> float:
  """석고보드–스터드 피스 1개당 설계 전단강도(N) — AISI S240-20 해설 Table C-B3.2-1(No.6) 극한 / 2.0.

  12.7 mm 미만은 두께 비례 외삽(확인 필요), 12.7~15.9 mm는 선형 보간, 15.9 mm 초과는 15.9 mm 값(문헌 없음, 보수측).
  """
  (t1, u1), (t2, u2) = GYPSUM_SCREW_ULTIMATE_SHEAR_N
  if board_thickness_mm <= t1:
    ultimate = u1 * board_thickness_mm / t1
  elif board_thickness_mm < t2:
    ultimate = u1 + (u2 - u1) * (board_thickness_mm - t1) / (t2 - t1)
  else:
    ultimate = u2
  return ultimate / GYPSUM_SCREW_STRENGTH_DIVISOR


def _layer_pitch_count(layer: _Layer, bolt: BoltInput) -> tuple[float, float]:
  order = layer.connection_order or layer.order
  pitch = layer.connection_pitch_mm if layer.connection_pitch_mm is not None else _pitch_for_order(bolt.pitch, order)
  count = layer.connection_count if layer.connection_count is not None else _count_for_order(bolt.count, order)
  return pitch, count


def _stud_thickness_mm(section: _Section) -> float:
  thickness = section.stud_section.t
  if thickness is None:
    raise ValueError(f"스터드 {section.stud_section.name} 두께 t가 없어 피스 tilting·지압을 검토할 수 없습니다.")
  return thickness


def _screw_stud_side_shear_N(stud_thickness_mm: float, diameter_mm: float, stud_tensile_strength: float) -> float:
  """피스 1개당 스터드(강재)측 허용 전단강도(N) — AISI S100-16 J4.3.1 (t2/t1 ≤ 1.0) min(tilting, 스터드 지압) / Ω."""
  tilting = SCREW_TILTING_COEFFICIENT * math.sqrt(stud_thickness_mm**3 * diameter_mm) * stud_tensile_strength
  bearing = SCREW_STUD_BEARING_COEFFICIENT * stud_thickness_mm * diameter_mm * stud_tensile_strength
  return min(tilting, bearing) / SCREW_SHEAR_OMEGA


def _connection_capacity_kN(
  layer: _Layer,
  bolt: BoltInput,
  span_mm: float,
  stud_thickness_mm: float,
  stud_tensile_strength: float,
  for_strength: bool = False,
) -> float:
  if layer.board_property is None:
    return 0.0
  pitch, count = _layer_pitch_count(layer, bolt)
  board_bearing_strength = layer.board_property.Fu
  # 피스 1개당 전단강도 = 0.5 × Fv × Ab / 1.25 (EN 1993-1-8 인용), Fv = 0.6 × Fy
  shear_n = (
    0.5
    * BOLT_SHEAR_TO_YIELD_RATIO
    * bolt.yield_strength
    * math.pi
    / 4.0
    * bolt.diameter**2
    / 1.25
  )
  bearing_n = 2.0 * 0.85 * layer.thickness_mm * bolt.diameter * board_bearing_strength
  # 스터드측 tilting·지압 한계(Ω 3.0)는 강성·강도 경로 모두 적용
  per_screw_n = min(shear_n, bearing_n, _screw_stud_side_shear_N(stud_thickness_mm, bolt.diameter, stud_tensile_strength))
  if for_strength:
    # 강도(Mn)용: 석고보드 피스 문헌 설계강도로 상한(강성 η·R 보정에는 미적용)
    per_screw_n = min(per_screw_n, _gypsum_screw_design_shear_N(layer.thickness_mm))
  return per_screw_n * count * (span_mm / 2.0) / pitch * 1e-3


def _pitch_for_order(pitches: tuple[float, ...], order: int) -> float:
  if not pitches:
    raise ValueError("볼트 간격이 비어 있습니다.")
  if order >= 3 and len(pitches) >= 1:
    return pitches[0]
  if order == 2 and len(pitches) >= 2:
    return pitches[1]
  if order <= 1 and len(pitches) >= 3:
    return pitches[2]
  return pitches[-1]


def bolt_values_from_ply_order(ply_values: tuple[float, ...]) -> tuple[float, ...]:
  """층별 값(피스 간격·개수)을 [1P(내측, 스터드 인접), 2P, 3P(외측)] 순서(엑셀 VAR. C32:C34 등)에서
  엔진 bolt.pitch·bolt.count 순서 [외측, 중간, 내측]로 변환한다."""
  if len(ply_values) != 3:
    raise ValueError(f"층별 피스 값은 1P·2P·3P 3개가 필요합니다: {ply_values}")
  return tuple(reversed(ply_values))


def _screw_pitch_notices(section: _Section, bolt: BoltInput) -> tuple[str, ...]:
  """표준 외 피스 간격 경고(판정 불변). CH·I-STUD 고정 후면 보드(간격 고정)는 제외한다."""
  # _pitch_for_order와 같은 기준으로 order를 1~3에 정규화한 뒤 중복 제거(order ≥ 3은 모두 외측 피치)
  stud_index = next(i for i, layer in enumerate(section.layers) if layer.layer_type == "stud")
  bilateral_single_ply = (
    sum(layer.layer_type == "board" for layer in section.layers[:stud_index]) == 1
    and sum(layer.layer_type == "board" for layer in section.layers[stud_index + 1:]) == 1
  )
  orders = sorted(
    {
      min(max(layer.connection_order or layer.order, 1), 3)
      for layer in section.layers
      if layer.layer_type == "board" and layer.connection_pitch_mm is None
    }
  )
  notices: list[str] = []
  for order in orders:
    pitch = _pitch_for_order(bolt.pitch, order)
    standard = (
      BILATERAL_SINGLE_PLY_SCREW_PITCH_MM
      if bilateral_single_ply and order == 1
      else _pitch_for_order(STANDARD_SCREW_PITCH_MM, order)
    )
    if math.isclose(pitch, standard):
      continue
    label = BOARD_ORDER_LABELS[order]
    notices.append(
      f"{label} 피스 간격 {pitch:g} mm는 표준 간격 {standard:g} mm와 다름 — 실험 검증 범위 밖의 입력이므로 결과 적용에 유의할 것"
    )
  return tuple(notices)


def _count_for_order(counts: tuple[float, ...], order: int) -> float:
  if not counts:
    raise ValueError("볼트 개수가 비어 있습니다.")
  if order >= 3 and len(counts) >= 1:
    return counts[0]
  if order == 2 and len(counts) >= 2:
    return counts[1]
  if order <= 1 and len(counts) >= 3:
    return counts[2]
  return counts[-1]


def _composite_ratio(layers: tuple[_Layer, ...], shear_by_name: dict[str, float]) -> float:
  ratios = [
    shear_by_name[layer.name] / layer.axial_strength_kN
    for layer in layers
    if layer.layer_type == "board" and layer.axial_strength_kN > 0 and shear_by_name.get(layer.name, 0.0) > 0
  ]
  if not ratios:
    return 0.0
  return max(0.0, min(1.0, min(ratios)))


def _stud_section_modulus(
  stud_layer: LayerResult,
  assembly: _StudAssembly,
  composite: bool,
) -> tuple[float, float]:
  """스터드 유효단면계수 Se(mm³)와 최외단 거리 c(mm)를 반환한다.

  - 부분합성: 합성 중립축 기준 스터드 I / 합성 중립축~스터드 최외단 거리
  - 스터드 단독: 스터드 자체 도심 기준 I / 자체 도심~최외단 거리(비대칭 단면은 큰 쪽)
  두 경우 모두 총단면 S에 Se/Sx 비(AISI S100-16 부록 1)를 곱한다.
  """
  if composite:
    neutral_axis = stud_layer.y_centroid_mm - stud_layer.distance_to_neutral_axis_mm
    y_bottom = stud_layer.y_centroid_mm - assembly.centroid_mm
    y_top = y_bottom + assembly.height_mm
    extreme_fiber = max(neutral_axis - y_bottom, y_top - neutral_axis)
    inertia = stud_layer.inertia_about_neutral_axis_mm4
  else:
    extreme_fiber = max(assembly.centroid_mm, assembly.height_mm - assembly.centroid_mm)
    inertia = assembly.self_inertia_mm4
  if extreme_fiber <= 0.0:
    raise ValueError("스터드 최외단 거리가 0 이하입니다.")
  return inertia / extreme_fiber * assembly.effective_section_ratio, extreme_fiber


def _nominal_moment(
  layers: tuple[LayerResult, ...],
  shear_by_name: dict[str, float],
  stud_section_modulus_mm3: float,
  stud_yield_strength: float,
  include_board_layers: bool = True,
) -> float:
  total = 0.0
  for layer in layers:
    if layer.layer_type == "board":
      if not include_board_layers:
        continue
      force = min(layer.axial_strength_kN, shear_by_name.get(layer.name, 0.0))
      total += abs(force * layer.distance_to_neutral_axis_mm * 1e-3)
    else:
      total += stud_yield_strength * stud_section_modulus_mm3 * 1e-6
  return total


def _strength_check_nominal_moment(
  strength_check_mode: str,
  composite_moment_kNm: float,
  stud_only_moment_kNm: float,
) -> float:
  if strength_check_mode == STRENGTH_CHECK_STUD_ONLY:
    return stud_only_moment_kNm
  return composite_moment_kNm


def _maximum_allowable_height_mm(
  request: WallCheckRequest,
  repository: MaterialRepository,
) -> float:
  search_limit = max(
    MAX_HEIGHT_SEARCH_LIMIT_MM,
    math.ceil(request.span_mm / MAX_HEIGHT_INCREMENT_MM) * MAX_HEIGHT_INCREMENT_MM,
  )
  max_height = 0.0
  for height_mm in range(MAX_HEIGHT_INCREMENT_MM, int(search_limit) + MAX_HEIGHT_INCREMENT_MM, MAX_HEIGHT_INCREMENT_MM):
    trial_request = replace(request, span_mm=float(height_mm))
    result = _calculate_wall_check_once(trial_request, repository)
    if _all_checks_ok(result):
      max_height = float(height_mm)
  return max_height


def _maximum_anchor_allowable_height_mm(
  request: WallCheckRequest,
  repository: MaterialRepository,
) -> float:
  if request.design_case == DESIGN_CASE_NON_SEISMIC:
    return 0.0
  search_limit = max(
    MAX_HEIGHT_SEARCH_LIMIT_MM,
    math.ceil(request.span_mm / MAX_HEIGHT_INCREMENT_MM) * MAX_HEIGHT_INCREMENT_MM,
  )
  max_height = 0.0
  for height_mm in range(MAX_HEIGHT_INCREMENT_MM, int(search_limit) + MAX_HEIGHT_INCREMENT_MM, MAX_HEIGHT_INCREMENT_MM):
    trial_request = replace(request, span_mm=float(height_mm))
    result = _calculate_wall_check_once(trial_request, repository)
    anchor_utilization = result.intermediate.get("anchor_utilization", math.inf)
    if _all_checks_ok(result) and anchor_utilization <= 1.0:
      max_height = float(height_mm)
  return max_height


def _deflection_mm(request: WallCheckRequest, I_eff_mm4: float) -> float:
  line_load_N_mm = request.live_load_kN_m2 * (request.spacing_mm / 1000.0)
  return 5.0 * line_load_N_mm * request.span_mm**4 / (384.0 * STUD_ELASTIC_MODULUS * I_eff_mm4)


def _live_moment_kNm(request: WallCheckRequest) -> float:
  spacing_m = request.spacing_mm / 1000.0
  span_m = request.span_mm / 1000.0
  return request.live_load_kN_m2 * spacing_m * span_m**2 / 8.0


def _required_moment_kNm(request: WallCheckRequest, live_moment: float, seismic_moment: float) -> float:
  if request.design_case == DESIGN_CASE_NON_SEISMIC:
    return live_moment
  return max(
    live_moment,
    ASD_SEISMIC_FACTOR * seismic_moment,
    _combined_live_seismic(live_moment, seismic_moment),
  )


def _combined_live_seismic(live: float, seismic: float) -> float:
  """KDS 41 10 15 허용응력 조합 0.75L + 0.75(0.7E)."""
  return ASD_COMBINED_LIVE_FACTOR * live + ASD_COMBINED_SEISMIC_FACTOR * ASD_SEISMIC_FACTOR * seismic


def _seismic_moment_kNm(
  request: WallCheckRequest,
  layers: tuple[_Layer, ...],
) -> tuple[float, float, float, float]:
  seismic_weight = sum(layer.mass_kN for layer in layers)
  fa = _seismic_fa(request)
  sds = request.seismic.S * 2.5 * 2.0 / 3.0 * fa
  fp = SEISMIC_FP_COEFFICIENT * sds * request.seismic.Ip * seismic_weight
  moment = 0.25 * fp * (request.span_mm / 1000.0)
  return moment, seismic_weight, sds, fp


def _reaction_result_kN_per_m(request: WallCheckRequest, fp_kN: float) -> _ReactionResult:
  spacing_m = request.spacing_mm / 1000.0
  span_m = request.span_mm / 1000.0
  live_per_spacing = request.live_load_kN_m2 * span_m * spacing_m / 2.0
  seismic_per_spacing = fp_kN / 2.0 * 2.0
  live_kN_per_m = live_per_spacing / spacing_m
  seismic_kN_per_m = seismic_per_spacing / spacing_m
  # 앵커 반력의 지진항에만 과강도계수 Ω0 적용
  anchor_seismic_kN_per_m = ANCHOR_SEISMIC_OVERSTRENGTH_FACTOR * seismic_kN_per_m
  load_combination_L = live_kN_per_m
  load_combination_0_7E = ASD_SEISMIC_FACTOR * anchor_seismic_kN_per_m
  load_combination_0_75L_0_525E = _combined_live_seismic(live_kN_per_m, anchor_seismic_kN_per_m)
  if request.design_case == DESIGN_CASE_NON_SEISMIC:
    required = load_combination_L
  else:
    required = max(load_combination_L, load_combination_0_7E, load_combination_0_75L_0_525E)
  anchor_allowable_spacing_mm = _anchor_spacing_floor_mm(
    request.anchor_capacity_kN / required * 1000.0 if required > 0.0 else 0.0,
  )
  anchor_capacity_kN_per_m = request.anchor_capacity_kN / (request.anchor_spacing_mm / 1000.0)
  anchor_utilization = required / anchor_capacity_kN_per_m if anchor_capacity_kN_per_m > 0.0 else math.inf
  return _ReactionResult(
    live_kN_per_m=live_kN_per_m,
    seismic_kN_per_m=seismic_kN_per_m,
    load_combination_L_kN_per_m=load_combination_L,
    load_combination_0_7E_kN_per_m=load_combination_0_7E,
    load_combination_0_75L_0_525E_kN_per_m=load_combination_0_75L_0_525E,
    required_kN_per_m=required,
    anchor_capacity_kN=request.anchor_capacity_kN,
    anchor_spacing_mm=request.anchor_spacing_mm,
    anchor_allowable_spacing_mm=anchor_allowable_spacing_mm,
    anchor_capacity_kN_per_m=anchor_capacity_kN_per_m,
    anchor_utilization=anchor_utilization,
  )


def _reaction_intermediate(request: WallCheckRequest, reaction: _ReactionResult) -> dict[str, float]:
  values = {
    "reaction_L_kN_per_m": reaction.load_combination_L_kN_per_m,
    "reaction_required_kN_per_m": reaction.required_kN_per_m,
  }
  if request.design_case != DESIGN_CASE_NON_SEISMIC:
    values.update(
      {
        "reaction_0_7E_kN_per_m": reaction.load_combination_0_7E_kN_per_m,
        "reaction_0_75L_0_525E_kN_per_m": reaction.load_combination_0_75L_0_525E_kN_per_m,
        "anchor_seismic_overstrength_factor": ANCHOR_SEISMIC_OVERSTRENGTH_FACTOR,
        "anchor_capacity_kN": reaction.anchor_capacity_kN,
        "anchor_spacing_mm": reaction.anchor_spacing_mm,
        "anchor_allowable_spacing_mm": reaction.anchor_allowable_spacing_mm,
        "anchor_capacity_kN_per_m": reaction.anchor_capacity_kN_per_m,
        "anchor_utilization": reaction.anchor_utilization,
      }
    )
  return values


def _anchor_spacing_floor_mm(value: float) -> float:
  if value <= 0.0 or not math.isfinite(value):
    return 0.0
  return math.floor(value / ANCHOR_SPACING_INCREMENT_MM) * ANCHOR_SPACING_INCREMENT_MM


def _seismic_fa(request: WallCheckRequest) -> float:
  if request.seismic.Fa is not None:
    return request.seismic.Fa
  return calculate_fa(
    request.seismic.site_class,
    request.seismic.S,
    request.seismic.s5_bedrock_depth_unknown,
  )


def _validate_design_case(design_case: str) -> None:
  if design_case not in DESIGN_CASES:
    raise ValueError(f"지원하지 않는 검토 CASE입니다: {design_case}")


def _validate_strength_check_mode(strength_check_mode: str) -> None:
  if strength_check_mode not in STRENGTH_CHECK_MODES:
    raise ValueError(f"지원하지 않는 강도 체크 기준입니다: {strength_check_mode}")


def _all_checks_ok(result: WallCheckResult) -> bool:
  return (
    result.stress_verdict == "O.K"
    and result.deflection_verdict == "O.K"
    and result.screw_tension_verdict == "O.K"
  )


def _screw_tension_result(
  request: WallCheckRequest,
  section: _Section,
  sds: float,
) -> dict[str, float]:
  """피스 인장(면외 이탈) 검토 — AISI S100-16 J4.4.

  - 요구 인장력 T = q × s × p_max [N/개] (피치당 피스 1개, 보수측)
    q: 면별 설계 횡압력(kN/m²) = L 또는 max(L, 0.7E, 0.75L + 0.75(0.7E)),
       E = 0.48·SDS·Ip × (해당 면 보드 자중). 면의 전체 하중을 피스가 가장 성긴 층이 부담한다고 가정(보수측).
  - 풀아웃 Pnot = 0.85·tc·d·Fu2 (Eq. J4.4.1-1), tc = 스터드 두께, Ω = 3.0
  - 풀스루(석고보드) = 입력 공칭값 / Ω (AISI 강판식 J4.4.2는 석고보드에 적용 불가)
  벽 높이와 무관한 검토이다.
  """
  stud = section.stud_section
  if stud.t is None:
    raise ValueError(f"스터드 두께 t가 등록되지 않아 피스 풀아웃 검토를 할 수 없습니다: {stud.group} {stud.name}")
  stud_index = next(index for index, layer in enumerate(section.layers) if layer.layer_type == "stud")
  faces = (
    tuple(layer for layer in section.layers[:stud_index] if layer.layer_type == "board"),
    tuple(layer for layer in section.layers[stud_index + 1 :] if layer.layer_type == "board"),
  )
  demand_N = 0.0
  governing_pressure = 0.0
  governing_spacing = 0.0
  for face in faces:
    if not face:
      continue
    face_weight_kN_m2 = sum(
      layer.board_property.mass_kg_m2 * GRAVITY / 1000.0
      for layer in face
      if layer.board_property is not None
    )
    seismic_kN_m2 = SEISMIC_FP_COEFFICIENT * sds * request.seismic.Ip * face_weight_kN_m2
    live = request.live_load_kN_m2
    if request.design_case == DESIGN_CASE_NON_SEISMIC:
      pressure = live
    else:
      pressure = max(live, ASD_SEISMIC_FACTOR * seismic_kN_m2, _combined_live_seismic(live, seismic_kN_m2))
    # 보수측: 피치당 피스 1개로 봄(bolt.count는 보드 이음부 2열 체결 등을 포함할 수 있어 인장 분담에는 미적용 — 확인 필요)
    spacing_per_screw = max(_layer_pitch_count(layer, request.bolt)[0] for layer in face)
    face_demand = pressure * 1e-3 * request.spacing_mm * spacing_per_screw
    if face_demand > demand_N:
      demand_N = face_demand
      governing_pressure = pressure
      governing_spacing = spacing_per_screw
  pullout_nominal = SCREW_PULLOUT_COEFFICIENT * stud.t * request.bolt.diameter * _stud_steel(stud).Fu
  pullout_allowable = pullout_nominal / SCREW_TENSION_OMEGA
  pull_through_allowable = request.screw_pull_through_nominal_N / SCREW_TENSION_OMEGA
  pullout_utilization = demand_N / pullout_allowable
  pull_through_utilization = demand_N / pull_through_allowable
  return {
    "screw_tension_pressure_kN_m2": governing_pressure,
    "screw_tension_spacing_mm": governing_spacing,
    "screw_tension_demand_N": demand_N,
    "screw_pullout_tc_mm": stud.t,
    "screw_pullout_nominal_N": pullout_nominal,
    "screw_pullout_allowable_N": pullout_allowable,
    "screw_pull_through_nominal_N": request.screw_pull_through_nominal_N,
    "screw_pull_through_allowable_N": pull_through_allowable,
    "screw_pullout_utilization": pullout_utilization,
    "screw_pull_through_utilization": pull_through_utilization,
    "screw_tension_utilization": max(pullout_utilization, pull_through_utilization),
  }


def _validate_pull_through(value_N: float) -> None:
  if not math.isfinite(value_N) or value_N <= 0.0:
    raise ValueError("석고보드 풀스루 공칭강도는 0보다 커야 합니다.")


def _validate_anchor_spacing(anchor_spacing_mm: float) -> None:
  if anchor_spacing_mm < ANCHOR_SPACING_MIN_MM or anchor_spacing_mm > ANCHOR_SPACING_MAX_MM:
    raise ValueError(
      f"앵커 간격은 {ANCHOR_SPACING_MIN_MM:g}mm 이상 {ANCHOR_SPACING_MAX_MM:g}mm 이하로 입력해야 합니다.",
    )
  quotient = anchor_spacing_mm / ANCHOR_SPACING_INCREMENT_MM
  if not math.isclose(quotient, round(quotient), rel_tol=0.0, abs_tol=1e-9):
    raise ValueError(f"앵커 간격은 {ANCHOR_SPACING_INCREMENT_MM:g}mm 단위로 입력해야 합니다.")
