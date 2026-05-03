from __future__ import annotations

"""Heuristic discussion window construction for local MVP experiments.

This module does not try to solve full conversational segmentation.
It provides a transparent, configurable first pass that groups nearby events
into candidate windows before extraction or topic tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
import re

from app.config import load_json_config, load_topic_markers
from app.storage.models import DiscussionWindow, RawEvent


DEFAULT_TOPIC_MARKERS: dict[str, list[str]] = {
    "tech_route": ["streamlit", "vue", "fastapi", "frontend", "backend", "tech route", "architecture", "react", "ui", "api", "stack"],
    "timeline": ["deadline", "schedule", "timeline", "milestone", "eta", "review", "ship", "launch", "delivery"],
    "risk": ["risk", "blocker", "issue", "problem", "failure", "deploy", "deployment", "incident", "unstable"],
    "reporting": ["report", "summary", "weekly update", "status update", "slide", "deck", "recap"],
    "onboarding": ["onboarding", "new member", "handoff", "context", "background"],
    "ownership": ["owner", "ownership", "follow up", "follow-up", "responsible", "take care"],
}

DEFAULT_SHIFT_MARKERS = [
    "by the way",
    "back to",
    "switch topic",
    "another topic",
    "correction:",
    "however",
    "also",
    "in addition",
    "meanwhile",
    "separately",
    "for onboarding",
    "for reporting",
]

DEFAULT_WINDOW_CONFIG = {
    "max_gap_minutes": 30,
    "max_messages_per_window": 8,
    "lexical_overlap_threshold": 0.2,
    "force_thread_boundary": True,
    "topic_markers": DEFAULT_TOPIC_MARKERS,
    "shift_markers": DEFAULT_SHIFT_MARKERS,
}


@dataclass(slots=True)
class WindowBuildConfig:
    """Configurable heuristics for splitting raw events into candidate windows."""

    max_gap_minutes: int = 30
    max_messages_per_window: int = 8
    lexical_overlap_threshold: float = 0.2
    force_thread_boundary: bool = True
    topic_markers: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_TOPIC_MARKERS))
    shift_markers: list[str] = field(default_factory=lambda: list(DEFAULT_SHIFT_MARKERS))


class WindowBuilder:
    """Build candidate discussion windows using transparent rule-based heuristics."""

    def __init__(self, config: WindowBuildConfig | None = None) -> None:
        if config is not None:
            self.config = config
            return

        loaded = load_json_config("window_builder_rules.json", DEFAULT_WINDOW_CONFIG)
        topic_markers = load_topic_markers() or {key: list(value) for key, value in loaded.get("topic_markers", DEFAULT_TOPIC_MARKERS).items()}
        self.config = WindowBuildConfig(
            max_gap_minutes=int(loaded["max_gap_minutes"]),
            max_messages_per_window=int(loaded["max_messages_per_window"]),
            lexical_overlap_threshold=float(loaded["lexical_overlap_threshold"]),
            force_thread_boundary=bool(loaded["force_thread_boundary"]),
            topic_markers=topic_markers,
            shift_markers=list(loaded["shift_markers"]),
        )

    def build_windows(self, events: list[RawEvent]) -> list[DiscussionWindow]:
        """Split a chat event stream into candidate windows for later extraction."""
        if not events:
            return []

        sorted_events = sorted(events, key=lambda event: (event.valid_time_start, event.transaction_time, event.event_id))
        windows: list[DiscussionWindow] = []
        current_events: list[RawEvent] = []
        pending_split_reason = "stream_start"

        for event in sorted_events:
            if not current_events:
                current_events = [event]
                continue

            previous_event = current_events[-1]
            split_reason = self._should_split(current_events, previous_event, event)
            if split_reason is None:
                current_events.append(event)
                continue

            windows.append(self._build_window(current_events, split_reason=pending_split_reason))
            current_events = [event]
            pending_split_reason = split_reason

        if current_events:
            windows.append(self._build_window(current_events, split_reason=pending_split_reason))

        return windows

    def _should_split(
        self,
        current_events: list[RawEvent],
        previous_event: RawEvent,
        next_event: RawEvent,
    ) -> str | None:
        """Return a split reason when the next event should start a new window."""
        if self.config.force_thread_boundary and previous_event.thread_id != next_event.thread_id:
            if previous_event.thread_id or next_event.thread_id:
                return "thread_boundary"

        if previous_event.chat_id != next_event.chat_id:
            return "chat_boundary"

        if minutes_gap(previous_event.transaction_time, next_event.transaction_time) > self.config.max_gap_minutes:
            return "time_gap"

        if len(current_events) >= self.config.max_messages_per_window:
            return "message_cap"

        next_text = (next_event.content or "").lower()
        if any(marker.lower() in next_text for marker in self.config.shift_markers):
            return "explicit_shift_marker"

        current_tokens = collect_tokens(current_events)
        next_tokens = tokenize_text(next_event.content)
        overlap = token_overlap_ratio(current_tokens, next_tokens)
        if current_tokens and next_tokens and overlap < self.config.lexical_overlap_threshold:
            current_topic = infer_topic_hint(current_events, self.config.topic_markers)
            next_topic = infer_topic_hint([next_event], self.config.topic_markers)
            if current_topic and next_topic and current_topic != next_topic:
                return "topic_marker_shift"

        return None

    def _build_window(self, events: list[RawEvent], split_reason: str) -> DiscussionWindow:
        """Create a DiscussionWindow record from a finalized event segment."""
        return DiscussionWindow(
            tenant_id=events[0].tenant_id,
            project_id=events[0].project_id,
            chat_id=events[0].chat_id,
            thread_id=events[0].thread_id,
            topic_hint=infer_topic_hint(events, self.config.topic_markers),
            split_reason=split_reason,
            start_time=events[0].valid_time_start,
            end_time=events[-1].transaction_time,
            event_ids=[event.event_id for event in events],
            message_count=len(events),
            raw_summary=" | ".join(event.content for event in events if event.content),
        )


def minutes_gap(previous_time: str, next_time: str) -> float:
    """Return the number of minutes between two ISO-8601 timestamps."""
    try:
        previous_dt = datetime.fromisoformat(previous_time)
        next_dt = datetime.fromisoformat(next_time)
    except ValueError:
        return 0.0
    return abs((next_dt - previous_dt).total_seconds()) / 60.0


def tokenize_text(text: str | None) -> set[str]:
    """Tokenize mixed Chinese/English text into a simple lexical set."""
    if not text:
        return set()
    tokens = re.findall(r"[a-z0-9_+\-#.]+|[\u4e00-\u9fff]+", text.lower())
    return {token for token in tokens if token.strip()}


def collect_tokens(events: list[RawEvent]) -> set[str]:
    """Collect a merged token set from a list of raw events."""
    merged: set[str] = set()
    for event in events:
        merged.update(tokenize_text(event.content))
    return merged


def token_overlap_ratio(left: set[str], right: set[str]) -> float:
    """Compute simple overlap ratio between two token sets."""
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    denominator = min(len(left), len(right))
    if denominator == 0:
        return 0.0
    return intersection / denominator


def infer_topic_hint(events: list[RawEvent], topic_markers: dict[str, list[str]]) -> str | None:
    """Infer a coarse topic hint from marker hits across the events."""
    combined_text = " ".join(event.content for event in events if event.content).lower()
    best_topic: str | None = None
    best_score = 0

    for topic, markers in topic_markers.items():
        score = sum(1 for marker in markers if marker.lower() in combined_text)
        if score > best_score:
            best_topic = topic
            best_score = score

    return best_topic
