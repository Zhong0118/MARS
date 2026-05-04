from __future__ import annotations

"""Session-level topic state machine for event streams.

Tracks topic transitions across a chat's event stream, producing per-event
annotations (new_topic / continuation / resume / drift) that downstream
WindowBuilder v2 uses for intelligent window splitting.

Pure rule-based + token overlap. No LLM calls.
"""

from dataclasses import dataclass, field
from typing import Literal

from app.core.window_builder import (
    tokenize_text,
    token_overlap_ratio,
    minutes_gap,
    infer_topic_hint,
    DEFAULT_TOPIC_MARKERS,
)
from app.storage.models import RawEvent


TopicStatus = Literal["active", "paused", "closed"]
EventTopicState = Literal["new_topic", "continuation", "resume", "drift"]


@dataclass
class TopicState:
    """Tracked topic within a session."""

    label: str
    key_tokens: set[str]
    last_seen_time: str
    event_count: int
    status: TopicStatus = "active"
    topic_index: int = 0


@dataclass
class EventTopicAnnotation:
    """Per-event annotation produced by the SessionTracker."""

    event_id: str
    topic_state: EventTopicState
    matched_topic: str | None
    confidence: float
    topic_label: str


@dataclass(slots=True)
class SessionTrackerConfig:
    """Tunable thresholds for session-level topic tracking."""

    continuation_threshold: float = 0.15
    resume_threshold: float = 0.25
    drift_threshold: float = 0.08
    time_gap_new_topic_minutes: float = 60.0
    topic_markers: dict[str, list[str]] = field(
        default_factory=lambda: dict(DEFAULT_TOPIC_MARKERS)
    )
    min_tokens_for_comparison: int = 2


