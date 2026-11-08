"""런너 고정 앵커 제품 허용내력 조회(순수함수).

제품 허용하중 표(data/seed/anchor_product.json)에서 매입깊이·콘크리트 강도로 허용 전단·인장을 찾는다.
보간·외삽은 하지 않는다. 엔진 계산(calculator)은 이 모듈을 호출하지 않으며, API 계층이 조회 결과의
anchor_capacity_kN을 WallCheckRequest에 채워 넘긴다(엔진 순수성 유지).

조회 규칙
1. 강도 무관 제품(표의 concrete_fc_MPa가 전부 None, basis rec): 입력 매입깊이 이하 중 최대 embedment_mm 행.
   입력이 최소 행보다 작으면 오류.
2. 강도 열이 있는 제품(basis asd): (embedment_mm, concrete_fc_MPa) 정확 일치 행. 없으면 오류.
3. design_case가 내진이고 apply_seismic_cap이면 허용 전단 = min(표 값, cap_N). cap 적용 여부를 반환한다.
   cap_N 출처: ICC-ES ESR 공통 SDC D·E·F 런너 고정 허용 전단 90 lbf(400 N) — 국내 적용 타당성 확인 필요.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from backend.engine.models import AnchorLoadRow, AnchorProduct, WallCheckRequest
from backend.engine.repository import MaterialRepository

# 사용자 정의 항목 식별자(시드 anchor_product.json의 family 'custom' 항목). 조회를 거치지 않는다.
ANCHOR_CUSTOM_ID = "custom"
ANCHOR_FAMILY_CUSTOM = "custom"
# 내진 검토 CASE 식별자(calculator.DESIGN_CASE_SEISMIC과 같은 값. 순환 import를 피해 문자열로 둔다)
_DESIGN_CASE_SEISMIC = "seismic"
# N → kN 환산 후 반올림 자릿수
_CAPACITY_KN_DECIMALS = 3


class AnchorLookupError(ValueError):
  """앵커 제품 허용하중 표 조회 실패."""


@dataclass(frozen=True)
class AnchorResolution:
  """조회 결과. anchor_capacity_kN이 WallCheckRequest.anchor_capacity_kN으로 들어간다."""

  anchor_id: str
  anchor_capacity_kN: float
  allowable_shear_N: float
  allowable_tension_kN: float
  # 표에서 고른 행(cap 적용 전 값)
  matched_row: AnchorLoadRow
  table_shear_N: float
  cap_applied: bool
  cap_N: float | None
  basis: str
  basis_label: str
  source: str
  approvals: str
  condition_text: str
  summary: str


def is_custom_anchor(product_id: str | None) -> bool:
  return product_id is None or product_id == ANCHOR_CUSTOM_ID


def product_uses_concrete_strength(product: AnchorProduct) -> bool:
  """표에 콘크리트 강도 열이 있는 제품인지. 시드 무결성 테스트가 제품 내 일관성을 보장한다."""
  if not product.table:
    return False
  return all(row.concrete_fc_MPa is not None for row in product.table)


def embedment_options(product: AnchorProduct) -> tuple[float, ...]:
  return tuple(sorted({row.embedment_mm for row in product.table}))


def concrete_strength_options(product: AnchorProduct, embedment_mm: float) -> tuple[float, ...]:
  return tuple(
    sorted(
      row.concrete_fc_MPa
      for row in product.table
      if row.embedment_mm == embedment_mm and row.concrete_fc_MPa is not None
    )
  )


def resolve_anchor_capacity(
  product: AnchorProduct,
  embedment_mm: float | None,
  concrete_fc_MPa: float | None,
  design_case: str,
  apply_seismic_cap: bool,
  cap_N: float | None,
) -> AnchorResolution:
  if product.family == ANCHOR_FAMILY_CUSTOM or product.anchor_id == ANCHOR_CUSTOM_ID:
    raise AnchorLookupError("사용자 정의 항목은 허용하중 표 조회 대상이 아닙니다. 허용내력을 직접 입력하십시오.")
  if not product.table:
    raise AnchorLookupError(f"앵커 제품 {product.anchor_id}의 허용하중 표가 비어 있습니다.")
  if embedment_mm is None:
    raise AnchorLookupError(f"앵커 제품 {product.anchor_id}: 매입깊이(hET)를 지정해야 합니다.")

  if product_uses_concrete_strength(product):
    row = _match_exact(product, float(embedment_mm), concrete_fc_MPa)
  else:
    row = _match_embedment_floor(product, float(embedment_mm))

  table_shear_N = float(row.allowable_shear_N)
  shear_N = table_shear_N
  cap_applied = False
  if design_case == _DESIGN_CASE_SEISMIC and apply_seismic_cap and cap_N is not None and shear_N > cap_N:
    shear_N = float(cap_N)
    cap_applied = True

  condition_text = _condition_text(product, row)
  return AnchorResolution(
    anchor_id=product.anchor_id,
    anchor_capacity_kN=round(shear_N / 1000.0, _CAPACITY_KN_DECIMALS),
    allowable_shear_N=shear_N,
    allowable_tension_kN=round(float(row.allowable_tension_N) / 1000.0, _CAPACITY_KN_DECIMALS),
    matched_row=row,
    table_shear_N=table_shear_N,
    cap_applied=cap_applied,
    cap_N=None if cap_N is None else float(cap_N),
    basis=product.basis,
    basis_label=product.basis_label,
    source=product.source,
    approvals=product.approvals,
    condition_text=condition_text,
    summary=f"{product.maker} {product.product} / {condition_text} / {product.basis_label} / {product.source}",
  )


def resolve_request_anchor(
  request: WallCheckRequest,
  repo: MaterialRepository,
) -> tuple[WallCheckRequest, AnchorResolution | None]:
  """요청에 앵커 제품이 지정되어 있으면 허용 전단을 조회해 anchor_capacity_kN을 채운 요청을 돌려준다.

  API·CLI 등 호출 계층이 계산 직전에 쓴다. 사용자 정의(custom/None)이면 요청을 그대로 돌려주고 조회 결과는 None이다.
  """
  if is_custom_anchor(request.anchor_product_id):
    return request, None
  product = repo.get_anchor_product(str(request.anchor_product_id))
  cap = repo.get_anchor_seismic_cap()
  resolution = resolve_anchor_capacity(
    product,
    request.anchor_embedment_mm,
    request.anchor_concrete_fc_MPa,
    request.design_case,
    request.anchor_apply_seismic_cap,
    cap.cap_N,
  )
  return replace(request, anchor_capacity_kN=resolution.anchor_capacity_kN), resolution


def _match_exact(product: AnchorProduct, embedment_mm: float, concrete_fc_MPa: float | None) -> AnchorLoadRow:
  if concrete_fc_MPa is None:
    raise AnchorLookupError(
      f"앵커 제품 {product.anchor_id}: 콘크리트 강도(f'c)를 지정해야 합니다. "
      f"선택 가능: {_format_values(concrete_strength_options(product, embedment_mm))} MPa"
    )
  fc = float(concrete_fc_MPa)
  for row in product.table:
    if row.embedment_mm == embedment_mm and row.concrete_fc_MPa == fc:
      return row
  raise AnchorLookupError(
    f"앵커 제품 {product.anchor_id}: hET {embedment_mm:g} mm, f'c {fc:g} MPa 행이 허용하중 표에 없습니다. "
    f"매입깊이 선택 가능: {_format_values(embedment_options(product))} mm"
  )


def _match_embedment_floor(product: AnchorProduct, embedment_mm: float) -> AnchorLoadRow:
  candidates = [row for row in product.table if row.embedment_mm <= embedment_mm]
  if not candidates:
    minimum = min(row.embedment_mm for row in product.table)
    raise AnchorLookupError(
      f"앵커 제품 {product.anchor_id}: 매입깊이 {embedment_mm:g} mm는 표의 최소 매입깊이 {minimum:g} mm보다 작습니다."
    )
  return max(candidates, key=lambda row: row.embedment_mm)


def _condition_text(product: AnchorProduct, row: AnchorLoadRow) -> str:
  if row.concrete_fc_MPa is None:
    return f"hET {row.embedment_mm:g} mm / f'c 강도 무관"
  return f"hET {row.embedment_mm:g} mm / f'c {row.concrete_fc_MPa:g} MPa"


def _format_values(values: tuple[float, ...]) -> str:
  return ", ".join(f"{value:g}" for value in values) if values else "없음"
