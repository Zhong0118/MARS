from __future__ import annotations

"""CLI entrypoint for creating the local MARS SQLite database."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.db import initialize_database


def main() -> None:
    """Initialize the local database file and print its location."""
    db_path = initialize_database()
    print(f"Initialized database at {db_path}")


if __name__ == "__main__":
    main()
