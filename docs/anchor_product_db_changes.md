# 런너 고정 앵커 제품 DB 도입 — 변경 내역 (2026-11-08)

브랜치: `feat/anchor-product-db` (기준: main 0b2970c, v0.8.0 → v0.9.0 → v0.9.3). ADR-002(DevVault). v0.9.3 결정 반영은 §7.

내진 런너 고정못 허용내력을 제품 DB에서 자동 입력한다. 제품 + 매입깊이(hET) + 콘크리트 강도(f'c)를 고르면 허용 전단값이 기존 `anchor_capacity_kN`에 들어가고, 입력 화면과 계산서에 조건·출처가 표기된다. 사용자 정의(직접 입력) 경로는 그대로 유지한다. 엔진 `calculate_wall_check`와 판정 로직은 변경하지 않았다.

## 1. 변경 항목 (커밋 7건)

| 작업 | 커밋 | 내용 | 주요 파일 |
|---|---|---|---|
| 1 시드 | 3664400 | `anchor_product.json`(제품 12 + custom 1, 허용하중 74행, `seismic_shear_cap_N` 400) + 무결성 테스트 7건 | data/seed/anchor_product.json, tests/test_anchor_product.py |
| 2 모델·저장소 | 78463ea | `AnchorLoadRow`·`AnchorProduct`·`AnchorSeismicCap` 모델, Repository Protocol 3메서드, SQLite schema 8→9(`anchor_product`·`anchor_load_row`, 구 DB 이관·롤백), 조회 함수 `resolve_anchor_capacity`·`resolve_request_anchor` | models.py, repository.py, engine/anchor.py, tests/test_anchor_resolution.py |
| 3 API | de77478 | `GET /api/db/anchor-products`, `/api/check` 요청 4필드(`anchor_product_id`·`anchor_embedment_mm`·`anchor_concrete_fc_MPa`·`anchor_apply_seismic_cap`) → 조회 후 `anchor_capacity_kN` 덮어쓰기, 응답 `anchor_product_summary`·`anchor_capacity_overridden`·intermediate 5키 | schemas.py, main.py, tests/test_api_anchor.py |
| 4 입력 UI | 48f3ee7 | 제품(optgroup) → hET → f'c → 내진 상한 체크 → 허용내력(읽기 전용/사용자 정의) → 출처 → 간격, 참조 카드, 최소 간격 경고. 기본 hilti_x_u / 22 mm → 0.3 kN 자동 입력 | page.tsx, input-workspace.tsx, lib/anchor.ts, lib/api.ts, globals.css |
| 5 계산서 | f2354c3 | 검토 조건에 고정못 제품·조회 조건·허용 전단/인장·기준·출처 행, 반력 산정 각주, 참고 부록 "선택 앵커 제품의 허용하중 표"(선택 행 강조), 요약페이지 동일 행 | calculation-report.tsx, summary-report.tsx, page.tsx |
| 6 문서 | 8671ee3 | 매뉴얼 §5.3·§8.1·§9·부록 A, var_formula_spec §9.1, CODEX §6, PRD(스키마·API·OI-10) | docs/*, CODEX.md |
| 7 마감 | 36a44b8 | 판정 영향 고정 테스트 4건, 버전 0.9.0, 본 문서 | tests/test_anchor_height_impact.py, package.json·lock, pyproject.toml |
| 리뷰 반영 | (본 커밋) | Codex 커밋 전 리뷰 5건 반영 — ①schema 9 이관 `executescript` 암묵 커밋 → 문장별 `execute`(실패 시 테이블까지 롤백) ②N→kN 반올림 규칙 서버·클라이언트 통일(0.5 올림) ③화면 기본 제품을 카탈로그 `is_default`에서 결정(하드코딩 제거) ④사용자 정의 전환 시 자동 생성 출처만 비움 ⑤`anchor_embedment_mm`·`anchor_concrete_fc_MPa` 유한값 검증(`allow_inf_nan=False`) | repository.py, anchor.py, schemas.py, page.tsx, tests |

## 2. 판정 영향 — 11개 시편 내진 런너 고정못 기준 허용높이

v0.9.0~0.9.2에서는 화면 기본값이 "0.4 kN/개 직접 입력"에서 "기본 제품 Hilti X-U P8, hET 22 mm → 300 N = 0.3 kN/개"로 바뀌었다. **v0.9.3(결정 1, 2026-11-09)에서 기본 매입깊이를 27 mm로 확정**하여 자동 입력값이 0.4 kN/개(v0.8.0 기본값과 동일)가 되었고, 기본 경로의 anchorHeight는 종전과 같다(마지막 열). 아래 표는 `tests/golden/requested_shape_cases.json` 11개 시편을 내진, 고정못 간격 450 mm, 그 외 공통 조건으로 산출한 값이다(`tests/test_anchor_height_impact.py`가 고정). 응력·처짐·피스 인장과 `max_height_mm`는 허용내력에 영향받지 않으므로 변화가 없다.

| No. | 시편 | 종전 anchorH (0.4 kN) | v0.9.0~0.9.2 anchorH (hET 22 → 0.3 kN) | 차이 | 허용 간격 0.4 → 0.3 (mm) | 확정 기본값(hET 27 → 0.4 kN, v0.9.3) |
|---|---|---|---|---|---|---|
| 01 | C-STUD 중앙부이음 50S-45-08, 450, 방화 19T 2P 양면 | 2,600 | 1,950 | −650 | 450 → 350 | 2,600 (종전과 동일) |
| 02 | C-STUD 기본 50S-45-08, 450, 전면 방화 19T 2P | 4,100 | 3,050 | −1,050 | 750 → 550 | 4,100 (종전과 동일) |
| 03 | C-STUD 맞댐이음 50S-45-08, 450, 방화 19T 2P 양면 | 2,600 | 1,950 | −650 | 450 → 350 | 2,600 (종전과 동일) |
| 04 | C-STUD 기본 50S-45-08, 450, 방화 19T 2P 양면 | 2,650 | 2,000 | −650 | 500 → 350 | 2,650 (종전과 동일) |
| 05 | CH-STUD 75CHS-08, 600, 후면 25T 1P + 전면 15T 3P | 2,800 | 2,100 | −700 | 500 → 350 | 2,800 (종전과 동일) |
| 06 | HR-STUD HR-124, 450, 방화 19T 2P 양면 | 2,650 | 1,950 | −700 | 450 → 350 | 2,650 (종전과 동일) |
| 07 | MP-STUD MP-74, 450, 방화 19T 2P 양면 | 2,650 | 2,000 | −650 | 500 → 350 | 2,650 (종전과 동일) |
| 08 | RV-STUD RV-74, 450, 방화 19T 2P 양면 | 2,650 | 2,000 | −650 | 500 → 350 | 2,650 (종전과 동일) |
| 09 | T.silent-STUD 19TH-A-74x45x10x0.5, 450, 방화 19T 2P 양면 | 2,650 | 2,000 | −650 | 500 → 350 | 2,650 (종전과 동일) |
| 10 | R-STUD 75S-45-08, 450, 방화 19T 2P 양면 | 2,650 | 2,000 | −650 | 500 → 350 | 2,650 (종전과 동일) |
| 11 | I-STUD 75-06, 600, 후면 25T 1P + 전면 15T 3P | 2,800 | 2,100 | −700 | 500 → 350 | 2,800 (종전과 동일) |

단위 mm. 런너 고정못 반력은 지진항에 Ω0 = 2.0을 곱하므로 허용내력 25% 감소가 허용높이 약 25% 감소로 나타난다.

| 경로 | 영향 |
|---|---|
| 사용자 정의 + 종전 값 0.4 kN 입력 | 없음(종전과 동일) |
| 기본 제품 그대로 사용 | 위 표. `anchorHeight`·내진 `heightCheck`의 런너 고정못 판정이 보수측으로 이동 |
| ICC-ES 제품 + 내진 상한 적용(기본) | 허용 전단 = min(표 값, 400 N) → 대부분 0.4 kN(종전 기본과 동일) |
| 비내진 | 없음(앵커 항목 미표시·미사용) |
| 골든 회귀 | `cases.json`·`requested_shape_cases.json`·`latest_github_reference.json` 전부 불변 |

## 3. 조회 규칙 요약

| 구분 | 규칙 |
|---|---|
| 제조사 권장하중(rec, f'c 전부 null) | 입력 hET 이하 중 최대 매입깊이 행. 표 최소값 미만이면 `AnchorLookupError` |
| ICC-ES 허용하중(asd) | (hET, f'c) 정확 일치. 보간·외삽 없음 |
| 내진 상한 | 내진 + 적용 체크 + **적용 대상 제품군(`seismic_shear_cap_families` = dx·gx)**일 때 `min(V표, 400 N)`, `anchor_seismic_cap_applied` = 1. screw(콘크리트 스크류)는 비적용(`anchor_seismic_cap_eligible` = 0, 표 값 그대로) — ICC-ES PAF 평가서 §4.1 Item 2가 타정못·가스핀 전용이므로(결정 2, 2026-11-09). 스크류 앵커 내진 적격성은 ACI 318 Ch.17 / KDS 14 20 54 체계로 별도 확인 필요 |
| 사용자 정의 | 조회 안 함. 입력 `anchor_capacity_kN` 그대로 |
| 위치 | 규칙은 `backend/engine/anchor.py`(순수 함수), API 계층이 `anchor_capacity_kN`을 채움. 클라이언트 `renderer/src/lib/anchor.ts`는 참조 카드·자동 입력용 미러이며 판정값은 서버 응답을 따름 |

## 4. 시험 결과

| 항목 | 결과 |
|---|---|
| `python -m pytest` | 358 passed, 478 subtests passed (v0.9.3) |
| 골든 회귀(상대오차 ≤ 0.1%) | 통과, 골든 파일 수정 없음 |
| 신규 테스트 | test_anchor_product 8, test_anchor_resolution 20, test_api_anchor 9, test_anchor_height_impact 6 (v0.9.3 기준) |
| `tsc --noEmit` / `npm run build` | 성공 |
| 브라우저 스모크 | 미실시(개발 PC의 브라우저 확장이 맥북 Chrome에 연결되어 Windows 개발 서버를 볼 수 없었음). 맥북 Electron 배포 후 확인 예정 |

## 5. 확인 필요 (임의 확정 금지, 시드 `_notes`·PRD OI-10)

- Hilti 권장하중(rec)의 콘크리트 안전율 — Data Sheet 미기재
- Hilti X-C 승인번호(Data Sheet 미기재), Simpson ESR-2138 최소 간격·연단 원문
- ICC-ES 400 N 내진 상한의 KDS 41 17 00 비구조요소 대응, 타정못의 KDS 14 20 54 적용 범위
- `default_embedment_mm` — **확정(27 mm, 2026-11-09)**. Hilti X-U·X-C Vrec 0.4 kN(hET ≥ 27 mm)·ICC-ES 내진 상한 400 N과 일치. 런너 0.8~1.0 mm 기준 X-U 32 P8 사용 시 hET ≈ 31 mm
- 국내 제조사 제품 추가(시드 행 추가로 대응)

## 6. 알려진 제한

- 제품 DB 수치는 제조사·ICC-ES 전재값(1 lbf = 4.448 N 환산)이며 국내 인증값이 아니다.
- 매뉴얼 캡처 이미지는 v0.7.3 화면이다. 앵커 제품 선택 UI·참조 카드 캡처 갱신이 필요하다.
- `dev_servers.py` POSIX 전용 문제는 별도 작업 항목(CLAUDE.md §3).

## 7. v0.9.3 결정 반영 (2026-11-09)

검토 완료된 확정값 4건을 반영하였다. 결과(판정)에 영향하는 변경은 결정 1(기본 매입깊이)과 결정 2(스크류 상한 해제) 두 가지이다.

| No | 결정 | 반영 | 변경 파일 |
|---|---|---|---|
| 1 | 기본 제품 Hilti X-U P8 유지, `default_embedment_mm` 22 → **27** → 자동 입력 0.4 kN/개 | 시드 label·_status, 참조 카드 기본값 안내, 정적 폴백 0.4/27, 판정 영향 테스트 재구성(0.4 경로 = v0.8.0 고정, hET 22 → 0.3 경로 보존) | `data/seed/anchor_product.json`, `renderer/src/components/input-workspace.tsx`, `renderer/src/app/page.tsx`, `tests/test_anchor_height_impact.py`, `tests/test_api_anchor.py` |
| 2 | 내진 상한 400 N 적용 대상을 **dx·gx**로 한정, `screw` 비적용 + 별도 안내 | 시드 `seismic_shear_cap_families`, `AnchorSeismicCap.families`, SQLite schema 9 → 10(metadata, 이관·롤백), `resolve_anchor_capacity(cap_families)`·`cap_eligible`, intermediate `anchor_seismic_cap_eligible`, summary 문구, UI 체크박스 비활성·스크류 경고, 계산서·요약 분기 | `backend/engine/{models,repository,anchor}.py`, `backend/api/schemas.py`, `renderer/src/lib/{api,anchor}.ts`, `renderer/src/app/page.tsx`, `renderer/src/components/{input-workspace,calculation-report}.tsx`, 테스트 3파일 |
| 3 | CH 끼움 보드 모델 A안 유지, 용어·문서 정합화 | "피스 300 mm/피치당 4개 체결 상당(등가)" 서술 통일, PRD OI-11 | 렌더러 3파일, `docs/{var_formula_spec,user_manual,screw_count_changes,PRD}.md` |
| 4 | I-STUD M* 0.890 유지, 민감도 표·확인 필요 | `backend/tools/kl_sensitivity.py`(임시 주입, 상수 불변), screw_count_changes §6.1, PRD OI-12 | 도구 1, 문서 2 |
| 5 | 버전 0.9.2 → 0.9.3 | package.json·lock, pyproject.toml, About(동적), 매뉴얼 부록 B(캡처 갱신 목록) | — |

### 7.1 판정 영향

| 경로 | v0.8.0 | v0.9.2 | v0.9.3 | 비고 |
|---|---|---|---|---|
| 기본 제품·기본 매입(내진, 11개 시편 anchorHeight) | 0.4 kN 값(2,600~4,100) | 0.3 kN 값(1,950~3,050) | 0.4 kN 값(= v0.8.0) | 결정 1. §2 표 마지막 열 |
| ICC-ES PAF 제품(dx·gx) + 내진 | — | min(표, 400) | min(표, 400) | 불변 |
| 콘크리트 스크류(screw) + 내진 | — | 400 N | 표 값(cap 비적용) | 결정 2. 허용내력 증가 → anchorHeight 증가. 예: Titen 1/4 hET 38·f'c 27.6 → 1,779 N |
| CH 구성 허용높이 | 종전 | R 0.66 | R 0.66(불변) | 결정 3, 문구만 |
| I-STUD 허용높이 | — | M* 0.890 | M* 0.890(불변) | 결정 4, 민감도 기록만 |
| 골든 3파일 | — | 불변 | 불변 | `git diff --stat tests/golden` 비어 있음 |
