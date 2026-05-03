from __future__ import annotations

"""Developer script for inspecting provider outputs on one sample file."""

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.connectors.sample_loader import load_raw_events
from app.core.topic_tracker import TopicTracker
from app.core.window_builder import WindowBuilder
from app.llm.provider import get_llm_provider


def build_parser() -> argparse.ArgumentParser:
    """Build CLI args for provider inspection."""
    parser = argparse.ArgumentParser(description="Inspect mock or GLM provider outputs on one sample file.")
    parser.add_argument("--input", required=True, help="Path to sample chat JSON.")
    return parser


def main() -> None:
    """Print the provider name, windows, topics, and extracted raw JSON output."""
    args = build_parser().parse_args()
    provider = get_llm_provider()
    events = load_raw_events(args.input)
    windows = WindowBuilder().build_windows(events)
    tracker = TopicTracker()
    previous_assignments = []

    print(f"provider: {type(provider).__name__}")
    print(f"event_count: {len(events)}")
    print(f"window_count: {len(windows)}")

    for index, window in enumerate(windows, start=1):
        assignment = tracker.assign_topic(window, previous_assignments)
        previous_assignments.append(assignment)
        print(f"\nwindow[{index}]")
        print(f"  event_ids: {', '.join(window.event_ids)}")
        print(f"  topic_hint: {window.topic_hint}")
        print(f"  assigned_topic: {assignment.label}")
        print(f"  assignment_reason: {assignment.assignment_reason}")
        print(f"  raw_summary: {window.raw_summary}")
        window_events = [event.model_dump() for event in events if event.event_id in window.event_ids]
        extracted = provider.extract_memories(window_events)
        print("  extracted_json:")
        print(json.dumps(extracted, ensure_ascii=False, indent=2))

    provider_name = type(provider).__name__
    print(f"\nselected_provider_class: {provider_name}")


if __name__ == "__main__":
    main()
