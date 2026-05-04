from __future__ import annotations

"""Discussion window construction for MARS memory extraction.

v2 uses SessionTracker annotations (new_topic / continuation / resume / drift)
as the primary splitting signal, with thread/chat boundaries and a token budget
as hard constraints. The old rule-stack (shift markers, topic marker divergence,
fixed message cap) is removed in favor of session-level topic awareness.
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
    "max_messages_per_window": 12,
    "lexical_overlap_threshold": 0.2,
    "force_thread_boundary": True,
    "token_budget": 2000,
    "topic_markers": DEFAULT_TOPIC_MARKERS,
    "shift_markers": DEFAULT_SHIFT_MARKERS,
}


@dataclass(slots=True)
class WindowBuildConfig:
    """Configurable heuristics for splitting raw events into candidate windows."""

    max_gap_minutes: int = 30
    max_messages_per_window: int = 12
    lexical_overlap_threshold: float = 0.2
    force_thread_boundary: bool = True
    token_budget: int = 2000
    topic_markers: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_TOPIC_MARKERS))
    shift_markers: list[str] = field(default_factory=lambda: list(DEFAULT_SHIFT_MARKERS))


class WindowBuilder:
    """Build candidate discussion windows using SessionTracker annotations.

    v2 flow: SessionTracker annotates each event with a topic state, then
    WindowBuilder groups events into windows based on those annotations plus
    hard boundaries (thread, chat, token budget).
    """

    def __init__(self, config: WindowBuildConfig | None = None) -> None:
        if config is not None:
            self.config = config
            return

        loaded = load_json_config("window_builder_rules.json", DEFAULT_WINDOW_CONFIG)
        topic_markers = load_topic_markers() or {key: list(value) for key, value in loaded.get("topic_markers", DEFAULT_TOPIC_MARKERS).items()}
        self.config = WindowBuildConfig(
            max_gap_minutes=int(loaded["max_gap_minutes"]),
            max_messages_per_window=int(loaded.get("max_messages_per_window", 12)),
            lexical_overlap_threshold=float(loaded["lexical_overlap_threshold"]),
            force_thread_boundary=bool(loaded["force_thread_boundary"]),
            token_budget=int(loaded.get("token_budget", 2000)),
            topic_markers=topic_markers,
            shift_markers=list(loaded["shift_markers"]),
        )

    def build_windows(self, events: list[RawEvent], annotations: dict[str, "EventTopicAnnotation"] | None = None) -> list[DiscussionWindow]:
        """Split a chat event stream into candidate windows.

        When *annotations* is provided (v2 mode), topic_state drives splitting.
        When omitted, falls back to the v1 heuristic rules for backward compat.
        """
        if not events:
            return []

        sorted_events = sorted(events, key=lambda event: (event.valid_time_start, event.transaction_time, event.event_id))

        if annotations is None:
            return self._build_windows_v1(sorted_events)
        return self._build_windows_v2(sorted_events, annotations)

    def _build_windows_v2(
        self,
        sorted_events: list[RawEvent],
        annotations: dict[str, "EventTopicAnnotation"],
    ) -> list[DiscussionWindow]:
        """Topic-state-driven window construction."""
        from app.core.session_tracker import EventTopicAnnotation  # noqa: F811

        windows: list[DiscussionWindow] = []
        current_events: list[RawEvent] = []
        current_token_count = 0
        current_topic_label: str | None = None
        pending_split_reason = "stream_start"

        for event in sorted_events:
            annotation = annotations.get(event.event_id)
            event_tokens = len(tokenize_text(event.content))

            if not current_events:
                current_events = [event]
                current_token_count = event_tokens
                current_topic_label = annotation.topic_label if annotation else None
                continue

            prev_event = current_events[-1]
            hard_split = self._check_hard_boundary(prev_event, event)
            if hard_split:
                windows.append(self._build_window(current_events, split_reason=pending_split_reason, topic_label=current_topic_label))
                current_events = [event]
                current_token_count = event_tokens
                current_topic_label = annotation.topic_label if annotation else None
                pending_split_reason = hard_split
                continue

            if annotation is None:
                current_events.append(event)
                current_token_count += event_tokens
                continue

            topic_state = annotation.topic_state

            if topic_state == "new_topic":
                windows.append(self._build_window(current_events, split_reason=pending_split_reason, topic_label=current_topic_label))
                current_events = [event]
                current_token_count = event_tokens
                current_topic_label = annotation.topic_label
                pending_split_reason = "new_topic"

            elif topic_state == "resume":
                windows.append(self._build_window(current_events, split_reason=pending_split_reason, topic_label=current_topic_label))
                current_events = [event]
                current_token_count = event_tokens
                current_topic_label = annotation.topic_label
                pending_split_reason = "topic_resume"

            elif topic_state == "continuation":
                if current_token_count + event_tokens > self.config.token_budget:
                    windows.append(self._build_window(current_events, split_reason=pending_split_reason, topic_label=current_topic_label))
                    current_events = [event]
                    current_token_count = event_tokens
                    pending_split_reason = "token_budget"
                elif len(current_events) >= self.config.max_messages_per_window:
                    windows.append(self._build_window(current_events, split_reason=pending_split_reason, topic_label=current_topic_label))
                    current_events = [event]
                    current_token_count = event_tokens
                    pending_split_reason = "message_cap"
                else:
                    current_events.append(event)
                    current_token_count += event_tokens

            elif topic_state == "drift":
                if current_token_count + event_tokens > self.config.token_budget:
                    windows.append(self._build_window(current_events, split_reason=pending_split_reason, topic_label=current_topic_label))
                    current_events = [event]
                    current_token_count = event_tokens
                    pending_split_reason = "token_budget"
                else:
                    current_events.append(event)
                    current_token_count += event_tokens

        if current_events:
            windows.append(self._build_window(current_events, split_reason=pending_split_reason, topic_label=current_topic_label))

        return windows

    def _build_windows_v1(self, sorted_events: list[RawEvent]) -> list[DiscussionWindow]:
        """Legacy v1 heuristic splitting for backward compatibility."""
        windows: list[DiscussionWindow] = []
        current_events: list[RawEvent] = []
        pending_split_reason = "stream_start"

        for event in sorted_events:
            if not current_events:
                current_events = [event]
                continue

            previous_event = current_events[-1]
            split_reason = self._should_split_v1(current_events, previous_event, event)
            if split_reason is None:
                current_events.append(event)
                continue

            windows.append(self._build_window(current_events, split_reason=pending_split_reason))
            current_events = [event]
            pending_split_reason = split_reason

        if current_events:
            windows.append(self._build_window(current_events, split_reason=pending_split_reason))

        return windows

    def _check_hard_boundary(self, prev_event: RawEvent, next_event: RawEvent) -> str | None:
        """Hard boundaries that always force a split regardless of topic state."""
        if self.config.force_thread_boundary and prev_event.thread_id != next_event.thread_id:
            if prev_event.thread_id or next_event.thread_id:
                return "thread_boundary"
        if prev_event.chat_id != next_event.chat_id:
            return "chat_boundary"
        return None

    def _should_split_v1(
        self,
        current_events: list[RawEvent],
        previous_event: RawEvent,
        next_event: RawEvent,
    ) -> str | None:
        """v1 split rules kept for backward compatibility."""
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

    def _build_window(self, events: list[RawEvent], split_reason: str, topic_label: str | None = None) -> DiscussionWindow:
        """Create a DiscussionWindow record from a finalized event segment."""
        return DiscussionWindow(
            tenant_id=events[0].tenant_id,
            project_id=events[0].project_id,
            chat_id=events[0].chat_id,
            thread_id=events[0].thread_id,
            topic_hint=topic_label or infer_topic_hint(events, self.config.topic_markers),
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


def tokenize_query(query: str) -> list[str]:
    """Tokenize mixed Chinese/English text into a list for retrieval scoring."""
    lowered = query.lower()
    tokens = re.findall(r"[a-z0-9_+\-#.]+|[\u4e00-\u9fff]+", lowered)
    return [token for token in tokens if token.strip()]


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
