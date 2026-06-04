"""SQLite 자재 DB 초기화 CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.engine.repository import initialize_sqlite_from_seed


def main() -> None:
  parser = argparse.ArgumentParser(description="JSON 시드에서 SQLite 자재 DB를 초기화합니다.")
  parser.add_argument(
    "--db-path",
    default="data/local/materials.sqlite3",
    help="생성할 SQLite DB 경로",
  )
  parser.add_argument(
    "--seed-dir",
    default="data/seed",
    help="JSON 시드 디렉터리 경로",
  )
  parser.add_argument(
    "--no-reset",
    action="store_true",
    help="기존 테이블을 삭제하지 않고 재적재합니다.",
  )
  args = parser.parse_args()

  initialize_sqlite_from_seed(
    db_path=Path(args.db_path),
    seed_dir=Path(args.seed_dir),
    reset=not args.no_reset,
  )
  print(f"SQLite 자재 DB 초기화 완료: {args.db_path}")


if __name__ == "__main__":
  main()
