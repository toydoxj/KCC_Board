# 개발 실행 계획

## 1. 기준 문서
- 요구사항 기준: `docs/PRD.md`
- 계산식 기준: `docs/var_formula_spec.md`
- 회귀검증 기준: `tests/golden/cases.json`
- 초기 자재 DB: `data/seed/*.json`

## 2. 개발 원칙
- 계산엔진은 UI, Electron, FastAPI에 의존하지 않는 순수 Python 모듈로 구현한다.
- 내부 단위는 PRD 기준을 따른다. 길이는 mm, 면적은 mm², 단면2차모멘트는 mm⁴, 응력은 N/mm², 모멘트는 kN·m로 유지한다.
- 모든 DB 조회 실패는 명시적 예외로 처리한다.
- 계산 중간값은 계산서와 엑셀 대조를 위해 결과에 포함한다.
- 결과에 영향을 주는 FIX 항목은 승인 게이트를 둔다.

## 3. 1차 착수 범위(M0~M1)

### M0. 백엔드 골격
- Python 가상환경(`.venv`) 구성
- `backend/` 패키지 구조 생성
- JSON 시드 기반 Repository 구현
- 표준 라이브러리 기반 테스트 실행 구조 구성

### M1. 계산엔진
- `WallCheckRequest`, `WallCheckResult` 모델 정의
- FR-CALC-01~14 순수함수 파이프라인 구현
- 엑셀 대응 핵심값 반환
  - `neutral_axis_mm`
  - `I_full_mm4`
  - `eta`
  - `I_eff_mm4`
  - `Mn_kNm`
  - `Mu_kNm`
  - `stress_ratio`
  - `deflection_mm`
  - `deflection_limit_mm`
  - `seismic_moment_kNm`
  - `deflection_verdict`
  - `stress_verdict`
- `tests/golden/cases.json` 기준 상대오차 0.1% 이내 회귀검증

## 4. 승인 게이트
- FIX-01: 현재 골든값에 이미 반영되어 있으므로 엔진도 전체 레이어 중량 합산을 기본으로 한다.
- FIX-02: 합성률 분모 통일은 결과 영향 항목이므로 기본 엔진에서는 엑셀 호환 모드를 우선 구현하고, 별도 옵션으로 분리한다.
- FIX-03: 중립축 적층 좌표는 가변 레이어 모델 기준으로 정상화한다.
- FIX-04: 볼트 강도식은 명세의 엑셀식을 우선 이관한다.
- FIX-05: 빈 보드 `----`는 입력 변환 단계에서 제외한다.

## 5. 이후 단계
- M2: FastAPI `/api/check` 및 SQLite Repository
  - 완료: `/api/health`, `/api/check`, 공통 응답 형식, API 회귀테스트
  - 완료: SQLite 스키마, JSON 시드 초기화, SQLite 조회 Repository, SQLite 기반 엔진/API 회귀테스트
  - 다음: 자재 DB 조회/CRUD API
- M3: Electron + Next.js 입력/결과 UI
  - 완료: Next.js 15 렌더러 초기 화면, 자재 목록 연동, `/api/check` 검토 실행, 단면 SVG, 결과 패널
  - 다음: Electron shell, preload/IPC, FastAPI 사이드카 spawn
- M4: 자동선정 `/api/optimize`
- M5: 계산서 PDF `/api/report`
- M6: 패키징 및 배포

## 6. 완료 기준
- 골든 케이스 3건이 모두 통과한다.
- 계산엔진은 JSON 시드만으로 실행 가능하다.
- 계산 결과는 모든 핵심 중간값과 판정을 포함한다.
- 테스트는 가상환경에서 한 명령으로 실행 가능하다.

## 7. 현재 실행 명령
- 개발 의존성 설치: `.venv/bin/python -m pip install -r requirements-dev.txt`
- SQLite 자재 DB 초기화: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m backend.tools.init_db`
- 전체 테스트: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -v`
- API 실행: `.venv/bin/uvicorn backend.api.main:app --host 127.0.0.1 --port 8000`
- UI 빌드: `cd renderer && npm run build`
- 로컬 UI 서버 시작: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m backend.tools.dev_servers start`
- 로컬 UI 서버 중지: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m backend.tools.dev_servers stop`
- UI 접속: `http://127.0.0.1:3000`
