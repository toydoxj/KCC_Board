# 기술인증 2차 심사의견 반영 — 변경 내역 (2026-11-05)

브랜치: `fix/review-round2` (기준: main 47f9dc6, v0.7.4 → v0.8.0)

답변서(기술인증_2차심사의견_답변서.docx)의 조치 내용과 1:1 대응한다. 결과(판정)에 영향하는 변경은 D-2 z/h 하나이며, 기본값 z/h = 1.0에서 기존 결과는 변하지 않는다.

## 1. 변경 항목

| 의견 ID | 커밋 | 종전 | 수정 | 주요 파일 |
|---|---|---|---|---|
| F-1 | 546b6f4 | 스터드 간격 0 초과면 허용 | 사용자 정의 150~600 mm. 범위 밖은 엔진 ValueError("스터드 간격은 150~600 mm 범위여야 합니다"), 화면 zod·input min/max, 안내 helper | calculator.py `_validate_stud_spacing`, constants.py, page.tsx, input-workspace.tsx |
| F-2 | d1a8b0e | "본 결과는 전체 석고보드 구성에 대한 실험 검증값이 아니며 …" | "[주의] 본 결과는 이론 계산값임. … 11종 시험 시편 구성과 시험 높이 2.4 m에 한정 … 외삽값 … η·R 수치 적정성은 기술인증 범위 외" | result-notice.ts, user_manual.md |
| A-1 | d1a8b0e | 시험 구성 일치 여부 표시 없음 | 엔진이 입력 구성을 시험 시편 11종과 대조. 일치 시 "입력 구성은 시험 시편 No.{n}(높이 2.4 m)와 일치함", 불일치 시 "… 일치하지 않음 — 이론 산정값 (차이: …)" 배지(결과 화면·요약·상세, 내진·비내진) | stud_method.json `tested_configurations`, repository.py(schema 8), calculator.py `_tested_configuration_match`, schemas.py, result-notices.tsx |
| B-2 | c33e0d7 | Step 04 입력 설명 없음 | 현장 높이·활하중·처짐한계·연직하중·S·지반등급·S5 110%·Ip helper와 라벨 툴팁, Fp 산정식 요약 1행. 출처 미확인 항목은 코드 주석만 | input-workspace.tsx, field.tsx, user_manual.md §5.4·§5.5 |
| D-2 | b9bffbb | Fp = 0.48·SDS·Ip·Wp 고정 | Fp = 0.4·ap·SDS·Ip·Wp·(1+2z/h)/Rp (ap 1.0, Rp 2.5), 계수 0.3~1.6. z/h 선택 입력(기본 1.0 → 0.48). 모멘트·피스 인장 경로 공통 `_fp_coefficient`. 계산서 Fp 산정 행(ap, Rp, z/h, 계수, 상·하한). 지지조건 적용범위 문구 | constants.py, models.py, calculator.py, schemas.py, page.tsx, calculation-report.tsx, summary-report.tsx, var_formula_spec.md, PRD.md OI-02 |
| D-1 | e82fdd3 | "런너 고정못 성능 (kN/개)" | "런너 고정못 허용내력 (제조사 설계값, kN/개)", 시험성적서 기준 안내, 선택 입력 "허용내력 출처" → 계산서 입력조건 표("—" 미입력), 검증 범위 문구 | models.py `anchor_capacity_source`, schemas.py, input-workspace.tsx, calculation-report.tsx, summary-report.tsx |
| E-3 | 01bba36, 89ce233 | API 포트 8000 고정, 종료 시 `kill()`만 | OS 할당 동적 포트(최대 3회 재시도), preload `getApiBaseUrl`, `taskkill /PID /T /F`, 잔존 `kcc-board-api.exe` 감지·정리, 부모 PID 감시(ctypes, 의존성 추가 없음), 오류 문구 개정, 매뉴얼 §8 문제해결 | main.cjs, preload.cjs, api.ts, electron_api.py, user_manual.md §8, electron_distribution.md |
| E-2, B-3 | 5e80d6f | "KCC Board 구조검토 프로그램" 등 제목 혼용 | "경량철골 스터드와 석고보드의 부분합성을 고려한 칸막이벽체 허용높이 산정 프로그램"(영문 병기 KCC Board). 타이틀바, Help → 프로그램 정보, 계산서 머리글, 매뉴얼 표지. productName "KCC Board" 유지 | package.json `programTitle`, app-info.ts, layout.tsx, main.cjs, 보고서 컴포넌트 |
| 마감 | (본 커밋) | 0.7.4 | 0.8.0 (renderer package.json·lock, pyproject.toml), 본 문서, CODEX.md §6·§9 | — |

