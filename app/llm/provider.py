from __future__ import annotations

"""Deterministic local LLM provider used by the MVP.

The real system will eventually swap this layer for an API or local model.
For now we keep extraction logic stable and reproducible for the bundled
sample cases so the rest of the memory pipeline can be validated.
MockLLM，给样例返回稳定 memory
"""

from typing import Any


class MockLLM:
    """Deterministic placeholder provider for local MVP phases."""

    def extract_memories(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return structured memory candidates for known sample scenarios."""
        if not events:
            return []

        project_id = events[0].get("project_id")
        tenant_id = events[0].get("tenant_id")
        event_ids = [str(event["event_id"]) for event in events]
        combined_text = " ".join(str(event.get("content", "")) for event in events).lower()
        first_time = str(events[0].get("valid_time_start") or events[0].get("transaction_time"))
        last_time = str(events[-1].get("transaction_time") or events[-1].get("valid_time_start"))

        if "streamlit" in combined_text and "vue plus fastapi" in combined_text and "correction:" not in combined_text:
            return [
                {
                    "memory_id": f"mem_{project_id}_tech_route_v1",
                    "version_group_id": f"vg_{project_id}_tech_route",
                    "memory_type": "decision",
                    "scope": "project",
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "topic": "tech_route",
                    "title": "Phase One Demo Uses Streamlit",
                    "content": "Use Streamlit for phase one so the demo ships quickly, and revisit Vue + FastAPI later.",
                    "rationale": [
                        "The timeline is tight.",
                        "The current data processing stack is already Python-heavy.",
                        "Streamlit is faster for a first demo.",
                    ],
                    "objections": [
                        "Vue + FastAPI may be better for a more engineered long-term frontend.",
                    ],
                    "tags": ["demo", "frontend", "tech_route"],
                    "status": "active",
                    "version": 1,
                    "confidence": 0.92,
                    "importance": 4,
                    "valid_time_start": first_time,
                    "valid_time_end": None,
                    "transaction_time": last_time,
                    "source_event_ids": event_ids,
                }
            ]

        if "correction:" in combined_text and "vue plus fastapi" in combined_text:
            return [
                {
                    "memory_id": f"mem_{project_id}_tech_route_v2",
                    "version_group_id": f"vg_{project_id}_tech_route",
                    "memory_type": "decision",
                    "scope": "project",
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "topic": "tech_route",
                    "title": "Phase One Moves to Vue + FastAPI",
                    "content": "The formal phase-one demo should use Vue + FastAPI instead of Streamlit.",
                    "rationale": [
                        "The formal demo needs a more engineered frontend.",
                    ],
                    "objections": [
                        "This is slower than the earlier Streamlit-first plan.",
                    ],
                    "tags": ["demo", "frontend", "tech_route", "correction"],
                    "status": "active",
                    "version": 2,
                    "confidence": 0.95,
                    "importance": 5,
                    "valid_time_start": first_time,
                    "valid_time_end": None,
                    "transaction_time": last_time,
                    "source_event_ids": event_ids,
                }
            ]

        return []

    def judge_relation(self, new_memory: dict[str, Any], existing_memories: list[dict[str, Any]]) -> dict[str, Any]:
        """Return a simple deterministic relation judgment for MVP samples."""
        new_title = str(new_memory.get("title", "")).lower()
        existing_titles = " ".join(str(memory.get("title", "")).lower() for memory in existing_memories)

        if "vue + fastapi" in new_title and "streamlit" in existing_titles:
            return {
                "relation": "supersedes",
                "reason": "The new statement explicitly replaces the earlier Streamlit-first plan.",
                "confidence": 0.95,
            }

        if new_title and new_title in existing_titles:
            return {
                "relation": "duplicate",
                "reason": "The candidate repeats an existing memory title.",
                "confidence": 0.9,
            }

        return {"relation": "unrelated", "reason": "MockLLM placeholder.", "confidence": 1.0}
