<!-- 생성: 2026-10-21 | 대상: 1차 심사의견 반영 2차 — 로컬 동기화·검증 및 답변서 약속 항목 구현 -->

# KCC_Board 1차 심사의견 반영 — 로컬 동기화·검증 및 후속 구현 요청

## 목표
1. 클라우드 세션에서 작성한 미푸시 커밋 4건을 로컬에 반영하고, Windows에서 검증한 뒤 원격에 푸시한다.
2. 답변서(초안 13차)에서 "수정함"으로 답변했지만 아직 구현하지 않은 항목 중 사용자가 선택한 1건을 구현한다.

## 현재 상태 (요약)
- 브랜치 `fix/review-round1-strength`. 원격(origin)은 `e75d8c2`까지만 반영됨
- 미푸시 커밋 4건 (번들 `review-round1-f.bundle`, 마지막은 본 문서)
  - `ba7892e` 피스 전단 강성·강도 분리: Mn에 AISI S240-20 해설 C-B3.2-1 극한/2.0 상한, CH·I 후면 보드 피스 체결(300 mm, 2개)
  - `6ca754a` 단방향 강성 보정 (E-8): `I = max[R·I_raw·min{1,(u/u_ref)^(1−m)}, I_s]`
  - `cfa27c0` 석고보드 항복비 (B-3): Fy = Fu × 종류·두께별 실측 Py/Pu(`constants.BOARD_YIELD_RATIO_BY_BOARD`, 미시험 종류는 유사 보드 준용, 미등재 0.6), SQLite schema 6, R 재보정(C 0.72, 중앙부 0.36, CH 0.67, T.silent 0.46, R 0.27, I 0.90, HR 0.73, RV 0.44, MP 0.43), 골든값 재산정, API·계산서에 `yield_ratio`·근거 표시
- 클라우드(Linux) 검증: pytest 54 passed + 57 subtests, `npm run build` 성공
- 변경 내역: `docs/review_round1_changes.md` §1-2~1-4

## 작업 범위
### 1단계 (필수, 선행)
1. 저장소 루트에 `review-round1-f.bundle`을 두고 실행(다른 브랜치로 체크아웃한 상태에서 fetch):
   ```powershell
   git fetch .\review-round1-f.bundle fix/review-round1-strength:fix/review-round1-strength
   git checkout fix/review-round1-strength
   git log --oneline -5   # HEAD(NEXT_PROMPT), cfa27c0, 6ca754a, ba7892e, e75d8c2 확인
   ```
2. 자재 DB 재초기화: `.\.venv-win\Scripts\python.exe -m backend.tools.init_db`
3. `.\.venv-win\Scripts\python.exe -m pytest -v` → 54 passed(+57 subtests) 확인
4. `cd renderer; npm run build` 성공 확인
5. 이상 없으면 `git push origin fix/review-round1-strength`. main 병합·PR은 사용자 확인 후 진행
6. bundle 파일은 커밋하지 않는다.

### 2단계 (착수 전 사용자에게 선택 질문, 1건만 진행)
| 후보 | 관련 의견 | 내용 | 비고 |
|---|---|---|---|
| A | A-4, D-7 | 전단 경로 min(피스 전단, 보드 지압)에 tilting(AISI S100-16 Eq. J4.3.1-1)과 스터드 지압(Eq. J4.3.1-3) 추가 | **Ω를 공칭값(1.0)으로 둘지 3.0으로 둘지 사용자 결정 필요**. 공칭이면 결과 불변, Ω 3.0이면 t0.6 형식(MP·RV·T.silent·I 75-06) 허용높이 300~500 mm 감소. 골든값 재산정 필요 |
| B | E-9 | 중립축 위치 검사: NA가 스터드 범위(0~H) 밖이면 경고하고 누적 방향 재설정 | 결과 화면·계산서 경고 |
| C | D-2, F-4 | 결과 화면에 문구 표시: "본 결과는 전체 석고보드 구성에 대한 실험 검증값이 아니며, 석고보드·스터드 및 합성 효과에 대한 실험 물성치를 바탕으로 이론 계산식에 따라 산정한 값임". 표준 외 피스 간격(1P 600 / 2P 300 mm 외) 입력 시 경고 | 렌더러 위주. 판정 불변 |
| D | D-5 | 기호 `Paxial`을 혼동 없는 명칭으로 변경(API·계산서·문서) | 명칭은 사용자 확인. API 필드명 변경 시 호환성 검토 |
| E | B-8 | 스터드 강종별 Fy·Fu를 상수에서 자재 DB로 분리 | 강종 확정(KS D 3030 SGMH295Y) 후 |

## 제약·규칙
- CLAUDE.md·CODEX.md를 준수한다. 판정에 영향하는 계산 변경은 사전 승인 후 반영한다(CODEX.md §8).
- 골든값(`tests/golden/*.json`)은 임의로 수정하지 않는다. 재산정이 필요하면 근거를 제시하고 승인받으며, 기존값은 `expected_legacy`로 보존한다. `_recalc_note`에 이력을 추가한다.
- JJH 백업 파일은 수정하거나 삭제하지 않는다.
- `repository.py`, `CODEX.md`, `docs/PRD.md`, `data/seed/board_property.json`은 CRLF 줄끝을 유지한다.
- 확인 필요 항목은 확정값처럼 쓰지 않는다: I-STUD 2겹 체결 방식 근거 자료(일체 거동 자체는 2026-10-21 확정), 고강도 12.5 시험 두께 입력(15 mm 오기 의심, E 과소), 방화 25.1·25.2 데이터 중복, 전방수 15 단위중량 미등재.

## 완료 조건
- 1단계: 로컬 pytest 54 passed, 렌더러 빌드 성공, 원격 푸시 확인
- 2단계: 선택 항목 구현과 관련 테스트 추가, 전체 pytest 통과, 변경 전후와 영향 보고(11개 시편 허용높이 4조건: 내진/비내진 × 부분합성/스터드 단독), `docs/review_round1_changes.md` 갱신

## 참고 파일
- `docs/review_round1_changes.md`, `docs/var_formula_spec.md`, `docs/PRD.md`, `CODEX.md`
- `backend/engine/calculator.py` (`_connection_capacity_kN`, `_gypsum_screw_design_shear_N`, `_effective_inertia_correction_factor`, `_stiffness_load_factor`, `_neutral_axis`)
- `backend/engine/constants.py`, `backend/engine/repository.py`, `data/seed/*.json`
- `renderer/src/components/result-panel.tsx`, `renderer/src/components/calculation-report.tsx`
- `tests/golden/requested_shape_cases.json`, `tests/test_requested_shape_cases.py`, `tests/test_golden_cases.py`

---
## 이력
- 2026-10-16: 1차 동기화(커밋 52ef3c7·3b07a4f·1270c79) 완료. C-2 composite 유지 확정, E-8 (c) 단방향 보정 완료(2026-10-20)
