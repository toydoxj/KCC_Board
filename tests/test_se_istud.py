"""I-STUD 유효단면계수 Se(2겹 일체) 산정 도구 회귀 테스트."""

from __future__ import annotations

import unittest
from pathlib import Path

from backend.tools.se_istud import _rho, _slenderness, compute_i_stud_se, compute_seed_i_studs


ROOT = Path(__file__).resolve().parents[1]


class IStudEffectiveSectionTest(unittest.TestCase):
  def test_seed_se_matches_tool(self) -> None:
    # 시드 Se = 도구 산정값(일체, 반올림) — Se 변경 시 도구로 재산정해야 함
    for item, result in compute_seed_i_studs(ROOT / "data/seed"):
      with self.subTest(spec=item["name"]):
        self.assertEqual(item["Se"], round(result.Se))
        self.assertEqual(item["Se_basis_Fy_MPa"], 295)
        self.assertLessEqual(abs(result.Ix_gross / item["Ix"] - 1.0), 1e-3)
        self.assertLess(result.Se, item["Sx"])

  def test_independent_mode_reproduces_previous_lower_bound(self) -> None:
    # 종전 DB(2겹 독립 하한) Se를 1% 이내로 재현 — 모델 가정 검증
    previous = {("75-06", 75.0, 0.6): 1947, ("102-06", 102.0, 0.6): 2651, ("75-08", 75.0, 0.8): 3081,
                ("92-08", 92.0, 0.8): 4032, ("102-08", 102.0, 0.8): 4590, ("127-08", 127.0, 0.8): 5672,
                ("152-08", 152.0, 0.8): 6752}
    for (name, H, t), se in previous.items():
      with self.subTest(spec=name):
        result = compute_i_stud_se(name, H, 40.0, t, 295.0, "independent")
        self.assertLessEqual(abs(result.Se / se - 1.0), 0.01)

  def test_effective_width_factor_boundaries(self) -> None:
    # App.1 Eq. 1.1-2: λ ≤ 0.673 → ρ = 1, λ = 1.0 → ρ = 0.78
    self.assertEqual(_rho(0.673), 1.0)
    self.assertLess(_rho(0.674), 1.0)
    self.assertAlmostEqual(_rho(1.0), 0.78)
    # 수계산: w 16.7, t 0.6, f 295, E 210000, k 0.43 → λ = 1.6043 × 27.833 × 0.037480 = 1.6736
    self.assertAlmostEqual(_slenderness(0.43, 16.7, 0.6, 295.0, 210000.0), 1.6736, places=3)

  def test_web_depth_limit_rejected(self) -> None:
    # h0/b0 > 4 이면 App.1 1.1.2 b2 식 범위 밖 → 예외
    with self.assertRaises(ValueError):
      compute_i_stud_se("H200", 200.0, 40.0, 0.8, 295.0)

  def test_unknown_ply_mode_rejected(self) -> None:
    with self.assertRaises(ValueError):
      compute_i_stud_se("75-06", 75.0, 40.0, 0.6, 295.0, "bonded")  # type: ignore[arg-type]

  def test_integral_exceeds_independent(self) -> None:
    integral = compute_i_stud_se("75-06", 75.0, 40.0, 0.6, 295.0, "integral")
    independent = compute_i_stud_se("75-06", 75.0, 40.0, 0.6, 295.0, "independent")
    self.assertGreater(integral.Se, independent.Se)


if __name__ == "__main__":
  unittest.main()
