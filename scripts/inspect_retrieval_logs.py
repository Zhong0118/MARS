from __future__ import annotations

"""Inspect retrieval logs for debugging search behavior."""

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.db import get_connection


def build_parser() -> argparse.ArgumentParser:
    """Build args for retrieval-log inspection."""
    parser = argparse.ArgumentParser(description="Inspect retrieval_logs in MARS.")
    parser.add_argument("--project-id", help="Optional project filter.")
    parser.add_argument("--top", type=int, default=20, help="How many logs to print.")
    return parser


def main() -> None:
    """Print recent retrieval logs with selected memory IDs."""
    args = build_parser().parse_args()
    query = """
        SELECT *
        FROM retrieval_logs
        WHERE 1 = 1
    """
    params: list[str] = []
    if args.project_id:
        query += " AND project_id = ?"
        params.append(args.project_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(args.top)

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()

    if not rows:
        print("No retrieval logs found for the current filter.")
        return

    for index, row in enumerate(rows, start=1):
        print(f"[{index}] query: {row['query']}")
        print(f"time: {row['created_at']}")
        print(f"project_id: {row['project_id']}")
        print(f"query_type: {row['query_type']}")
        print(f"retrieval_method: {row['retrieval_method']}")
        print(f"latency_ms: {row['latency_ms']}")
        print(f"selected_memory_ids: {json.loads(row['selected_memory_ids_json'] or '[]')}")
        print(f"score_items: {json.loads(row['score_json'] or '[]')}")
        if index != len(rows):
            print()


if __name__ == "__main__":
    main()
