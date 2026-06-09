"""Electron 배포용 FastAPI 실행 진입점."""

from __future__ import annotations

import os

import uvicorn

from backend.api.main import app


def main() -> None:
  host = os.environ.get("KCC_BOARD_API_HOST", "127.0.0.1")
  port = int(os.environ.get("KCC_BOARD_API_PORT", "8000"))
  uvicorn.run(app, host=host, port=port, access_log=False)


if __name__ == "__main__":
  main()
