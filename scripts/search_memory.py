from __future__ import annotations

"""CLI entrypoint for keyword-based local memory retrieval.
命令行搜索入口
"""

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.retriever import MemoryRetriever


def build_parser() -> argparse.ArgumentParser:
    """Build command-line arguments for local memory search."""
    parser = argparse.ArgumentParser(description="Search MARS memories.")
    parser.add_argument("query", help="Search query text.")
    parser.add_argument("--project-id", help="Optional project filter.")
    parser.add_argument("--top-k", type=int, default=5, help="Maximum number of results to return.")
    return parser


def main() -> None:
    """Run a keyword search and print compact evidence-rich results."""
    args = build_parser().parse_args()
    retriever = MemoryRetriever(top_k=args.top_k)
    results = retriever.search(args.query, project_id=args.project_id)

    if not results:
        print("No active memories matched the query.")
        return

    for index, result in enumerate(results, start=1):
        print(f"[{index}] {result.title}")
        print(f"memory_id: {result.memory_id}")
        print(f"project_id: {result.project_id}")
        print(f"topic: {result.topic}")
        print(f"status: {result.status}")
        print(f"score: {result.score}")
        print(f"content: {result.content}")
        print(f"source_event_ids: {', '.join(result.source_event_ids)}")
        if result.rationale:
            print(f"rationale: {' | '.join(result.rationale)}")
        if result.objections:
            print(f"objections: {' | '.join(result.objections)}")
        if index != len(results):
            print()


if __name__ == "__main__":
    main()
