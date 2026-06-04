"""KDS 지진계수 산정 유틸리티."""

from __future__ import annotations


SITE_CLASSES = ("S1", "S2", "S3", "S4", "S5")
FA_TABLE: dict[str, tuple[float, float, float]] = {
  "S1": (1.12, 1.12, 1.12),
  "S2": (1.4, 1.4, 1.3),
  "S3": (1.7, 1.5, 1.3),
  "S4": (1.6, 1.4, 1.2),
  "S5": (1.8, 1.3, 1.3),
}
S_POINTS = (0.1, 0.2, 0.3)


def calculate_fa(
  site_class: str,
  effective_ground_acceleration: float,
  s5_bedrock_depth_unknown: bool = False,
) -> float:
  """KDS 41 17 00 표 4.2-1에 따라 단주기 지반증폭계수 Fa를 계산한다."""
  normalized_site_class = site_class.upper()
  if normalized_site_class not in FA_TABLE:
    raise ValueError(f"자동 Fa 산정 대상이 아닌 지반등급입니다: {site_class}")
  if effective_ground_acceleration <= 0:
    raise ValueError("유효지반가속도 S는 0보다 커야 합니다.")

  values = FA_TABLE[normalized_site_class]
  if effective_ground_acceleration <= S_POINTS[0]:
    fa = values[0]
  elif effective_ground_acceleration >= S_POINTS[-1]:
    fa = values[-1]
  else:
    fa = values[-1]
    for index in range(len(S_POINTS) - 1):
      left_s = S_POINTS[index]
      right_s = S_POINTS[index + 1]
      if left_s <= effective_ground_acceleration <= right_s:
        ratio = (effective_ground_acceleration - left_s) / (right_s - left_s)
        fa = values[index] + ratio * (values[index + 1] - values[index])
        break

  if normalized_site_class == "S5" and s5_bedrock_depth_unknown:
    return fa * 1.1
  return fa
