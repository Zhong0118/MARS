from __future__ import annotations

"""Assembles enriched extraction context for each window.

Provides the LLM Extractor with cross-window awareness: bridge events from
the previous window, recent topic labels, and titles of existing memories
on the same topic — so the extractor can avoid redundant extraction and
leverage cross-window continuity.
"""

from dataclasses import dataclass, field

from app.storage.models import DiscussionWindow, MemoryObject, RawEvent


@dataclass
class ExtractionContext:
    """Enriched context passed alongside a window to the extractor."""

    current_window: DiscussionWindow
    bridge_events: list[RawEvent] = field(default_factory=list)
    topic_history: list[str] = field(default_factory=list)
    recent_memory_titles: list[str] = field(default_factory=list)


class ContextAssembler:
    """Builds ExtractionContext for each window in a stream."""

    def __init__(
        self,
        *,
        bridge_count: int = 3,
        topic_history_limit: int = 3,
        memory_title_limit: int = 3,
    ) -> None:
        self.bridge_count = bridge_count
        self.topic_history_limit = topic_history_limit
        self.memory_title_limit = memory_title_limit

    def assemble(
        self,
        windows: list[DiscussionWindow],
        event_index: dict[str, RawEvent],
        existing_memories: list[MemoryObject] | None = None,
    ) -> list[ExtractionContext]:
        """Build ExtractionContext for each window in order."""
        existing_memories = existing_memories or []
        topic_labels_seen: list[str] = []
        contexts: list[ExtractionContext] = []

        for i, window in enumerate(windows):
            bridge = self._get_bridge_events(windows, i, event_index)
            topic_history = list(topic_labels_seen[-self.topic_history_limit:])
            memory_titles = self._get_recent_memory_titles(
                window, existing_memories
            )
            contexts.append(
                ExtractionContext(
                    current_window=window,
                    bridge_events=bridge,
                    topic_history=topic_history,
                    recent_memory_titles=memory_titles,
                )
            )
            if window.topic_hint and (
                not topic_labels_seen or topic_labels_seen[-1] != window.topic_hint
            ):
                topic_labels_seen.append(window.topic_hint)

        return contexts

    def _get_bridge_events(
        self,
        windows: list[DiscussionWindow],
        current_index: int,
        event_index: dict[str, RawEvent],
    ) -> list[RawEvent]:
        if current_index == 0:
            return []
        prev_window = windows[current_index - 1]
        tail_ids = prev_window.event_ids[-self.bridge_count:]
        return [event_index[eid] for eid in tail_ids if eid in event_index]

    def _get_recent_memory_titles(
        self,
        window: DiscussionWindow,
        existing_memories: list[MemoryObject],
    ) -> list[str]:
        if not window.topic_hint or not existing_memories:
            return []
        matching = [
            m.title
            for m in existing_memories
            if m.topic == window.topic_hint and m.status == "active"
        ]
        return matching[-self.memory_title_limit:]
