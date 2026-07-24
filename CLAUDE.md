# CLAUDE.md

건식벽체(석고보드·스터드 부분합성) 면외 구조검토 Electron 데스크톱 앱. 본 저장소는 **Codex**로 작성되었으며, Claude Code로 이어서 작업하기 위한 안내 문서이다.

## 0. 문서 우선순위 (필독 순서)
1. **`CODEX.md`** — 프로젝트 규칙 정본. 아키텍처·단위계·계산 파이프라인·설계 의도·금지사항을 담고 있다. **작업 전 반드시 정독한다.** (파일명이 `CODEX.md`라 Claude Code가 자동 로드하지 못하므로 본 `CLAUDE.md`가 이를 대신 가리킨다.)
2. `docs/PRD.md` — 요구사항 정의서(FR/NFR/Open Issues).
3. `docs/var_formula_spec.md` — 계산식 상세 명세.
4. `docs/development_plan.md` — 개발 로드맵·마일스톤(실행 명령은 리눅스식 경로이므로 아래 §3 Windows 명령으로 치환).

> 규칙이 충돌하면 `CODEX.md`가 우선한다. 본 문서는 Claude Code 작업 편의(환경·명령·주의사항)만 보완한다.

## 1. 환경 (검증 완료: 2026-07-24)
| 항목 | 상태 |
|------|------|
| Python 가상환경 | `.venv-win\` (Python 3.14.2) — **`.venv`가 아니라 `.venv-win` 사용**. `renderer/package.json`의 `build:backend`가 이 경로를 참조함 |
| Python 패키지 | `requirements-dev.txt` 설치 완료(fastapi 0.139, uvicorn 0.51, pytest 9.1, httpx2 2.5, pyinstaller 6.21, pydantic 2.13) |
| Node / npm | v24.13.1 / 11.8.0, `renderer/node_modules` 설치 완료 |
| 자재 DB | `data/local/materials.sqlite3` 초기화 완료(`data/seed`에서 재생성) |
| 테스트 | 전체 통과 (45 passed + 36 subtests) — 골든 회귀 포함 |
| 렌더러 빌드 | `npm run build` 성공(Next.js 15.5, static export) |

> CLAUDE.md 전역 규칙: **파이썬은 반드시 가상환경(`.venv-win`)에서 실행한다.**

## 2. 코드 구조
```
backend/
├─ api/         FastAPI 앱(main.py, schemas.py) — /api/health, /api/check, /api/db/*
├─ engine/      순수함수 계산엔진(calculator, models, seismic, constants) + repository(JSON/SQLite)
├─ tools/       init_db(SQLite 초기화), dev_servers(⚠ POSIX 전용 — §3 참조)
└─ electron_api.py   PyInstaller 번들 엔트리포인트
renderer/       Next.js 15(App Router) + Electron(main.cjs). src/{app,components,lib,store}
data/seed/      자재 DB 시드(JSON) — SQLite의 정본
tests/golden/   엑셀 회귀 골든값(cases.json 등)
refs/           원본 엑셀·단면 시각화(정본 데이터 소스)
```

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

## 5. 검증 루프 (변경 후 반드시 실행)
1. 계산엔진/API 변경 → `.\.venv-win\Scripts\python.exe -m pytest -v` (골든 회귀 상대오차 ≤ 0.1% 확인)
2. 렌더러 변경 → `cd renderer; npm run build`
3. DB 시드 변경 → `init_db` 재실행 후 pytest
