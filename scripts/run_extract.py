from __future__ import annotations

"""CLI entrypoint for sample-chat ingestion and extraction.

Phase 2 stores normalized RawEvent records.
Phase 3 runs deterministic MockLLM extraction and persists MemoryObject plus
MemorySource rows.
Phase 5 applies reconciliation so newer memories can supersede older ones.
"""

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.ingestion import extract_and_reconcile, ingest_events
from app.connectors.sample_loader import load_raw_events
from app.storage.db import get_connection, initialize_database
from app.storage.models import MemoryObject
from app.llm.provider import get_llm_provider


def build_parser() -> argparse.ArgumentParser:
    """Build command-line arguments for the extraction script."""
    parser = argparse.ArgumentParser(description="Ingest sample chat JSON and optionally extract memories.")
    parser.add_argument("--input", required=True, help="Path to sample chat JSON file.")
    parser.add_argument("--ingest-only", action="store_true", help="Only persist raw events, skip memory extraction.")
    return parser


def print_memory_summary(memories: list[MemoryObject]) -> None:
    """Print a compact summary of extracted memories for developer feedback."""
    if not memories:
        print("No memories were extracted.")
        return

    print("Extracted memory summary:")
    for index, memory in enumerate(memories, start=1):
        print(f"[{index}] {memory.title}")
        print(f"memory_id: {memory.memory_id}")
        print(f"version_group_id: {memory.version_group_id}")
        print(f"memory_type: {memory.memory_type}")
        print(f"status: {memory.status}")
        print(f"topic: {memory.topic}")
        print(f"content: {memory.content}")
        print(f"source_event_count: {len(memory.source_event_ids)}")
        print(f"source_event_ids: {', '.join(memory.source_event_ids)}")
        if index != len(memories):
            print()


def main() -> None:
    """Initialize storage, ingest events, and optionally extract structured memories."""
    args = build_parser().parse_args()
    initialize_database()
    events = load_raw_events(args.input)
    provider = get_llm_provider()

    with get_connection() as connection:
        ingest_events(connection, events)

        if args.ingest_only:
            print(f"Ingested {len(events)} raw events from {args.input}")
            return

        result = extract_and_reconcile(connection, events)

    print(f"Provider: {type(provider).__name__}")
    print(f"Ingested {len(events)} raw events and extracted {len(result.memories)} memories from {args.input}")
    if result.consolidation_traces:
        print(f"\nConsolidation: {result.pre_consolidation_count} -> {result.post_consolidation_count} memories "
              f"({result.llm_pair_count} LLM pair judgments)")
        for trace in result.consolidation_traces:
            print(f"  {trace.primary_memory_id} <-> {trace.candidate_memory_id}: "
                  f"merge={trace.merge_decision} relation={trace.relation} "
                  f"stage={trace.filter_stage} conf={trace.confidence:.2f}")
    print_memory_summary(result.memories)


if __name__ == "__main__":
    main()
