from __future__ import annotations

"""CLI placeholder for local benchmark execution."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.db import ensure_storage_dirs


def main() -> None:
    """Create report directories so later benchmark phases can write outputs."""
    ensure_storage_dirs()
    print("Benchmark placeholder for phase 0/1.")



if __name__ == "__main__":
    main()
