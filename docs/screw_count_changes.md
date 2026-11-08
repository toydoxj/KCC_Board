# 피스 개수 규칙 변경 내역 (v0.9.1, 2026-11-08)

## 1. 변경 요지 (사용자 결정 2026-11-08)

| 항목 | 종전 | 변경 | 상수 |
|---|---|---|---|
| CH·I-STUD 고정 후면 보드 피스 | 300 mm / 피치당 2개 | 300 mm / **피치당 4개** | `FIXED_REAR_BOARD_SCREW_COUNT` 2.0 → 4.0 |
| 일면마감 1P 단독 구성 피스 | 1P 내측 규칙 600 mm / 1개 | 표준 **300 mm / 피치당 2개** | `ONE_SIDED_SINGLE_PLY_SCREW_PITCH_MM` 300, `ONE_SIDED_SINGLE_PLY_SCREW_COUNT` 2 (신설) |
| 양면 1P 구성 | 300 mm / 1개 | 변경 없음 | `BILATERAL_SINGLE_PLY_SCREW_PITCH_MM` |
| 다겹 구성(2P·3P, 일면 2P·3P 포함) | 1-3-5 누계(1P 600/1, 2P 300/2, 3P 300/2) | 변경 없음 | `STANDARD_SCREW_*` |

- "일면마감 1P 단독 구성" = 한 면에만 보드 1장, 반대 면 보드 없음. CH·I-STUD는 고정 후면 보드가 있어 해당 없음(양면 1P 규칙).
- 1P 간격은 입력값을 그대로 쓰고, 300 mm 외 입력은 결과 안내(notices)로 경고만 함(판정 불변, 심사의견 F-4 방식).
- UI: 일면마감 1P 구성에서 1P 나사못 간격 기본값이 300 mm로 바뀜(양면 1P와 같은 단일층 모드). CH 구성 안내 문구에 피스 300 mm·4개 고정 명시.

## 2. 파생 변경 — 시험 보정 상수 재산정 (`backend/tools/r_calibration.py --check` 일치)

고정 후면 보드 피스가 4개가 되면 CH·I-STUD의 Ieff,raw(2,400)·η·Mn이 바뀌므로 E-11·E-8 보정 상수를 시험 엑셀(`wall_test_analysis_20260724.xlsx`)로 재산정함.

| 형식 | R (`EFFECTIVE_INERTIA_CORRECTION_BY_TYPE`) | V* (`STIFFNESS_REF_SUPPORT_SHEAR_N_BY_TYPE`) | M* (`STIFFNESS_REF_MOMENT_KNM_BY_TYPE`) |
|---|---|---|---|
| CH-STUD(개량형 포함) | 0.79 → **0.66** | 800.8 (불변) | 0.732 → **0.789** |
| I-STUD | 1.00 (불변, 상한) | 826.9 → **949.2** | 1.690 → **0.890** |

다른 형식(C·HR·MP·RV·T.silent·R)은 불변.

## 3. 참조값 갱신 (사용자 승인 2026-11-08)

| 참조 | 케이스 | 종전 | 갱신 |
|---|---|---|---|
| `tests/golden/requested_shape_cases.json` | 05 CH 75CHS-08 | 6,200 / Ieff,raw 525,150 / R 0.79 | 6,200 / 614,681 / 0.66 |
| 〃 | 11 I-STUD 75-06 | 6,300 / 447,575 / Mu 1.212 | 6,750 / 517,516 / 1.392 |
| `tests/test_stiffness_moment_basis.py` SPECIMEN_MAX_HEIGHT_MM | 11 I-STUD | 6300 / 5150 / 6300 / 4000 | 6750 / 5150 / 6750 / 4000 |
| `tests/golden/latest_github_reference.json` | CH64 | 5,300 | 5,200 |
| 〃 | CH75 | 5,900 | 5,800 |
| 〃 | CH12_5_64 | 5,600 | 5,250 |
| 〃 | I75_06 | 6,050 | 6,350 |
| 〃 | I75_08 | 6,600 | 6,950 |

- `latest_github_reference.json`의 η·Ieff·Mn(3,000 mm)도 함께 갱신. 내진 `with_runner_mm`은 상한 비교용이라 유지.
- 골든 `tests/golden/cases.json`(C-STUD 3건)은 영향 없음.
- CH: Mn 증가에도 R 저하로 최대높이 100~350 mm 감소. I-STUD: 300~450 mm 증가.

## 4. 검증

| 항목 | 결과 |
|---|---|
| `pytest` | 346 passed, 465 subtests passed |
| `r_calibration.py --check` | constants 값과 일치 |
| `tsc --noEmit` / `npm run build` | 통과 |
| Codex 커밋 전 리뷰 | major 1(계산서 1번 내측 피스 개수가 1개로 표기됨 → 일면마감 1P 단독 구성은 2개 표기하도록 `createReportData` 수정), minor 1(CH·I-STUD 전면 0장에서 일면마감 안내 오표시 → 고정 후면 보드 형식 제외) 반영. critical 없음 |

## 5. 변경 파일

`backend/engine/constants.py`, `backend/engine/calculator.py`, `renderer/src/app/page.tsx`, `renderer/src/components/input-workspace.tsx`, `tests/test_single_ply_pitch.py`, `tests/test_golden_cases.py`, `tests/test_integrated_customizations.py`, `tests/test_stiffness_moment_basis.py`, `tests/golden/requested_shape_cases.json`, `tests/golden/latest_github_reference.json`, `docs/var_formula_spec.md`, `docs/user_manual.md`, 버전 0.9.0 → 0.9.1.

## 6. 확인 필요

- 동양구조 NC 재검토서 중 CH-STUD 케이스(R1-3·R1-4)는 본 변경으로 결과가 달라지므로 재출력 필요.
- I-STUD M* 0.890은 시험 최대모멘트(1.690) 대비 크게 낮아짐 — 하중 수준 보정 k_L이 더 이른 모멘트부터 적용됨. 시험 M–δ 곡선 재확인 권장.
