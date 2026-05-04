from __future__ import annotations

"""Structured memory extraction from normalized raw events."""

from app.llm.provider import LLMProvider, get_llm_provider
from app.core.context_assembler import ExtractionContext
from app.core.post_processor import ExtractionPostProcessor
from app.storage.models import DiscussionWindow, MemoryObject, RawEvent, TopicAssignment


class MemoryExtractor:
    """Convert a window of RawEvents into validated MemoryObjects."""

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm or get_llm_provider()
        self.post_processor = ExtractionPostProcessor()

    def extract(
        self,
        events: list[RawEvent],
        context: ExtractionContext | None = None,
    ) -> list[MemoryObject]:
        """Run extraction and validate every candidate with Pydantic.

        When *context* is provided, bridge events and existing memory titles
        are passed to the LLM so it avoids redundant extraction.
        """
        event_dicts = [event.model_dump() for event in events]
        extraction_hints: dict | None = None
        if context:
            extraction_hints = {}
            if context.bridge_events:
                extraction_hints["bridge_context"] = [
                    {"actor_name": e.actor_name, "content": e.content}
                    for e in context.bridge_events
                ]
            if context.topic_history:
                extraction_hints["recent_topics"] = context.topic_history
            if context.recent_memory_titles:
                extraction_hints["existing_memory_titles"] = context.recent_memory_titles

        candidates = self.llm.extract_memories(event_dicts, extraction_hints=extraction_hints)
        extracted_memories: list[MemoryObject] = []
        for candidate in candidates:
            try:
                extracted_memories.append(MemoryObject(**candidate))
            except Exception as exc:
                fallback_candidate = dict(candidate)
                fallback_candidate.setdefault("memory_type", "fact")
                fallback_candidate.setdefault("scope", "project")
                fallback_candidate.setdefault("project_id", events[0].project_id if events else None)
                fallback_candidate.setdefault("tenant_id", events[0].tenant_id if events else None)
                fallback_candidate.setdefault("valid_time_start", events[0].valid_time_start if events else "")
                fallback_candidate.setdefault("transaction_time", events[-1].transaction_time if events else "")
                fallback_candidate.setdefault("source_event_ids", [event.event_id for event in events])
                fallback_candidate["status"] = "pending"
                fallback_candidate["title"] = fallback_candidate.get("title", "Pending memory candidate")
                fallback_candidate["content"] = fallback_candidate.get("content", str(exc))
                extracted_memories.append(MemoryObject(**fallback_candidate))
        return extracted_memories

    def extract_from_windows(
        self,
        windows: list[DiscussionWindow],
        event_index: dict[str, RawEvent],
        topic_assignments: dict[str, TopicAssignment] | None = None,
        extraction_contexts: dict[str, ExtractionContext] | None = None,
    ) -> list[MemoryObject]:
        """Extract memories window by window to keep provider inputs bounded."""
        extracted_memories: list[MemoryObject] = []
        topic_assignments = topic_assignments or {}
        extraction_contexts = extraction_contexts or {}

        for window in windows:
            window_events = [event_index[event_id] for event_id in window.event_ids if event_id in event_index]
            if not window_events:
                continue

            ctx = extraction_contexts.get(window.window_id)
            window_memories = self.extract(window_events, context=ctx)
            assignment = topic_assignments.get(window.window_id)
            for memory in window_memories:
                if not memory.topic:
                    if assignment is not None:
                        memory.topic = assignment.label
                    elif window.topic_hint:
                        memory.topic = window.topic_hint

            extracted_memories.extend(
                self.post_processor.process_window_memories(
                    window_memories,
                    window=window,
                    assignment=assignment,
                )
            )

        return extracted_memories
