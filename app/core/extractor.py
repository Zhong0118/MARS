from __future__ import annotations

"""Structured memory extraction from normalized raw events.
调 MockLLM，并把返回结果校验成 MemoryObject
"""

from app.llm.provider import MockLLM
from app.storage.models import MemoryObject, RawEvent


class MemoryExtractor:
    """Convert a window of RawEvents into validated MemoryObjects."""

    def __init__(self, llm: MockLLM | None = None) -> None:
        self.llm = llm or MockLLM()

    def extract(self, events: list[RawEvent]) -> list[MemoryObject]:
        """Run deterministic extraction and validate every candidate with Pydantic."""
        candidates = self.llm.extract_memories([event.model_dump() for event in events])
        extracted_memories: list[MemoryObject] = []
        for candidate in candidates:
            try:
                extracted_memories.append(MemoryObject(**candidate))
            except Exception as exc:
                fallback_candidate = dict(candidate)
                fallback_candidate["status"] = "pending"
                fallback_candidate["title"] = fallback_candidate.get("title", "Pending memory candidate")
                fallback_candidate["content"] = fallback_candidate.get("content", str(exc))
                extracted_memories.append(MemoryObject(**fallback_candidate))
        return extracted_memories
