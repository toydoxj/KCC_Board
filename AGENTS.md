# AGENTS.md

건식벽체(석고보드·스터드 부분합성) 면외 구조검토 Electron 데스크톱 앱. 본 저장소는 **Codex**로 작성되었다. 본 `AGENTS.md`는 Codex·Claude Code 등 모든 에이전트가 읽는 작업 안내 정본이다(`CLAUDE.md`는 `@AGENTS.md`로 본 문서를 불러온다).

## 0. 문서 우선순위 (필독 순서)
1. **`CODEX.md`** — 프로젝트 규칙 정본. 아키텍처·단위계·계산 파이프라인·설계 의도·금지사항을 담고 있다. **작업 전 반드시 정독한다.** (파일명이 `CODEX.md`라 에이전트가 자동 로드하지 못하므로 본 `AGENTS.md`가 이를 대신 가리킨다.)
2. `docs/PRD.md` — 요구사항 정의서(FR/NFR/Open Issues).
3. `docs/var_formula_spec.md` — 계산식 상세 명세.
4. `docs/development_plan.md` — 개발 로드맵·마일스톤(실행 명령은 리눅스식 경로이므로 아래 §3 Windows 명령으로 치환).

> 규칙이 충돌하면 `CODEX.md`가 우선한다. 본 문서는 에이전트 작업 편의(환경·명령·주의사항)만 보완한다.

## 1. 환경
- Python 가상환경은 `.venv-win\` (Python 3.14)이다 — **`.venv`가 아니라 `.venv-win` 사용**. `renderer/package.json`의 `build:backend`가 이 경로를 참조함

> CLAUDE.md 전역 규칙: **파이썬은 반드시 가상환경(`.venv-win`)에서 실행한다.**

## 3. 실행 명령 (Windows / PowerShell 기준)
가상환경 인터프리터는 `.\.venv-win\Scripts\python.exe`이다. (`development_plan.md`의 `.venv/bin/...`은 리눅스용이므로 아래로 치환한다.)

```powershell
# 자재 DB(SQLite) 초기화 — data/seed → data/local/materials.sqlite3
.\.venv-win\Scripts\python.exe -m backend.tools.init_db

# 전체 테스트(골든 회귀 포함). pyproject.toml에 pytest 설정 있음
.\.venv-win\Scripts\python.exe -m pytest -v

# FastAPI 백엔드 단독 실행 (localhost 사이드카)
.\.venv-win\Scripts\uvicorn.exe backend.api.main:app --host 127.0.0.1 --port 8000

# 렌더러 개발 서버 / 프로덕션 빌드
cd renderer; npm run dev      # http://127.0.0.1:3000
cd renderer; npm run build    # static export → renderer/out

# Electron 배포 번들(백엔드 PyInstaller + Next 빌드 + electron-builder)
cd renderer; npm run dist
```

> ⚠ **`backend/tools/dev_servers.py`는 POSIX 전용이다.** `.venv/bin/uvicorn`(리눅스 경로), `start_new_session`, `os.kill(..., SIGTERM)`을 사용하므로 Windows에서 동작하지 않는다. Windows에서는 위의 uvicorn·`npm run dev`를 **별도 터미널에서 각각** 실행한다. dev_servers를 크로스플랫폼으로 고치는 것은 별도 작업 항목이며, 로직 변경이므로 승인 후 진행한다.

## 4. 작업 시 주의사항 (범위·금지)
- **결과(판정)에 영향하는 계산 변경은 사용자 승인 후 반영**한다(무단 변경 금지 — `CODEX.md` §8, FIX-01~05).
- `tests/golden/cases.json` 등 **골든값은 임의 수정 금지**. 단면성능 변동으로 재산정이 필요하면 근거를 제시하고 승인받는다.
- **JJH 백업 파일 삭제·수정 금지**: `pyproject-JJH.toml`, `renderer/package-JJH.json`, `renderer/package-lock-JJH.json`, `data/local/materials-JJH.sqlite3`(원본 복사본).
- 미커밋 버전 변경(렌더러 0.5.0)은 의도된 것이므로 되돌리지 않는다.
- 하드코딩 금지(상수는 설정 분리), silent 실패 금지(예외 명시), 작업 전 단계별 계획 제시(`CODEX.md` §10).
- 응답·문서는 보고서체(~이다/~임), 한국어 주석 허용(기술용어·변수명 영문).
- **산출 문서(계산서·요약페이지 PDF·인쇄)에 「확인 필요」「미검증」「주의」「WARN」류 내부 검토 문구를 쓰지 않는다.** 판정은 계산값 기준 O.K / N.G(종합은 적합 / 부적합)만 쓰고, 안내 사유는 화면 메시지로 옮긴다. 단, 사용자 자유입력·식별 필드(출처·제품명·자재명 등)는 원문 그대로 인쇄하고 PDF 출력 전 화면에 유보 문구 필드 목록을 경고로 보인다(`CODEX.md` §11, item 182).

## 5. 검증 루프 (변경 후 반드시 실행)
1. 계산엔진/API 변경 → `.\.venv-win\Scripts\python.exe -m pytest -v` (골든 회귀 상대오차 ≤ 0.1% 확인)
2. 렌더러 변경 → `cd renderer; npm run build`. 계산서 문구 회귀는 pytest의 `tests/test_report_wording.py`가 `renderer/node_modules`로 실제 렌더링 텍스트까지 검사한다(`npm ci` 선행). node_modules가 없으면 이 시험은 실패한다
3. DB 시드 변경 → `init_db` 재실행 후 pytest
