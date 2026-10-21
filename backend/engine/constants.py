"""계산엔진 기본 상수."""

STUD_ELASTIC_MODULUS = 210000.0
# 스터드 강재 Fy·Fu는 자재 DB(data/seed/stud_steel.json)로 이관(심사의견 B-8, 2026-10-20)
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

# 석고보드 항복비 Fy/Fu 기본값 — 아래 표에 없는 보드(미등재)에만 적용
BOARD_YIELD_RATIO_FROM_FRACTURE = 0.6
# 석고보드 종류·두께별 항복비 Fy/Fu = Py/Pu (1차 심사의견 B-3, 2026-10).
# 시험: KCC 휨-변위 시험 41개 시험체, 초기 선형 회귀 직선 대비 하중 5% 저하점(비례한도)의 평균.
# 준용: 미시험 종류는 심재 계열·단위중량이 같은(유사한) 시험 보드 값을 적용함.
# 값: (Fy/Fu, 근거)
BOARD_YIELD_RATIO_BY_BOARD: dict[tuple[str, float], tuple[float, str]] = {
  ("일반", 9.5): (0.52, "시험"),
  ("일반", 12.5): (0.55, "시험"),
  ("일반", 15.0): (0.59, "시험"),
  ("방화", 12.5): (0.56, "시험"),
  ("방화", 15.0): (0.70, "시험"),
  ("방화", 19.0): (0.65, "시험"),
  ("방화", 25.0): (0.80, "시험"),
  ("고강도일반", 12.5): (0.61, "시험"),
  ("전방수", 12.5): (0.48, "시험"),
  ("전방수", 15.0): (0.38, "시험"),
  ("방수", 9.5): (0.52, "준용: 일반 9.5"),
  ("방수", 12.5): (0.55, "준용: 일반 12.5"),
  ("방균", 9.5): (0.52, "준용: 일반 9.5"),
  ("방균", 12.5): (0.55, "준용: 일반 12.5"),
  ("방화방수", 12.5): (0.56, "준용: 방화 12.5"),
  ("방화방수", 15.0): (0.70, "준용: 방화 15"),
  ("방화방수", 19.0): (0.65, "준용: 방화 19"),
  ("차음", 9.5): (0.56, "준용: 방화 12.5"),
  ("차음", 12.5): (0.56, "준용: 방화 12.5"),
  ("고강도일반", 15.0): (0.61, "준용: 고강도일반 12.5"),
  ("고강도전방수", 12.5): (0.61, "준용: 고강도일반 12.5"),
}
# 피스(볼트) 전단강도 Fv = 0.6 × Fy (전단항복비, EN 1993-1-8 계열)
BOLT_SHEAR_TO_YIELD_RATIO = 0.6

# KDS 41 10 15 허용응력설계 하중조합 (D + L, D + 0.7E, D + 0.75L + 0.75(0.7E))
ASD_SEISMIC_FACTOR = 0.7
ASD_COMBINED_LIVE_FACTOR = 0.75
ASD_COMBINED_SEISMIC_FACTOR = 0.75

# 비구조요소 지진력 계수: Fp = 0.48 × SDS × Ip × W (= 0.4·ap·(1+2z/h)/Rp, ap=1.0, z/h=1, Rp=2.5)
SEISMIC_FP_COEFFICIENT = 0.48

# 피스 인장(면외 이탈) 검토 — AISI S100-16 J4.4
SCREW_PULLOUT_COEFFICIENT = 0.85  # Eq. J4.4.1-1: Pnot = 0.85·tc·d·Fu2
SCREW_TENSION_OMEGA = 3.0  # J4 Ω (ASD)
# 피스 전단 — 스터드(강재)측 한계, AISI S100-16 J4.3.1 (t2/t1 ≤ 1.0, t2 = 스터드 두께, Fu2 = 스터드 Fu)
SCREW_TILTING_COEFFICIENT = 4.2  # Eq. J4.3.1-1: Pns = 4.2·(t2³·d)^0.5·Fu2
SCREW_STUD_BEARING_COEFFICIENT = 2.7  # Eq. J4.3.1-3: Pns = 2.7·t2·d·Fu2
SCREW_SHEAR_OMEGA = 3.0  # J4 Ω (ASD). 강성(η)·강도(Mn) 경로 모두 적용(사용자 결정, 심사의견 A-4·D-7)
# 석고보드 풀스루 공칭강도(N/개). 참고값: ASTM C1396 nail pull 최소값 12.7mm 77 lbf ≈ 343 N
# (못 기준 참고값을 기본값으로 적용 — 사용자 확정 2026-10-21)
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
# 시험 피스 간격(엔진 bolt.pitch 순서: 3번 외측 / 2번 중간 / 1번 내측, mm) — u/u_ref에 피치비로 반영
# 엑셀 VAR. C32:C34 = [1P 600, 2P 300, 3P 300], 1P = 내측(스터드 인접)
STIFFNESS_REF_SCREW_PITCH_MM = (300.0, 300.0, 600.0)

# 표준 피스 간격(3번 외측 / 2번 중간 / 1번 내측, mm). 1P(내측)는 스터드에 가장 가까운 층.
# 이와 다른 입력은 결과 안내(notices)로 경고만 하고 판정에는 반영하지 않음 (심사의견 F-4)
STANDARD_SCREW_PITCH_MM = (300.0, 300.0, 600.0)
# 표준 피치당 연결 피스 개수(같은 순서: 3번 외측 / 2번 중간 / 1번 내측). 누계 1-3-5개 = 층별 1·2·2개
STANDARD_SCREW_COUNT = (2.0, 2.0, 1.0)
BOARD_ORDER_LABELS = {1: "1번(내측)", 2: "2번(중간)", 3: "3번(외측)"}