## 2. 판정 영향

| 항목 | 영향 |
|---|---|
| z/h = 1.0(기본) | 없음. 계수 0.48과 비트 단위로 같음(12자리 반올림). 골든 cases.json·requested_shape_cases.json 전부 통과 |
| z/h < 1.0 | Fp·지진모멘트·앵커 반력·피스 인장 지진항이 계수비만큼 감소(z/h = 0.5 → 0.32/0.48). z/h < 0.4375는 하한 0.3 |
| 스터드 간격 150~600 mm 밖 | 계산 거부(종전에는 계산) |
| 그 외(F-2, A-1, B-2, D-1, E-3, E-2) | 없음(표시·입력·배포) |

## 3. 시험 시편 구성 대조 규칙

- 단일 출처: `data/seed/stud_method.json`의 `tested_configurations`(11건, 시험 높이 2,400 mm). R 보정 시편 입력과 일치 여부를 테스트로 검사한다.
- 대조 항목 키: `stud_type`, `stud_spec`, `stud_method`(C-STUD만, 미입력은 기본, "중앙부연결"은 중앙부 이음과 같음), `board_kind`, `board_thickness`, `board_layers`(면별 다중집합 비교), `spacing`.
- 기준 시편: 형식 일치 → 규격 일치 → 차이 항목 수 → 시편 번호 순으로 가장 가까운 시편.
- 출력: intermediate `tested_configuration_match`(0/1), `matched_specimen_no`(불일치 0), `closest_specimen_no`, `tested_height_mm`, 응답 최상위 `tested_configuration_mismatch_fields`.

## 4. 시험 결과

| 항목 | 결과 |
|---|---|
| `python -m pytest` | 305 passed, 432 subtests passed |
| 골든 회귀(상대오차 ≤ 0.1%) | 통과(cases.json, requested_shape_cases.json, latest_github_reference.json) |
| 신규 `tests/test_review_round2.py` | 51건 통과 |
| `npm run build` / `tsc --noEmit` | 성공 |
| `npm run dist` | `KCC Board Setup 0.8.0.exe` 생성 |
| E-3 설치본 검증 | 3건 적합(electron_distribution.md 검증 기록) |

## 5. 확인 필요(임의 확정 금지, 코드 주석 유지)

- KDS 41 17 00 18장 비구조요소 Fp 식·상하한 조항 번호, ap = 1.0·Rp = 2.5 표 번호 (OI-02)
- 활하중 프리셋 0.36·0.48 kN/m² 출처
- ASTM C754 최대 스터드 간격 조항

## 6. 알려진 제한·후속 확인

- 잔존 백엔드 정리는 이름(`/IM`) 기준 — 같은 PC 다른 계정의 KCC Board 백엔드도 종료될 수 있음.
- 정상 종료(창 닫기) 경로의 `taskkill /PID /T /F`는 수동 확인 대상.
- 매뉴얼 캡처 이미지는 v0.7.3 화면 — 신규 입력(z/h, 고정못 출처, 배지) 캡처 갱신 필요.
- 프롬프트의 "매뉴얼 §4 입력 항목 표"·"§8 오류 메시지 표"는 현행 매뉴얼 번호로 §5(입력 항목)·§8(문제해결)에 반영함.
