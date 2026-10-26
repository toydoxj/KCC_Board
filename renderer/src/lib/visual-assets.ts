import manifest from "@/data/stud-assets.json";
import type { StudSection } from "@/lib/api";

// User-supplied UI colors. These never enter the calculation payload.
export const boardColors: Record<string, string> = {
  "고강도일반": "#6FB6E9", "고강도전방수": "#F6B26B", "방균": "#72C9B0",
  "방수": "#A7D8F0", "방화": "#E99AAA", "방화방수": "#F28C52",
  "일반": "#B7B7B7", "전방수": "#F4D06F", "차음": "#D96C32",
};
export function boardColor(kind: string) {return boardColors[kind.replace(/[\s/]/g, "")] ?? "#D5DCE3";}
export function displayStudGroup(group: string) {return group.replace(/개량형/g, "12.5T형");}
export interface StudAsset {
  group: string; spec: string; method: string; svg: string;
  css_width_px: number; css_height_px: number; stroke_px: number;
  shape_height_px?: number; upper_c_height_px?: number;
  slot_center_x_px?: number; board_insert_top_px?: number; board_display_height_px?: number;
}
export function findStudAsset(stud: StudSection | undefined, method?: string): StudAsset | undefined {
  if (!stud) return undefined;
  const group = stud.group.replace("R.STUD", "R-STUD");
  const methodKey = group !== "C-STUD" ? "" : method?.includes("중앙") ? "중앙부 이음" : method?.includes("맞댐") ? "맞댐이음" : (method?.includes("이중") || method?.includes("일면")) ? "더블스터드" : "기본 형상";
  const assets = manifest as StudAsset[];
  return assets.find(a=>a.group===group && a.spec===stud.name && a.method===methodKey);
}
