# Electron 배포 절차

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