class SessionTracker:
    """Maintains a topic state machine over one chat's event stream.

    Each call to ``annotate`` ingests one event and returns an annotation
    describing how that event relates to the topic history.
    """

    def __init__(self, config: SessionTrackerConfig | None = None) -> None:
        self.config = config or SessionTrackerConfig()
        self.topics: list[TopicState] = []
        self.current_topic: TopicState | None = None
        self._topic_counter = 0

    def annotate(self, event: RawEvent) -> EventTopicAnnotation:
        """Classify one event against the running topic state."""
        event_tokens = tokenize_text(event.content)
        event_time = event.valid_time_start or event.transaction_time

        if self.current_topic is None:
            return self._start_new_topic(event, event_tokens, event_time)

        current_overlap = self._overlap_with_topic(event_tokens, self.current_topic)

        time_since_current = minutes_gap(
            self.current_topic.last_seen_time, event_time
        )
        if time_since_current > self.config.time_gap_new_topic_minutes:
            resume_topic, resume_overlap = self._find_best_resume(
                event_tokens, exclude=self.current_topic
            )
            if resume_topic and resume_overlap >= self.config.resume_threshold:
                return self._resume_topic(event, resume_topic, resume_overlap, event_time)
            return self._start_new_topic(event, event_tokens, event_time)

        resume_topic, resume_overlap = self._find_best_resume(
            event_tokens, exclude=self.current_topic
        )
        if (
            resume_topic
            and resume_overlap >= self.config.resume_threshold
            and resume_overlap > current_overlap + 0.1
        ):
            return self._resume_topic(event, resume_topic, resume_overlap, event_time)

        if current_overlap >= self.config.continuation_threshold:
            return self._continue_topic(event, event_tokens, current_overlap, event_time)

        marker_hint = infer_topic_hint([event], self.config.topic_markers)
        if marker_hint and self.current_topic.label != marker_hint:
            for topic in self.topics:
                if topic.label == marker_hint and topic is not self.current_topic:
                    return self._resume_topic(event, topic, 0.5, event_time)
            return self._start_new_topic(
                event, event_tokens, event_time, label_hint=marker_hint
            )

        if current_overlap >= self.config.drift_threshold:
            return self._drift(event, event_tokens, current_overlap, event_time)

        return self._start_new_topic(event, event_tokens, event_time)

    def annotate_batch(self, events: list[RawEvent]) -> list[EventTopicAnnotation]:
        """Annotate a full event stream in order."""
        sorted_events = sorted(
            events,
            key=lambda e: (e.valid_time_start, e.transaction_time, e.event_id),
        )
        return [self.annotate(event) for event in sorted_events]

    def _overlap_with_topic(
        self, event_tokens: set[str], topic: TopicState
    ) -> float:
        if len(event_tokens) < self.config.min_tokens_for_comparison:
            return 0.3
        if len(topic.key_tokens) < self.config.min_tokens_for_comparison:
            return 0.3
        return token_overlap_ratio(event_tokens, topic.key_tokens)

    def _find_best_resume(
        self, event_tokens: set[str], *, exclude: TopicState | None = None
    ) -> tuple[TopicState | None, float]:
        best_topic: TopicState | None = None
        best_overlap = 0.0
        for topic in self.topics:
            if topic is exclude:
                continue
            if topic.status == "closed":
                continue
            overlap = self._overlap_with_topic(event_tokens, topic)
            if overlap > best_overlap:
                best_overlap = overlap
                best_topic = topic
        return best_topic, best_overlap

    def _make_label(self, event_tokens: set[str], event: RawEvent, label_hint: str | None = None) -> str:
        if label_hint:
            return label_hint
        marker_hint = infer_topic_hint([event], self.config.topic_markers)
        if marker_hint:
            return marker_hint
        self._topic_counter += 1
        return f"session_topic_{self._topic_counter}"

    def _start_new_topic(
        self,
        event: RawEvent,
        event_tokens: set[str],
        event_time: str,
        label_hint: str | None = None,
    ) -> EventTopicAnnotation:
        if self.current_topic is not None:
            self.current_topic.status = "paused"
        label = self._make_label(event_tokens, event, label_hint)
        new_topic = TopicState(
            label=label,
            key_tokens=set(event_tokens),
            last_seen_time=event_time,
            event_count=1,
            status="active",
            topic_index=len(self.topics),
        )
        self.topics.append(new_topic)
        self.current_topic = new_topic
        return EventTopicAnnotation(
            event_id=event.event_id,
            topic_state="new_topic",
            matched_topic=None,
            confidence=0.6,
            topic_label=label,
        )

    def _continue_topic(
        self,
        event: RawEvent,
        event_tokens: set[str],
        overlap: float,
        event_time: str,
    ) -> EventTopicAnnotation:
        assert self.current_topic is not None
        self.current_topic.key_tokens.update(event_tokens)
        self.current_topic.last_seen_time = event_time
        self.current_topic.event_count += 1
        return EventTopicAnnotation(
            event_id=event.event_id,
            topic_state="continuation",
            matched_topic=self.current_topic.label,
            confidence=min(1.0, 0.5 + overlap),
            topic_label=self.current_topic.label,
        )

    def _resume_topic(
        self,
        event: RawEvent,
        topic: TopicState,
        overlap: float,
        event_time: str,
    ) -> EventTopicAnnotation:
        if self.current_topic is not None:
            self.current_topic.status = "paused"
        topic.status = "active"
        topic.last_seen_time = event_time
        topic.event_count += 1
        topic.key_tokens.update(tokenize_text(event.content))
        self.current_topic = topic
        return EventTopicAnnotation(
            event_id=event.event_id,
            topic_state="resume",
            matched_topic=topic.label,
            confidence=min(1.0, 0.4 + overlap),
            topic_label=topic.label,
        )

    def _drift(
        self,
        event: RawEvent,
        event_tokens: set[str],
        overlap: float,
        event_time: str,
    ) -> EventTopicAnnotation:
        assert self.current_topic is not None
        self.current_topic.key_tokens.update(event_tokens)
        self.current_topic.last_seen_time = event_time
        self.current_topic.event_count += 1
        return EventTopicAnnotation(
            event_id=event.event_id,
            topic_state="drift",
            matched_topic=self.current_topic.label,
            confidence=min(1.0, 0.3 + overlap),
            topic_label=self.current_topic.label,
        )
