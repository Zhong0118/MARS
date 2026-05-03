from __future__ import annotations

"""Backup, reset, or rebuild the local MARS database."""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.db import DB_PATH, initialize_database


def build_parser() -> argparse.ArgumentParser:
    """Build args for local database cleanup workflow."""
    parser = argparse.ArgumentParser(description="Backup or reset the local MARS SQLite database.")
    parser.add_argument("--backup-only", action="store_true", help="Only create a timestamped backup.")
    parser.add_argument("--reset", action="store_true", help="Delete the current DB and rebuild schema.")
    return parser


def main() -> None:
    """Run backup/reset workflow for the default local SQLite file."""
    args = build_parser().parse_args()
    if not DB_PATH.exists():
        print(f"Database does not exist yet: {DB_PATH}")
        if args.reset:
            initialize_database()
            print(f"Initialized new database at {DB_PATH}")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.with_name(f"{DB_PATH.stem}_backup_{timestamp}{DB_PATH.suffix}")
    shutil.copy2(DB_PATH, backup_path)
    print(f"Backup created: {backup_path}")

    if args.backup_only and not args.reset:
        return

    if args.reset:
        DB_PATH.unlink(missing_ok=True)
        initialize_database()
        print(f"Database reset and reinitialized: {DB_PATH}")


if __name__ == "__main__":
    main()
