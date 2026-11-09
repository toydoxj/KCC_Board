// 런너 고정 앵커 제품 허용내력 조회(화면 참조용). 판정에 쓰는 값은 서버(/api/check)가 같은 규칙으로 조회해
// anchor_capacity_kN을 덮어쓴다(backend/engine/anchor.py). 여기서는 선택 즉시 참조 카드·자동 입력에만 쓴다.
import type { AnchorLoadRow, AnchorProduct, DesignCase } from "./api";

export const ANCHOR_CUSTOM_ID = "custom";
const ANCHOR_FAMILY_CUSTOM = "custom";
// family 표시 순서(시드 family_label을 쓰되 순서만 고정)
const FAMILY_ORDER = ["dx", "gx", "screw", ANCHOR_FAMILY_CUSTOM];

export interface AnchorClientResolution {
  row: AnchorLoadRow;
  tableShearN: number;
  shearN: number;
  tensionN: number;
  capApplied: boolean;
  // 제품 family가 상한 적용 대상(dx·gx)인지. false(screw)면 내진이어도 표 값 그대로
  capEligible: boolean;
  capN: number | null;
  capacityKn: number;
  tensionKn: number;
}

export type AnchorClientResult = { ok: true; value: AnchorClientResolution } | { ok: false; message: string };

export function isCustomAnchor(anchorId: string | null | undefined, product?: AnchorProduct) {
  if (!anchorId || anchorId === ANCHOR_CUSTOM_ID) return true;
  return product?.family === ANCHOR_FAMILY_CUSTOM;
}

export function productUsesConcreteStrength(product: AnchorProduct) {
  return product.table.length > 0 && product.table.every((row) => row.concrete_fc_MPa !== null);
}

export function embedmentOptions(product: AnchorProduct): number[] {
  return Array.from(new Set(product.table.map((row) => row.embedment_mm))).sort((a, b) => a - b);
}

export function concreteStrengthOptions(product: AnchorProduct, embedmentMm: number): number[] {
  return product.table
    .filter((row) => row.embedment_mm === embedmentMm && row.concrete_fc_MPa !== null)
    .map((row) => row.concrete_fc_MPa as number)
    .sort((a, b) => a - b);
}

export function anchorProductLabel(product: AnchorProduct) {
  return `${product.maker} ${product.product}`.trim();
}

export function anchorSourceText(product: AnchorProduct) {
  return `${product.source} (${product.approvals})`;
}

export function groupAnchorProductsByFamily(products: AnchorProduct[]) {
  const groups = new Map<string, { family: string; label: string; items: AnchorProduct[] }>();
  for (const product of products) {
    const group = groups.get(product.family) ?? { family: product.family, label: product.family_label, items: [] };
    group.items.push(product);
    groups.set(product.family, group);
  }
  return Array.from(groups.values()).sort(
    (left, right) => familyRank(left.family) - familyRank(right.family),
  );
}

function familyRank(family: string) {
  const index = FAMILY_ORDER.indexOf(family);
  return index === -1 ? FAMILY_ORDER.length : index;
}

/** 제품 family가 내진 상한 적용 대상(시드 seismic_shear_cap_families)인지. */
export function isCapEligibleFamily(product: AnchorProduct | undefined, capFamilies: readonly string[]) {
  return product !== undefined && capFamilies.includes(product.family);
}

/** 서버 규칙과 동일: rec 제품은 hET 이하 최대 행, asd 제품은 (hET, f'c) 정확 일치, 보간 금지, 내진 cap(dx·gx 한정). */
export function resolveAnchorClient(
  product: AnchorProduct,
  embedmentMm: number | null | undefined,
  concreteFcMPa: number | null | undefined,
  designCase: DesignCase,
  applySeismicCap: boolean,
  capN: number | null,
  capFamilies: readonly string[],
): AnchorClientResult {
  if (isCustomAnchor(product.anchor_id, product)) {
    return { ok: false, message: "사용자 정의 항목은 허용내력을 직접 입력합니다." };
  }
  if (product.table.length === 0) {
    return { ok: false, message: "허용하중 표가 비어 있습니다." };
  }
  if (embedmentMm === null || embedmentMm === undefined || Number.isNaN(embedmentMm)) {
    return { ok: false, message: "매입깊이(hET)를 선택하십시오." };
  }

  let row: AnchorLoadRow | undefined;
  if (productUsesConcreteStrength(product)) {
    if (concreteFcMPa === null || concreteFcMPa === undefined || Number.isNaN(concreteFcMPa)) {
      return { ok: false, message: "콘크리트 강도(f'c)를 선택하십시오." };
    }
    row = product.table.find((item) => item.embedment_mm === embedmentMm && item.concrete_fc_MPa === concreteFcMPa);
    if (!row) {
      return { ok: false, message: `hET ${embedmentMm} mm, f'c ${concreteFcMPa} MPa 행이 허용하중 표에 없습니다.` };
    }
  } else {
    const candidates = product.table.filter((item) => item.embedment_mm <= embedmentMm);
    if (candidates.length === 0) {
      const minimum = Math.min(...product.table.map((item) => item.embedment_mm));
      return { ok: false, message: `매입깊이 ${embedmentMm} mm는 표의 최소 매입깊이 ${minimum} mm보다 작습니다.` };
    }
    row = candidates.reduce((best, item) => (item.embedment_mm > best.embedment_mm ? item : best));
  }

  const tableShearN = row.allowable_shear_N;
  let shearN = tableShearN;
  let capApplied = false;
  const capEligible = isCapEligibleFamily(product, capFamilies);
  if (designCase === "seismic" && applySeismicCap && capEligible && capN !== null && shearN > capN) {
    shearN = capN;
    capApplied = true;
  }
  return {
    ok: true,
    value: {
      row,
      tableShearN,
      shearN,
      tensionN: row.allowable_tension_N,
      capApplied,
      capEligible,
      capN,
      capacityKn: roundKn(shearN),
      tensionKn: roundKn(row.allowable_tension_N),
    },
  };
}

function roundKn(valueN: number) {
  return Math.round(valueN) / 1000;
}
