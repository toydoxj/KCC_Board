"""계산엔진 기본 상수."""

STUD_ELASTIC_MODULUS = 210000.0
# 스터드 강재 항복강도 Fy (1차 심사의견 반영: 275 → 295 MPa)
STUD_YIELD_STRENGTH = 295.0
STEEL_DENSITY_KG_M3 = 7800.0
GRAVITY = 9.81
DEFAULT_OMEGA = 1.5
DEFAULT_LIVE_LOAD_KN_M2 = 0.25
DEFAULT_HORIZONTAL_LOAD_KG_M2 = DEFAULT_LIVE_LOAD_KN_M2 * 1000.0 / GRAVITY
DEFAULT_DEFLECTION_LIMIT_DENOM = 240
DEFAULT_ANCHOR_CAPACITY_KN = 0.4
DEFAULT_ANCHOR_SPACING_MM = 450.0
ANCHOR_SPACING_INCREMENT_MM = 50.0
ANCHOR_SPACING_MIN_MM = 150.0
ANCHOR_SPACING_MAX_MM = 600.0

BOARD_YIELD_RATIO_FROM_FRACTURE = 0.6
# 피스(볼트) 전단강도 Fv = 0.6 × Fy (전단항복비, EN 1993-1-8 계열)
BOLT_SHEAR_TO_YIELD_RATIO = 0.6

# KDS 41 10 15 허용응력설계 하중조합 (D + L, D + 0.7E, D + 0.75L + 0.75(0.7E))
ASD_SEISMIC_FACTOR = 0.7
ASD_COMBINED_LIVE_FACTOR = 0.75
ASD_COMBINED_SEISMIC_FACTOR = 0.75

# 비구조요소 지진력 계수: Fp = 0.48 × SDS × Ip × W (= 0.4·ap·(1+2z/h)/Rp, ap=1.0, z/h=1, Rp=2.5)
SEISMIC_FP_COEFFICIENT = 0.48

# 피스 인장(면외 이탈) 검토 — AISI S100-16 J4.4
STUD_TENSILE_STRENGTH = 400.0  # 스터드 Fu (MPa), 1차 심사의견 B-8
SCREW_PULLOUT_COEFFICIENT = 0.85  # Eq. J4.4.1-1: Pnot = 0.85·tc·d·Fu2
SCREW_TENSION_OMEGA = 3.0  # J4 Ω (ASD)
# 석고보드 풀스루 공칭강도(N/개). 참고값: ASTM C1396 nail pull 최소값 12.7mm 77 lbf ≈ 343 N
# (못 기준 — KCC 피스·보드 시험값 확보 전 잠정값, 확인 필요)
DEFAULT_SCREW_PULL_THROUGH_NOMINAL_N = 343.0

# 석고보드–스터드 피스 1개당 극한 전단하중(No.6 피스 ≈ φ3.5) — AISI S240-20 해설 Table C-B3.2-1
# (Miller 1989, Lee 1995 시험 평균). (보드 두께 mm, 극한하중 N)
GYPSUM_SCREW_ULTIMATE_SHEAR_N = ((12.7, 516.0), (15.9, 605.0))
# 동 표의 설계강도 = 극한 / 2.0. 휨 Ω 1.5와 합하여 피스에 실질 Ω ≈ 3.0(AISI S100-16 J4 수준) 확보
GYPSUM_SCREW_STRENGTH_DIVISOR = 2.0
# CH·I-STUD 고정 후면 보드 피스 체결(가정): 간격 300 mm, 피치당 2개
FIXED_REAR_BOARD_SCREW_PITCH_MM = 300.0
FIXED_REAR_BOARD_SCREW_COUNT = 2.0

# 피스 활용도 기준 단방향 강성 보정 (E-8): I = R·Ieff,raw·min[1, (u/u_ref)^(1−m)]
# 시험 기준 피스 전단 대리값: 스터드 1개당 지점 전단력 V_ref = P·a/L (P = 306 kgf, a = 1,500, L = 2,400 mm)
STIFFNESS_REF_SUPPORT_SHEAR_N = 306.0 * 9.81 * 1500.0 / 2400.0
# 시험 피스 간격(외곽/중간/내측, mm) — u/u_ref에 피치비로 반영
STIFFNESS_REF_SCREW_PITCH_MM = (600.0, 300.0, 300.0)
