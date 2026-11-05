"""Electron 배포용 FastAPI 실행 진입점."""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time

import uvicorn

from backend.api.main import app

# 부모(Electron) 프로세스 생존 확인 주기 (2차 심사의견 E-3)
PARENT_WATCH_INTERVAL_S = 1.0
_WINDOWS_SYNCHRONIZE = 0x00100000
_WINDOWS_WAIT_TIMEOUT = 0x00000102


_WINDOWS_WAIT_OBJECT_0 = 0x00000000


def _kernel32() -> ctypes.WinDLL:
  """64비트에서 HANDLE이 잘리지 않도록 인자·반환 형식을 지정한다."""
  from ctypes import wintypes

  kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
  kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
  kernel32.OpenProcess.restype = wintypes.HANDLE
  kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
  kernel32.WaitForSingleObject.restype = wintypes.DWORD
  kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
  kernel32.CloseHandle.restype = wintypes.BOOL
  return kernel32


def _windows_open_process(pid: int) -> int | None:
  handle = _kernel32().OpenProcess(_WINDOWS_SYNCHRONIZE, False, pid)
  return handle or None


def _windows_process_alive(pid: int) -> bool:
  handle = _windows_open_process(pid)
  if handle is None:
    return False
  kernel32 = _kernel32()
  try:
    # 종료되지 않은 프로세스는 대기 시간 0에서 WAIT_TIMEOUT을 반환한다
    return kernel32.WaitForSingleObject(handle, 0) == _WINDOWS_WAIT_TIMEOUT
  finally:
    kernel32.CloseHandle(handle)


def _watch_parent_windows(handle: int) -> None:
  """시작 시 연 부모 핸들을 끝까지 유지한다. PID가 재사용되어도 원래 부모의 종료를 감지한다."""
  kernel32 = _kernel32()
  interval_ms = int(PARENT_WATCH_INTERVAL_S * 1000)
  while True:
    if kernel32.WaitForSingleObject(handle, interval_ms) == _WINDOWS_WAIT_OBJECT_0:
      os._exit(0)


def _posix_process_alive(pid: int) -> bool:
  try:
    os.kill(pid, 0)
  except ProcessLookupError:
    return False
  except PermissionError:
    return True
  return True


def process_alive(pid: int) -> bool:
  if sys.platform == "win32":
    return _windows_process_alive(pid)
  return _posix_process_alive(pid)


def _watch_parent_posix(pid: int) -> None:
  """부모가 사라지면(강제 종료 등) 백엔드도 즉시 종료하여 잔존 프로세스를 남기지 않는다."""
  while True:
    time.sleep(PARENT_WATCH_INTERVAL_S)
    if not process_alive(pid):
      os._exit(0)


def start_parent_watchdog(environ: dict[str, str] | os._Environ[str] = os.environ) -> int | None:
  raw = environ.get("KCC_BOARD_PARENT_PID")
  if not raw:
    return None
  try:
    pid = int(raw)
  except ValueError as error:
    raise ValueError(f"KCC_BOARD_PARENT_PID가 정수가 아닙니다: {raw}") from error
  if sys.platform == "win32":
    handle = _windows_open_process(pid)
    if handle is None:
      # 시작 시점에 부모가 이미 없으면 띄울 이유가 없다
      os._exit(0)
    target, args = _watch_parent_windows, (handle,)
  else:
    target, args = _watch_parent_posix, (pid,)
  threading.Thread(target=target, args=args, name="parent-watchdog", daemon=True).start()
  return pid


def main() -> None:
  host = os.environ.get("KCC_BOARD_API_HOST", "127.0.0.1")
  port = int(os.environ.get("KCC_BOARD_API_PORT", "8000"))
  start_parent_watchdog()
  uvicorn.run(app, host=host, port=port, access_log=False)


if __name__ == "__main__":
  main()
