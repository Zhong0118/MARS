from __future__ import annotations

from typing import Any


class MockLLM:
    """Deterministic placeholder provider for local MVP phases."""

    def extract_memories(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        del events
        return []

    def judge_relation(self, new_memory: dict[str, Any], existing_memories: list[dict[str, Any]]) -> dict[str, Any]:
        del new_memory, existing_memories
        return {"relation": "unrelated", "reason": "MockLLM placeholder.", "confidence": 1.0}
