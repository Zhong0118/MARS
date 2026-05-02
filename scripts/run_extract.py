from __future__ import annotations

"""CLI entrypoint for sample-chat ingestion.

In phase 0/1 this script only loads sample JSON and writes RawEvent records.
Later phases will extend it to run memory extraction as well.
"""

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.connectors.sample_loader import load_raw_events
from app.storage.db import get_connection, initialize_database, insert_raw_events


def build_parser() -> argparse.ArgumentParser:
    """Build command-line arguments for the extraction script."""
    parser = argparse.ArgumentParser(description="Ingest sample chat JSON into raw_events.")
    parser.add_argument("--input", required=True, help="Path to sample chat JSON file.")
    parser.add_argument("--ingest-only", action="store_true", help="Reserved for later phases.")
    return parser


def main() -> None:
    """Initialize storage, normalize the input file, and persist raw events."""
    args = build_parser().parse_args()
    initialize_database()
    events = load_raw_events(args.input)

    with get_connection() as connection:
        insert_raw_events(connection, events)

    print(f"Ingested {len(events)} raw events from {args.input}")


if __name__ == "__main__":
    main()
