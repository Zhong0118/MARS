from __future__ import annotations

"""Merge fragmented extracted memories into stronger consolidated candidates.

This layer sits after extraction/post-processing and before reconciliation.
Its job is not to do long-term state transitions, but to reduce noisy
same-batch fragments into fewer, stronger candidates.
"""

from collections import defaultdict
from datetime import datetime

from app.llm.provider import LLMProvider, get_llm_provider
from app.storage.models import MemoryObject


TYPE_PRIORITY = {
    "decision": 5,
    "procedure": 4,
    "risk": 4,
    "fact": 3,
    "preference": 2,
    "episode": 1,
    "skill": 1,
}


class MemoryConsolidator:
    """Collapse related extracted memories before reconciliation."""

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm or get_llm_provider()

    def consolidate(self, memories: list[MemoryObject]) -> list[MemoryObject]:
        """Return fewer, stronger candidates by merging only semantically supportive fragments."""
        if not memories:
            return []

        grouped: dict[tuple[str | None, str | None], list[MemoryObject]] = defaultdict(list)
        for memory in memories:
            grouped[(memory.project_id, memory.version_group_id or memory.topic)].append(memory)

        consolidated: list[MemoryObject] = []
        for group_memories in grouped.values():
            consolidated.extend(self._consolidate_group(group_memories))
        return consolidated

    def _consolidate_group(self, memories: list[MemoryObject]) -> list[MemoryObject]:
        """Merge memories in one topic/version group."""
        if len(memories) <= 1:
            return memories

        ordered = sorted(
            memories,
            key=lambda memory: (
                TYPE_PRIORITY.get(memory.memory_type, 0),
                memory.importance,
                memory.confidence,
                len(memory.source_event_ids),
                memory.transaction_time,
            ),
            reverse=True,
        )

        clusters: list[MemoryObject] = []
        for memory in ordered:
            attached = False
            for index, primary in enumerate(clusters):
                if self._should_merge(primary, memory):
                    clusters[index] = self._merge_support_into_primary(primary, [memory])
                    attached = True
                    break
            if not attached:
                clusters.append(memory)

        return clusters

    def _should_merge(self, primary: MemoryObject, candidate: MemoryObject) -> bool:
        """Decide whether a candidate is supportive enough to be folded into the primary."""
        if primary.memory_id == candidate.memory_id:
            return False

        if primary.project_id != candidate.project_id:
            return False

        if primary.version_group_id and candidate.version_group_id and primary.version_group_id != candidate.version_group_id:
            return False

        if primary.topic and candidate.topic and primary.topic != candidate.topic:
            return False

        if set(primary.source_event_ids).intersection(candidate.source_event_ids):
            return True

        if self._minutes_between(primary.transaction_time, candidate.transaction_time) <= 20:
            if primary.memory_type in {"decision", "risk", "procedure"} and candidate.memory_type in {"fact", "preference", "episode", "procedure"}:
                return True

        relation = self._judge_relation(primary, candidate)
        if relation["relation"] in {"support", "duplicate", "update"} and float(relation["confidence"]) >= 0.55:
            return True

        return False

    def _judge_relation(self, primary: MemoryObject, candidate: MemoryObject) -> dict[str, str | float]:
        """Ask the provider whether two same-batch memories are semantically mergeable."""
        try:
            relation = self.llm.judge_relation(
                primary.model_dump(),
                [candidate.model_dump()],
            )
        except Exception:
            return {"relation": "unrelated", "reason": "consolidator_fallback", "confidence": 0.0}
        return relation

    def _merge_support_into_primary(self, primary: MemoryObject, support_memories: list[MemoryObject]) -> MemoryObject:
        """Fold supporting fragments into one stronger memory while keeping the primary semantic center."""
        if not support_memories:
            return primary

        merged_rationale = list(primary.rationale)
        merged_objections = list(primary.objections)
        merged_tags = list(primary.tags)
        merged_sources = list(primary.source_event_ids)
        merged_content = primary.content
        merged_importance = primary.importance
        merged_confidence = primary.confidence
        merged_status = primary.status

        for support in support_memories:
            snippet = support.content.strip()
            if snippet and snippet not in merged_content and support.memory_type in {"fact", "preference", "episode"}:
                merged_content += f" Supporting context: {snippet}"
            elif snippet and snippet not in merged_content and support.memory_type == "procedure" and primary.memory_type in {"decision", "risk"}:
                merged_content += f" Follow-up procedure: {snippet}"
            for rationale in support.rationale or [support.title]:
                if rationale and rationale not in merged_rationale:
                    merged_rationale.append(rationale)
            for objection in support.objections:
                if objection and objection not in merged_objections:
                    merged_objections.append(objection)
            for tag in support.tags:
                if tag not in merged_tags:
                    merged_tags.append(tag)
            for source_event_id in support.source_event_ids:
                if source_event_id not in merged_sources:
                    merged_sources.append(source_event_id)
            merged_importance = max(merged_importance, support.importance)
            merged_confidence = max(merged_confidence, support.confidence)
            if merged_status != "active" and support.status == "active":
                merged_status = "active"

        primary.content = merged_content
        primary.rationale = merged_rationale
        primary.objections = merged_objections
        primary.tags = merged_tags
        primary.source_event_ids = merged_sources
        primary.importance = merged_importance
        primary.confidence = merged_confidence
        primary.status = merged_status
        return primary

    def _minutes_between(self, left: str, right: str) -> float:
        """Compute approximate distance between two ISO timestamps."""
        try:
            left_dt = datetime.fromisoformat(left.replace("Z", "+00:00"))
            right_dt = datetime.fromisoformat(right.replace("Z", "+00:00"))
        except ValueError:
            return 9999.0
        return abs((left_dt - right_dt).total_seconds()) / 60.0
