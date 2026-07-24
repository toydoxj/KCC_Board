"""석고보드·스터드 부분합성 단면 계산엔진."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from backend.engine.constants import (
  ANCHOR_SPACING_INCREMENT_MM,
  ANCHOR_SPACING_MAX_MM,
  ANCHOR_SPACING_MIN_MM,
  BOLT_SHEAR_TO_YIELD_RATIO,
  DEFAULT_ANCHOR_CAPACITY_KN,
  DEFAULT_ANCHOR_SPACING_MM,
  DEFAULT_DEFLECTION_LIMIT_DENOM,
  DEFAULT_HORIZONTAL_LOAD_KG_M2,
  DEFAULT_OMEGA,
  GRAVITY,
  STEEL_DENSITY_KG_M3,
  STUD_ELASTIC_MODULUS,
  STUD_YIELD_STRENGTH,
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
from backend.engine.repository import BoardProperty, JsonSeedRepository, MaterialRepository, StudSection
from backend.engine.seismic import calculate_fa

MAX_HEIGHT_INCREMENT_MM = 50
MAX_HEIGHT_SEARCH_LIMIT_MM = 30000
CENTRAL_JOINT_STUD_GAP_MM = 25.0
CH_STUD_REAR_BOARD_THICKNESS_MM = 25.0
CH_STUD_IMPROVED_REAR_BOARD_THICKNESS_MM = 12.5
I_STUD_REAR_BOARD_KIND = "방화"
I_STUD_REAR_BOARD_THICKNESS_MM = 25.0
R_STUD_BOARD_STUD_CLEAR_GAP_MM = 12.0
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
  fully_composite_with_stud: bool = False


@dataclass(frozen=True)
class _Section:
  layers: tuple[_Layer, ...]
  stud_layer: _Layer
  stud_section: StudSection
  stud_multiplier: float
  stud_unfactored_self_inertia_mm4: float
  stud_connection_inertia_factor: float
  stud_section_modulus_depth_mm: float


@dataclass(frozen=True)
class _StudAssembly:
  area_mm2: float
  height_mm: float
  centroid_mm: float
  self_inertia_mm4: float
  unfactored_self_inertia_mm4: float
  connection_inertia_factor: float
  multiplier: float
  section_modulus_depth_mm: float


@dataclass(frozen=True)
class _ReactionResult:
  live_kN_per_m: float
  seismic_kN_per_m: float
  load_combination_L_kN_per_m: float
  load_combination_0_7E_kN_per_m: float
  load_combination_0_75L_0_7E_kN_per_m: float
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
  repo = repository
  section = _build_section(request, repo)
  neutral_axis = _neutral_axis(section.layers)
  layer_results = _layer_results(section.layers, neutral_axis)
  I_full = sum(layer.inertia_about_neutral_axis_mm4 for layer in layer_results)
  stud_result = next(layer for layer in layer_results if layer.layer_type == "stud")

  shear_by_name = _shear_connection_by_layer(section.layers, request)
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
  I_eff = I_eff_raw * I_eff_correction_factor
  Mn_composite = _nominal_moment(layer_results, shear_by_name, section.stud_section_modulus_depth_mm)
  Mn_stud_only = _nominal_moment(
    layer_results,
    shear_by_name,
    section.stud_section_modulus_depth_mm,
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
    layers=enriched_layers,
    intermediate={
      "stud_I_mm4": stud_result.inertia_about_neutral_axis_mm4,
      "stud_I_unfactored_mm4": section.stud_unfactored_self_inertia_mm4,
      "stud_section_height_mm": section.stud_layer.thickness_mm,
      "stud_section_modulus_depth_mm": section.stud_section_modulus_depth_mm,
      "stud_connection_inertia_factor": section.stud_connection_inertia_factor,
      "Mn_composite_kNm": Mn_composite,
      "Mn_stud_only_kNm": Mn_stud_only,
      "I_eff_raw_mm4": I_eff_raw,
      "I_eff_correction_factor": I_eff_correction_factor,
      "live_moment_kNm": live_moment,
      "moment_L_kNm": live_moment,
      "moment_0_7E_kNm": 0.7 * seismic_moment,
      "moment_0_75L_0_7E_kNm": 0.75 * live_moment + 0.7 * seismic_moment,
      "vertical_load_kN_m": request.vertical_load_kN_m,
      "seismic_weight_kN": seismic_weight,
      "Fa": _seismic_fa(request),
      "Sds": sds,
      "Fp_kN": fp,
      "reaction_live_kN_per_m": reaction.live_kN_per_m,
      "reaction_seismic_kN_per_m": reaction.seismic_kN_per_m,
      **_reaction_intermediate(request, reaction),
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
      pitch=tuple(float(value) for value in pitch_raw),
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
  stud = repo.get_stud(group, request.stud.spec)
  stud_assembly = _stud_assembly(stud, method)
  fixed_rear_board = _fixed_rear_board_for_group(group)
  if fixed_rear_board is not None:
    _validate_fixed_rear_boards(group, request.rear_boards, fixed_rear_board)
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
      fully_composite_with_stud=fixed_rear_board is not None,
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

  return _Section(
    layers=tuple(layers),
    stud_layer=stud_layer,
    stud_section=stud,
    stud_multiplier=stud_assembly.multiplier,
    stud_unfactored_self_inertia_mm4=stud_assembly.unfactored_self_inertia_mm4,
    stud_connection_inertia_factor=stud_assembly.connection_inertia_factor,
    stud_section_modulus_depth_mm=stud_assembly.section_modulus_depth_mm,
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
  fully_composite_with_stud: bool = False,
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
      fully_composite_with_stud=fully_composite_with_stud,
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
    axial_strength_kN=assembly.area_mm2 * STUD_YIELD_STRENGTH * 1e-3,
    mass_kN=mass,
  )


def _stud_assembly(stud: StudSection, method: str) -> _StudAssembly:
  if _is_central_joint_method(method):
    distance = stud.H + CENTRAL_JOINT_STUD_GAP_MM / 2.0
    self_inertia = 2.0 * (stud.A * distance**2 + stud.Ix)
    return _StudAssembly(
      area_mm2=2.0 * stud.A,
      height_mm=2.0 * stud.H + CENTRAL_JOINT_STUD_GAP_MM,
      centroid_mm=(2.0 * stud.H + CENTRAL_JOINT_STUD_GAP_MM) / 2.0,
      self_inertia_mm4=self_inertia,
      unfactored_self_inertia_mm4=self_inertia,
      connection_inertia_factor=1.0,
      multiplier=2.0,
      section_modulus_depth_mm=stud.H,
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
    section_modulus_depth_mm=stud.H,
  )


def _is_central_joint_method(method: str) -> bool:
  normalized = method.replace(" ", "")
  return "중앙부이음" in normalized or "중앙부연결" in normalized


def _is_basic_method(method: str) -> bool:
  normalized = method.replace(".", "-").replace(" ", "").upper()
  return normalized == "C-STUD" or "기본" in normalized


def _effective_inertia_correction_factor(
  group: str,
  method: str,
  has_rear_board: bool = True,
) -> float:
  normalized_group = group.replace(".", "-").replace(" ", "").upper()
  if normalized_group == "C-STUD":
    if _is_central_joint_method(method):
      return 0.25
    if _is_basic_method(method) and not has_rear_board:
      return 1.0
    return 0.7
  if normalized_group.startswith("CH-STUD"):
    return 0.65
  if normalized_group in {"T-SILENT", "T-SILENT-STUD"}:
    return 0.4
  if normalized_group == "R-STUD":
    return 0.26
  if normalized_group == "I-STUD":
    return 0.87
  if normalized_group == "HR-STUD":
    return 0.71
  if normalized_group == "RV-STUD":
    return 0.43
  if normalized_group == "MP-STUD":
    return 0.42
  return 1.0


def _parse_stud_type(stud: StudInput) -> tuple[str, str]:
  if stud.stud_type.startswith("C-STUD("):
    group = stud.stud_type.split("(", maxsplit=1)[0]
  else:
    group = stud.stud_type
  method = stud.method or stud.stud_type
  return group, method


def _fixed_rear_board_for_group(group: str) -> tuple[str | None, float] | None:
  if _is_ch_stud_group(group):
    if "개량형" in group:
      return (None, CH_STUD_IMPROVED_REAR_BOARD_THICKNESS_MM)
    return (None, CH_STUD_REAR_BOARD_THICKNESS_MM)
  if _is_i_stud_group(group):
    return (I_STUD_REAR_BOARD_KIND, I_STUD_REAR_BOARD_THICKNESS_MM)
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
  fixed_rear_board: tuple[str | None, float],
) -> None:
  required_kind, required_thickness_mm = fixed_rear_board
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
  layers: tuple[_Layer, ...],
  request: WallCheckRequest,
) -> dict[str, float]:
  result: dict[str, float] = {}
  stud_index = next(index for index, layer in enumerate(layers) if layer.layer_type == "stud")
  rear_layers = tuple(layer for layer in layers[:stud_index] if layer.layer_type == "board")
  front_layers = tuple(layer for layer in layers[stud_index + 1 :] if layer.layer_type == "board")

  for layer, value in _side_cumulative_shear(tuple(rear_layers), request).items():
    result[layer] = value
  for layer, value in _side_cumulative_shear(tuple(reversed(front_layers)), request).items():
    result[layer] = value
  return result


def _side_cumulative_shear(layers_outer_to_inner: tuple[_Layer, ...], request: WallCheckRequest) -> dict[str, float]:
  cumulative = 0.0
  result: dict[str, float] = {}
  for layer in layers_outer_to_inner:
    capacity = (
      layer.axial_strength_kN
      if layer.fully_composite_with_stud
      else _connection_capacity_kN(layer, request.bolt, request.span_mm)
    )
    cumulative += min(layer.axial_strength_kN, capacity)
    result[layer.name] = cumulative
  return result


def _connection_capacity_kN(layer: _Layer, bolt: BoltInput, span_mm: float) -> float:
  if layer.board_property is None:
    return 0.0
  pitch = _pitch_for_order(bolt.pitch, layer.order)
  count = _count_for_order(bolt.count, layer.order)
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
  shear_n *= count
  bearing_n = 2.0 * 0.85 * layer.thickness_mm * count * bolt.diameter * board_bearing_strength
  return min(shear_n, bearing_n) * (span_mm / 2.0) / pitch * 1e-3


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


def _nominal_moment(
  layers: tuple[LayerResult, ...],
  shear_by_name: dict[str, float],
  stud_section_modulus_depth_mm: float,
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
      section_modulus = layer.inertia_about_neutral_axis_mm4 / stud_section_modulus_depth_mm * 2.0
      total += STUD_YIELD_STRENGTH * section_modulus * 1e-6
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
    if result.stress_verdict == "O.K" and result.deflection_verdict == "O.K":
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
    if (
      result.stress_verdict == "O.K"
      and result.deflection_verdict == "O.K"
      and anchor_utilization <= 1.0
    ):
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
  return max(live_moment, 0.7 * seismic_moment, 0.75 * live_moment + 0.7 * seismic_moment)


def _seismic_moment_kNm(
  request: WallCheckRequest,
  layers: tuple[_Layer, ...],
) -> tuple[float, float, float, float]:
  seismic_weight = sum(layer.mass_kN for layer in layers)
  fa = _seismic_fa(request)
  sds = request.seismic.S * 2.5 * 2.0 / 3.0 * fa
  fp = 0.48 * sds * request.seismic.Ip * seismic_weight
  moment = 0.25 * fp * (request.span_mm / 1000.0)
  return moment, seismic_weight, sds, fp


def _reaction_result_kN_per_m(request: WallCheckRequest, fp_kN: float) -> _ReactionResult:
  spacing_m = request.spacing_mm / 1000.0
  span_m = request.span_mm / 1000.0
  live_per_spacing = request.live_load_kN_m2 * span_m * spacing_m / 2.0
  seismic_per_spacing = fp_kN / 2.0 * 2.0
  live_kN_per_m = live_per_spacing / spacing_m
  seismic_kN_per_m = seismic_per_spacing / spacing_m
  load_combination_L = live_kN_per_m
  load_combination_0_7E = 0.7 * seismic_kN_per_m
  load_combination_0_75L_0_7E = 0.75 * live_kN_per_m + 0.7 * seismic_kN_per_m
  if request.design_case == DESIGN_CASE_NON_SEISMIC:
    required = load_combination_L
  else:
    required = max(load_combination_L, load_combination_0_7E, load_combination_0_75L_0_7E)
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
    load_combination_0_75L_0_7E_kN_per_m=load_combination_0_75L_0_7E,
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
        "reaction_0_75L_0_7E_kN_per_m": reaction.load_combination_0_75L_0_7E_kN_per_m,
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


def _validate_anchor_spacing(anchor_spacing_mm: float) -> None:
  if anchor_spacing_mm < ANCHOR_SPACING_MIN_MM or anchor_spacing_mm > ANCHOR_SPACING_MAX_MM:
    raise ValueError(
      f"앵커 간격은 {ANCHOR_SPACING_MIN_MM:g}mm 이상 {ANCHOR_SPACING_MAX_MM:g}mm 이하로 입력해야 합니다.",
    )
  quotient = anchor_spacing_mm / ANCHOR_SPACING_INCREMENT_MM
  if not math.isclose(quotient, round(quotient), rel_tol=0.0, abs_tol=1e-9):
    raise ValueError(f"앵커 간격은 {ANCHOR_SPACING_INCREMENT_MM:g}mm 단위로 입력해야 합니다.")
