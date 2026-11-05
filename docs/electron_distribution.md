# Electron 배포 절차

현재 배포 설정은 `electron@42.4.1`, `electron-builder@26.15.3` 기준입니다.
`electron-builder` 최신 계열은 Node.js 22.12 이상을 요구하므로, Windows 배포 빌드는 Node.js 22.12 이상에서 실행합니다.

## 1. Windows용 Python 가상환경 준비

현재 저장소의 `.venv`가 POSIX형 구조라면 Windows 빌드에는 `.venv-win`을 별도로 사용합니다.
이 가상환경은 빌드 도구 실행용이며, 설치 파일에는 PyInstaller로 만든 백엔드 실행 파일만 포함합니다.

```powershell
python -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install --upgrade pip
.\.venv-win\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## 2. Renderer 의존성 설치

OneDrive 동기화가 끝난 뒤 `renderer` 폴더에서 실행합니다.

```powershell
cd renderer
npm install
```

## 3. Electron 설치 파일 생성

```powershell
npm run dist
```

`npm run dist`는 FastAPI 백엔드를 `renderer/backend-dist/kcc-board-api/kcc-board-api.exe`로 먼저 패키징한 뒤,
Next 정적 파일과 Electron 설치 파일을 생성합니다. 빌드 결과는 `renderer/dist`에 생성됩니다.
현재 버전의 Windows 설치 파일명은 `KCC Board Setup 0.8.0.exe`입니다.

## 개발 실행

개발 중에는 Next 개발 서버와 Electron을 별도 터미널에서 실행합니다.

```powershell
cd renderer
npm run dev
```

```powershell
cd renderer
npm run electron
```


## 백엔드 포트·프로세스 관리 (2차 심사의견 E-3)

- 백엔드 포트: Electron main이 기동 시 OS가 할당한 빈 포트를 쓴다(`listen(0)`). 렌더러는 preload `getApiBaseUrl()`로 주소를 받는다.
- 포트 선점 대응: 기동 중 백엔드가 종료되면 새 포트로 최대 3회 재시도한다.
- 종료: `before-quit`·`will-quit`에서 Windows는 `taskkill /PID {pid} /T /F`로 프로세스 트리를 종료한다.
- 강제 종료 대응: 백엔드는 `KCC_BOARD_PARENT_PID`의 부모 핸들을 감시하다가 부모가 사라지면 스스로 종료한다.
- 잔존 프로세스: 설치본 기동 시 `kcc-board-api.exe`가 남아 있으면 확인 대화상자를 띄우고, 확인 시 `taskkill /IM kcc-board-api.exe /T /F` 후 시작한다.
- 로그: `%APPDATA%\kcc-board-rendererackend-electron.log` (할당 포트 `api port: …` 기록).
- 알려진 제한: 잔존 정리는 이름(`/IM`) 기준이므로 같은 PC의 다른 계정에서 실행 중인 KCC Board 백엔드도 종료될 수 있다.

### 검증 기록 (2026-11-05, v0.8.0, Windows 11, `renderer/dist/win-unpacked`)

| # | 시험 | 절차 | 결과 |
|---|---|---|---|
| 1 | 8000 포트 점유 상태 기동 | `python -m http.server 8000` 실행 후 앱 기동 | 적합. 백엔드 포트 57575 할당, `/api/health` 정상. 렌더러(`KCC Board`) 프로세스가 57575로 접속 확인 |
| 2 | 앱 강제 종료 후 잔존 확인 | 앱 주 프로세스만 `Stop-Process -Force` | 적합. 0.5 s 후 `kcc-board-api.exe` 종료, 잔존 0개 |
| 3 | 잔존 프로세스 안내 | 부모 PID 없이 `kcc-board-api.exe`(포트 58123) 수동 실행 후 앱 기동 | 적합. "잔존 백엔드 프로세스" 대화상자 표시 → 확인 → 잔존 PID 종료(`leftover backend killed: ok`), 새 포트 49714로 정상 기동 |

정상 종료(창 닫기) 경로의 `taskkill /PID /T /F`는 수동 확인 대상이다(자동 시험은 창 숨김 모드로 수행).
