from __future__ import annotations

"""Inspect raw events stored in the local raw ledger."""

import argparse
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.db import get_connection


def build_parser() -> argparse.ArgumentParser:
    """Build args for raw-event inspection."""
    parser = argparse.ArgumentParser(description="Inspect raw_events in MARS.")
    parser.add_argument("--project-id", help="Optional project filter.")
    parser.add_argument("--chat-id", help="Optional chat filter.")
    parser.add_argument("--top", type=int, default=20, help="How many rows to print.")
    return parser


def main() -> None:
    """Print event distribution and recent raw events."""
    args = build_parser().parse_args()
    query = """
        SELECT *
        FROM raw_events
        WHERE 1 = 1
    """
    params: list[str] = []
    if args.project_id:
        query += " AND project_id = ?"
        params.append(args.project_id)
    if args.chat_id:
        query += " AND chat_id = ?"
        params.append(args.chat_id)
    query += " ORDER BY transaction_time DESC, created_at DESC"

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()

    if not rows:
        print("No raw events found for the current filter.")
        return

    project_counts = Counter(row["project_id"] or "unknown" for row in rows)
    chat_counts = Counter(row["chat_id"] or "unknown" for row in rows)
    actor_counts = Counter(row["actor_name"] or row["actor_id"] or "unknown" for row in rows)

    print("Summary:")
    print(f"total_events: {len(rows)}")
    print(f"project_counts: {dict(project_counts)}")
    print(f"chat_counts: {dict(chat_counts)}")
    print(f"actor_counts: {dict(actor_counts)}")
    print()
    print("Recent events:")

    for index, row in enumerate(rows[: args.top], start=1):
        print(f"[{index}] {row['event_id']}")
        print(f"time: {row['transaction_time']}")
        print(f"project_id: {row['project_id']}")
        print(f"chat_id: {row['chat_id']}")
        print(f"actor: {row['actor_name'] or row['actor_id']}")
        print(f"content: {row['content']}")
        if index != min(len(rows), args.top):
            print()


if __name__ == "__main__":
    main()
