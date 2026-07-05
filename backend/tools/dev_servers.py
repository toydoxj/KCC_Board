"""로컬 백엔드·렌더러 개발 서버 실행 도구."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
LOCAL_DIR = ROOT_DIR / "data/local"
BACKEND_PID = LOCAL_DIR / "backend.pid"
RENDERER_PID = LOCAL_DIR / "renderer.pid"


def main() -> None:
  parser = argparse.ArgumentParser(description="로컬 개발 서버를 시작하거나 중지합니다.")
  parser.add_argument("command", choices=["start", "stop"], help="실행할 명령")
  args = parser.parse_args()

  if args.command == "start":
    start_servers()
  else:
    stop_servers()


def start_servers() -> None:
  LOCAL_DIR.mkdir(parents=True, exist_ok=True)
  _start_process(
    pid_path=BACKEND_PID,
    log_path=LOCAL_DIR / "backend.log",
    cwd=ROOT_DIR,
    command=[
      str(ROOT_DIR / ".venv/bin/uvicorn"),
      "backend.api.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      "8000",
    ],
  )
  _start_process(
    pid_path=RENDERER_PID,
    log_path=LOCAL_DIR / "renderer.log",
    cwd=ROOT_DIR / "renderer",
    command=["npm", "run", "dev", "--", "--port", "3000"],
  )
  print("개발 서버 시작 요청 완료")


def stop_servers() -> None:
  for pid_path in [RENDERER_PID, BACKEND_PID]:
    _stop_process(pid_path)
  print("개발 서버 중지 요청 완료")


def _start_process(pid_path: Path, log_path: Path, cwd: Path, command: list[str]) -> None:
  _stop_process(pid_path)
  with log_path.open("ab") as log_file:
    process = subprocess.Popen(
      command,
      cwd=cwd,
      stdout=log_file,
      stderr=subprocess.STDOUT,
      stdin=subprocess.DEVNULL,
      start_new_session=True,
      close_fds=True,
    )
  pid_path.write_text(str(process.pid), encoding="utf-8")


def _stop_process(pid_path: Path) -> None:
  if not pid_path.exists():
    return
  text = pid_path.read_text(encoding="utf-8").strip()
  pid_path.unlink(missing_ok=True)
  if not text:
    return
  try:
    os.kill(int(text), signal.SIGTERM)
  except ProcessLookupError:
    return


if __name__ == "__main__":
  main()
