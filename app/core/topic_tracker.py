from __future__ import annotations

"""Lightweight topic assignment built on top of discussion windows.

The MVP version is heuristic-first. It keeps the implementation explainable and
configurable, while now allowing an LLM fallback for ambiguous windows.
"""

from dataclasses import dataclass, field

from app.config import load_json_config, load_topic_markers
from app.llm.provider import LLMProvider, get_llm_provider
from app.core.window_builder import DEFAULT_TOPIC_MARKERS, tokenize_text, token_overlap_ratio
from app.storage.models import DiscussionWindow, TopicAssignment


DEFAULT_TOPIC_TRACKER_CONFIG = {
    "topic_markers": DEFAULT_TOPIC_MARKERS,
    "reuse_threshold": 0.35,
    "new_topic_prefix": "topic",
}


@dataclass(slots=True)
class TopicTrackerConfig:
    """Configurable defaults for coarse topic tracking."""

    topic_markers: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_TOPIC_MARKERS))
    reuse_threshold: float = 0.35
    new_topic_prefix: str = "topic"


class TopicTracker:
    """Assign windows to coarse topic labels using marker hits and lexical overlap."""

    def __init__(self, config: TopicTrackerConfig | None = None, llm: LLMProvider | None = None) -> None:
        if config is not None:
            self.config = config
        else:
            loaded = load_json_config("topic_tracker_rules.json", DEFAULT_TOPIC_TRACKER_CONFIG)
            topic_markers = load_topic_markers() or {key: list(value) for key, value in loaded.get("topic_markers", DEFAULT_TOPIC_MARKERS).items()}
            self.config = TopicTrackerConfig(
                topic_markers=topic_markers,
                reuse_threshold=float(loaded["reuse_threshold"]),
                new_topic_prefix=str(loaded["new_topic_prefix"]),
            )
        self.llm = llm or get_llm_provider()

    def assign_topic(
        self,
        window: DiscussionWindow,
        previous_assignments: list[TopicAssignment] | None = None,
    ) -> TopicAssignment:
        """Assign a topic to one window based on markers and prior topic history."""
        previous_assignments = previous_assignments or []
        marker_assignment = self._assign_by_markers(window)
        if marker_assignment is not None:
            return marker_assignment

        llm_assignment = self._assign_by_llm(window, previous_assignments)
        if llm_assignment is not None:
            return llm_assignment

        if window.topic_hint:
            return TopicAssignment(
                label=window.topic_hint,
                confidence=0.7,
                assignment_reason="window_topic_hint",
            )

        overlap_assignment = self._assign_by_previous_overlap(window, previous_assignments)
        if overlap_assignment is not None:
            return overlap_assignment

        return TopicAssignment(
            label=f"{self.config.new_topic_prefix}_{window.window_id}",
            confidence=0.4,
            assignment_reason="fallback_new_topic",
        )

    def _assign_by_llm(
        self,
        window: DiscussionWindow,
        previous_assignments: list[TopicAssignment],
    ) -> TopicAssignment | None:
        """Let the provider classify ambiguous windows when marker rules are weak."""
        try:
            payload = self.llm.classify_topic(
                {
                    "window_id": window.window_id,
                    "topic_hint": window.topic_hint,
                    "raw_summary": window.raw_summary,
                    "split_reason": window.split_reason,
                    "event_count": len(window.event_ids),
                },
                candidate_topics=list(self.config.topic_markers.keys()),
                previous_topics=[assignment.label for assignment in previous_assignments[-5:]],
            )
        except Exception:
            return None

        confidence = float(payload.get("confidence", 0.0))
        if confidence < 0.55:
            return None

        canonical = str(payload.get("canonical_topic", "") or "").strip()
        suggested = str(payload.get("suggested_label", "") or "").strip()
        label = canonical if canonical and canonical != "general" else suggested
        if not label:
            return None

        return TopicAssignment(
            label=label,
            confidence=confidence,
            assignment_reason="llm_topic_classification",
            matched_markers=[str(payload.get("reason", "semantic_classification"))],
        )

    def _assign_by_markers(self, window: DiscussionWindow) -> TopicAssignment | None:
        """Try topic assignment from configured marker dictionaries."""
        combined_text = (window.raw_summary or "").lower()
        best_topic: str | None = None
        matched_markers: list[str] = []

        for topic, markers in self.config.topic_markers.items():
            current_matches = [marker for marker in markers if marker.lower() in combined_text]
            if len(current_matches) > len(matched_markers):
                best_topic = topic
                matched_markers = current_matches

        if best_topic is None or not matched_markers:
            return None

        confidence = min(1.0, 0.5 + 0.1 * len(matched_markers))
        return TopicAssignment(
            label=best_topic,
            confidence=confidence,
            assignment_reason="topic_markers",
            matched_markers=matched_markers,
        )

    def _assign_by_previous_overlap(
        self,
        window: DiscussionWindow,
        previous_assignments: list[TopicAssignment],
    ) -> TopicAssignment | None:
        """Reuse an earlier topic when lexical overlap is sufficiently high."""
        if not previous_assignments:
            return None

        current_tokens = tokenize_text(window.raw_summary or "")
        best_assignment: TopicAssignment | None = None
        best_overlap = 0.0

        for assignment in previous_assignments:
            previous_tokens = tokenize_text(" ".join(assignment.matched_markers) or assignment.label)
            overlap = token_overlap_ratio(current_tokens, previous_tokens)
            if overlap > best_overlap:
                best_overlap = overlap
                best_assignment = assignment

        if best_assignment is None or best_overlap < self.config.reuse_threshold:
            return None

        return TopicAssignment(
            label=best_assignment.label,
            confidence=min(1.0, max(best_overlap, 0.45)),
            assignment_reason="previous_topic_overlap",
            matched_markers=best_assignment.matched_markers,
        )
