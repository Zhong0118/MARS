from __future__ import annotations

"""CLI placeholder for local memory search.

Phase 0/1 only defines the command shape so later retrieval work can plug into
the same script without changing the interface.
"""

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    """Build command-line arguments for local memory search."""
    parser = argparse.ArgumentParser(description="Search MARS memories.")
    parser.add_argument("query", help="Search query text.")
    parser.add_argument("--project-id", help="Optional project filter.")
    return parser


def main() -> None:
    """Print the accepted query shape until retrieval is implemented."""
    args = build_parser().parse_args()
    project_suffix = f" project_id={args.project_id}" if args.project_id else ""
    print(f"Search placeholder for query={args.query!r}{project_suffix}")


if __name__ == "__main__":
    main()
