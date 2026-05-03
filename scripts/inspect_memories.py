from __future__ import annotations

"""Inspect stored memories grouped by status, topic, and type."""

import argparse
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.db import get_connection, list_memories


def build_parser() -> argparse.ArgumentParser:
    """Build command-line args for memory inspection."""
    parser = argparse.ArgumentParser(description="Inspect MARS memories in the local database.")
    parser.add_argument("--project-id", help="Optional project filter.")
    parser.add_argument("--status", help="Optional status filter, e.g. active or pending.")
    parser.add_argument("--top", type=int, default=20, help="How many memories to print.")
    return parser


def main() -> None:
    """Print a compact database summary plus individual memory rows."""
    args = build_parser().parse_args()
    with get_connection() as connection:
        memories = list_memories(connection, project_id=args.project_id, status=args.status)

    if not memories:
        print("No memories found for the current filter.")
        return

    status_counts = Counter(memory.status for memory in memories)
    topic_counts = Counter(memory.topic or "unknown" for memory in memories)
    type_counts = Counter(memory.memory_type for memory in memories)

    print("Summary:")
    print(f"total_memories: {len(memories)}")
    print(f"status_counts: {dict(status_counts)}")
    print(f"topic_counts: {dict(topic_counts)}")
    print(f"type_counts: {dict(type_counts)}")
    print()
    print("Memories:")

    for index, memory in enumerate(memories[: args.top], start=1):
        print(f"[{index}] {memory.title}")
        print(f"memory_id: {memory.memory_id}")
        print(f"status: {memory.status}")
        print(f"topic: {memory.topic}")
        print(f"type: {memory.memory_type}")
        print(f"version_group_id: {memory.version_group_id}")
        print(f"source_event_count: {len(memory.source_event_ids)}")
        print(f"source_event_ids: {', '.join(memory.source_event_ids)}")
        print(f"content: {memory.content}")
        if memory.rationale:
            print(f"rationale: {' | '.join(memory.rationale)}")
        if index != min(len(memories), args.top):
            print()


if __name__ == "__main__":
    main()
