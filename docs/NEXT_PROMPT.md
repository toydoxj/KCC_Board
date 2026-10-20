<!-- 생성: 2026-10-16 | 대상: 1차 심사의견 반영 — 로컬 동기화·검증 및 후속 항목 -->

# KCC_Board 1차 심사의견 반영 — 로컬 동기화·검증 및 후속 작업 요청

## 목표
1. 클라우드 세션에서 작성한 커밋 3건을 로컬 저장소에 반영하고 원격에 푸시한다.
2. Windows 환경(.venv-win)에서 테스트·빌드를 재검증한다.
3. 후속 미결 항목 중 사용자가 선택한 1건을 진행한다.

## 현재 상태 (요약)
- 브랜치 `fix/review-round1-strength` (기준 main `a81524c`), 원격 미푸시, 커밋 3건(마지막은 본 문서)
  - `52ef3c7` DXF 단면 DB(69규격)·Se(AISI S100-16 App.1, Fy 295)·S=I/c_max·중앙부 이음 관성 수정·Ieff 하한·KDS 0.75L+0.75(0.7E)·R 재보정(중앙부 이음 0.35, T.silent 0.45)·골든값 재산정(`expected_legacy` 보존)
  - `3b07a4f` 피스 인장 검토 신설: 풀아웃 Pnot = 0.85·tc·d·Fu2(Eq. J4.4.1-1, Ω 3.0), 풀스루 입력값(기본 343 N, 잠정), `screw_tension_verdict`, N.G 시 최대높이 0
- 클라우드(Linux) 검증: pytest 50 passed + 36 subtests, `next build` 성공
- 변경 내역: `docs/review_round1_changes.md`, 계산식: `docs/var_formula_spec.md`

## 작업 범위
### 1단계 (필수, 선행)
1. 저장소 루트에 `review-round1.bundle`을 두고 실행:
   ```powershell
   git fetch .\review-round1.bundle fix/review-round1-strength:fix/review-round1-strength
   git checkout fix/review-round1-strength
   git log --oneline -4   # HEAD(NEXT_PROMPT), 3b07a4f, 52ef3c7, a81524c 확인
   ```
2. 자재 DB 재초기화(Se 열 추가): `.\.venv-win\Scripts\python.exe -m backend.tools.init_db`
3. `.\.venv-win\Scripts\python.exe -m pytest -v` → 50 passed 확인
4. `cd renderer; npm run build` 성공 확인
5. 이상 없으면 `git push -u origin fix/review-round1-strength` (main 병합·PR 생성은 사용자 확인 후)
6. bundle 파일은 커밋하지 않는다.

> 1단계 완료(2026-10-16, Windows): pytest 50 passed + 36 subtests, `npm run build` 성공, `origin/fix/review-round1-strength` 생성.

### 2단계 (사용자 선택 1건만 진행 — 착수 전 선택 질문, B~E 보류 중)
| 후보 | 관련 의견 | 내용 |
|---|---|---|
| ~~A~~ | C-2 | **종결(2026-10-16)**: composite 기본값 유지 확정, 피스 인장(풀아웃·풀스루) 검토로 대응. stud_only 변경 안 함 |
| B | E-9 | 중립축 위치 검사 추가(NA가 스터드 밖이면 경고·누적 방향 재설정) |
| C | B-2·D-1 | 실험 검증범위 초과 경고(결과 화면·계산서) |
| ~~D~~ | E-8 (c) | **완료(2026-10-20)**: 단방향 보정 I = R·I_raw·min[1,(u/u_ref)^(1−m)] 반영 |
| E | B-8 | 강종별 Fy·Fu를 상수에서 자재 DB로 분리 |

## 제약·규칙
- CLAUDE.md·CODEX.md 준수. 판정에 영향하는 계산 변경은 사전 승인 후 반영(CODEX.md §8)
- 골든값(`tests/golden/*.json`) 임의 수정 금지. 재산정 시 근거 제시·승인, 기존값은 `expected_legacy`로 보존
- JJH 백업 파일 수정·삭제 금지
- `repository.py`, `CODEX.md`, `docs/PRD.md`는 CRLF 줄끝 유지
- 확인 필요 항목(아래)은 확정값처럼 사용하지 말 것: T.silent 종전 DB 출처, I-STUD 2겹 플랜지 일체 거동, 강종 Fy 295 밀시트, 풀스루 시험값, `bolt.count` 의미(인장 계산 미적용)

## 완료 조건
- 1단계: 로컬 pytest 50 passed, 렌더러 빌드 성공, 원격 브랜치 생성 확인
- 2단계: 선택 항목 구현 + 관련 테스트 추가, 전체 pytest 통과, 변경 전후·영향(11개 시편 허용높이) 보고, `docs/review_round1_changes.md` 갱신

## 참고 파일
- `docs/review_round1_changes.md`, `docs/var_formula_spec.md`, `docs/PRD.md`, `CODEX.md`
- `backend/engine/calculator.py` (`_stud_section_modulus`, `_stud_assembly`, `_screw_tension_result`, `_effective_inertia_correction_factor`)
- `backend/engine/constants.py`, `data/seed/stud_section.json`
- `tests/golden/requested_shape_cases.json`, `tests/test_golden_cases.py`
