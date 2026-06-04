"""석고보드·스터드 부분합성 단면 계산엔진."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from backend.engine.constants import (
  DEFAULT_DEFLECTION_LIMIT_DENOM,
  DEFAULT_OMEGA,
  EXCEL_BOARD_BEARING_FACTOR,
  EXCEL_INNER_CONNECTION_FACTOR,
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


@dataclass(frozen=True)
class _Section:
  layers: tuple[_Layer, ...]
  stud_layer: _Layer
  stud_section: StudSection
  stud_multiplier: float


def calculate_wall_check(
  request: WallCheckRequest,
  repository: MaterialRepository | None = None,
) -> WallCheckResult:
  repo = repository or JsonSeedRepository()
  result = _calculate_wall_check_once(request, repo)
  max_height = _maximum_allowable_height_mm(request, repo)
  return replace(
    result,
    max_height_mm=max_height,
    max_height_increment_mm=float(MAX_HEIGHT_INCREMENT_MM),
  )


def _calculate_wall_check_once(
  request: WallCheckRequest,
  repository: MaterialRepository,
) -> WallCheckResult:
  repo = repository
  section = _build_section(request, repo)
  neutral_axis = _neutral_axis(section.layers)
  layer_results = _layer_results(section.layers, neutral_axis)
  I_full = sum(layer.inertia_about_neutral_axis_mm4 for layer in layer_results)
  stud_result = next(layer for layer in layer_results if layer.layer_type == "stud")

  shear_by_name = _shear_connection_by_layer(section.layers, request)
  eta = _composite_ratio(section.layers, shear_by_name)
  I_eff = stud_result.inertia_about_neutral_axis_mm4 + math.sqrt(eta) * (
    I_full - stud_result.inertia_about_neutral_axis_mm4
  )
  Mn = _nominal_moment(layer_results, shear_by_name, section.stud_layer.thickness_mm)
  deflection = _deflection_mm(request, I_eff)
  deflection_limit = request.span_mm / request.deflection_limit_denom
  seismic_moment, seismic_weight, sds, fp = _seismic_moment_kNm(request, section.layers)
  live_moment = _live_moment_kNm(request)
  Mu = max(live_moment, 0.7 * seismic_moment, 0.75 * live_moment + 0.7 * seismic_moment)
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
      "live_moment_kNm": live_moment,
      "seismic_weight_kN": seismic_weight,
      "Fa": _seismic_fa(request),
      "Sds": sds,
      "Fp_kN": fp,
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
  yield_strength_raw = inputs.get("bolt_yield_strength", inputs.get("bolt_fracture"))
  if yield_strength_raw is None:
    raise ValueError("골든 케이스 bolt_yield_strength 형식이 올바르지 않습니다.")

  return WallCheckRequest(
    rear_boards=tuple(rear),
    front_boards=tuple(front),
    stud=StudInput(stud_type=str(inputs["stud_type"]), spec=str(inputs["stud_spec"])),
    horizontal_load_kg_m2=float(inputs["horizontal_load_kg_m2"]),
    live_load_kN_m2=float(inputs.get("live_load_kN_m2", float(inputs["horizontal_load_kg_m2"]) / 100.0)),
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
    omega=DEFAULT_OMEGA,
  )


def _build_section(request: WallCheckRequest, repo: MaterialRepository) -> _Section:
  group, method = _parse_stud_type(request.stud)
  stud = repo.get_stud(group, request.stud.spec)
  stud_multiplier = 2.0 if "맞댐" in method else 1.0
  layers: list[_Layer] = []
  y_cursor = 0.0

  for board in _assign_rear_orders(request.rear_boards):
    layer, y_cursor = _board_layer(board, y_cursor, request, repo)
    layers.append(layer)

  stud_layer = _stud_layer(stud, y_cursor, request, stud_multiplier)
  layers.append(stud_layer)
  y_cursor += stud_layer.thickness_mm

  for board in _assign_front_orders(request.front_boards):
    layer, y_cursor = _board_layer(board, y_cursor, request, repo)
    layers.append(layer)

  return _Section(
    layers=tuple(layers),
    stud_layer=stud_layer,
    stud_section=stud,
    stud_multiplier=stud_multiplier,
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
    ),
    y_bottom + board.thickness,
  )


def _stud_layer(
  stud: StudSection,
  y_bottom: float,
  request: WallCheckRequest,
  multiplier: float,
) -> _Layer:
  area = stud.A * multiplier
  height = stud.H
  y_centroid = y_bottom + stud.cy
  mass = area * request.span_mm * 1e-9 * STEEL_DENSITY_KG_M3 * GRAVITY / 1000.0
  return _Layer(
    name=f"{stud.group}-{stud.name}",
    layer_type="stud",
    order=0,
    thickness_mm=height,
    y_centroid_mm=y_centroid,
    transformed_area_mm2=area,
    self_inertia_mm4=stud.Ix * multiplier,
    axial_strength_kN=area * STUD_YIELD_STRENGTH * 1e-3,
    mass_kN=mass,
  )


def _parse_stud_type(stud: StudInput) -> tuple[str, str]:
  if "(" in stud.stud_type:
    group = stud.stud_type.split("(", maxsplit=1)[0]
  else:
    group = stud.stud_type
  method = stud.method or stud.stud_type
  return group, method


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
    capacity = _connection_capacity_kN(layer, request.bolt, request.span_mm)
    cumulative += min(layer.axial_strength_kN, capacity)
    result[layer.name] = cumulative
  return result


def _connection_capacity_kN(layer: _Layer, bolt: BoltInput, span_mm: float) -> float:
  if layer.board_property is None:
    return 0.0
  pitch = _pitch_for_order(bolt.pitch, layer.order)
  count = _count_for_order(bolt.count, layer.order)
  order_factor = EXCEL_INNER_CONNECTION_FACTOR if layer.order == 1 else 1.0
  board_bearing_strength = layer.board_property.Fy * EXCEL_BOARD_BEARING_FACTOR
  shear_n = 0.6 * bolt.yield_strength * math.pi / 4.0 * bolt.diameter**2 / 1.25
  shear_n *= count * order_factor
  bearing_n = 2.0 * 0.85 * layer.thickness_mm * count * bolt.diameter * board_bearing_strength
  bearing_n *= order_factor
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
  stud_height_mm: float,
) -> float:
  total = 0.0
  for layer in layers:
    if layer.layer_type == "board":
      force = min(layer.axial_strength_kN, shear_by_name.get(layer.name, 0.0))
      total += abs(force * layer.distance_to_neutral_axis_mm * 1e-3)
    else:
      section_modulus = layer.inertia_about_neutral_axis_mm4 / stud_height_mm * 2.0
      total += STUD_YIELD_STRENGTH * section_modulus * 1e-6
  return total


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


def _deflection_mm(request: WallCheckRequest, I_eff_mm4: float) -> float:
  line_load_N_mm = request.horizontal_load_kg_m2 * request.spacing_mm * GRAVITY * 1e-6
  return 5.0 * line_load_N_mm * request.span_mm**4 / (384.0 * STUD_ELASTIC_MODULUS * I_eff_mm4)


def _live_moment_kNm(request: WallCheckRequest) -> float:
  spacing_m = request.spacing_mm / 1000.0
  span_m = request.span_mm / 1000.0
  return request.live_load_kN_m2 * spacing_m * span_m**2 / 8.0


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


def _seismic_fa(request: WallCheckRequest) -> float:
  if request.seismic.Fa is not None:
    return request.seismic.Fa
  return calculate_fa(
    request.seismic.site_class,
    request.seismic.S,
    request.seismic.s5_bedrock_depth_unknown,
  )
