"""KDS 지반증폭계수 산정 테스트."""

from __future__ import annotations

import unittest

from backend.engine.seismic import calculate_fa


class SeismicCoefficientTest(unittest.TestCase):
  def test_calculate_fa_interpolates_by_effective_ground_acceleration(self) -> None:
    self.assertAlmostEqual(calculate_fa("S2", 0.22), 1.38)
    self.assertAlmostEqual(calculate_fa("S3", 0.25), 1.4)

  def test_calculate_fa_preserves_current_default_value_for_s5(self) -> None:
    self.assertAlmostEqual(calculate_fa("S5", 0.22), 1.3)

  def test_calculate_fa_applies_s5_unknown_bedrock_depth_factor(self) -> None:
    self.assertAlmostEqual(calculate_fa("S5", 0.22, s5_bedrock_depth_unknown=True), 1.43)
    self.assertAlmostEqual(calculate_fa("S4", 0.22, s5_bedrock_depth_unknown=True), 1.36)

  def test_unknown_site_class_is_rejected(self) -> None:
    with self.assertRaises(ValueError):
      calculate_fa("S6", 0.22)


if __name__ == "__main__":
  unittest.main()
