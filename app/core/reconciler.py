from __future__ import annotations

"""Memory reconciliation and supersede handling for the MVP."""

from app.llm.provider import LLMProvider, get_llm_provider
from app.storage.db import (
    insert_memory_edge,
    insert_memory_object,
    insert_memory_sources,
    insert_policy_action,
    list_memories,
    mark_memory_superseded,
)
from app.storage.models import MemoryEdge, MemoryObject, MemorySource, PolicyAction


class MemoryReconciler:
    """Compare a new memory candidate against existing memories and apply updates."""

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm or get_llm_provider()

    def reconcile(self, connection, memory: MemoryObject) -> tuple[MemoryObject, dict[str, str | float]]:
        """Insert or supersede a memory candidate based on active project context."""
        existing_candidates = list_memories(
            connection,
            project_id=memory.project_id,
            status="active",
        )
        related_candidates = [
            candidate
            for candidate in existing_candidates
            if candidate.memory_id != memory.memory_id
            and (
                (memory.version_group_id and candidate.version_group_id == memory.version_group_id)
                or (memory.topic and candidate.topic == memory.topic)
            )
        ]

        relation, matched_candidate = self._select_relation(memory, related_candidates)

        if relation["relation"] == "supersedes" and matched_candidate is not None:
            old_memory = matched_candidate
            memory.version = max(memory.version, old_memory.version + 1)
            memory.supersedes = old_memory.memory_id
            memory.status = "active"

            insert_memory_object(connection, memory)
            insert_memory_sources(
                connection,
                [MemorySource(memory_id=memory.memory_id, event_id=event_id) for event_id in memory.source_event_ids],
            )
            mark_memory_superseded(connection, old_memory.memory_id, memory.memory_id)
            insert_memory_edge(
                connection,
                MemoryEdge(
                    source_memory_id=memory.memory_id,
                    target_memory_id=old_memory.memory_id,
                    relation_type="supersedes",
                    reason=str(relation["reason"]),
                    confidence=float(relation["confidence"]),
                ),
            )
            insert_policy_action(
                connection,
                PolicyAction(
                    action_type="UPDATE",
                    tenant_id=memory.tenant_id,
                    project_id=memory.project_id,
                    memory_id=memory.memory_id,
                    decision="SUPERSEDE",
                    reason=str(relation["reason"]),
                    confidence=float(relation["confidence"]),
                    candidate_payload=memory.model_dump(),
                    input_payload={"old_memory_id": old_memory.memory_id},
                ),
            )
            return memory, relation

        if relation["relation"] == "duplicate":
            insert_policy_action(
                connection,
                PolicyAction(
                    action_type="NOOP",
                    tenant_id=memory.tenant_id,
                    project_id=memory.project_id,
                    memory_id=memory.memory_id,
                    decision="DUPLICATE_SKIPPED",
                    reason=str(relation["reason"]),
                    confidence=float(relation["confidence"]),
                    candidate_payload=memory.model_dump(),
                ),
            )
            return memory, relation

        if relation["relation"] == "conflict":
            memory.status = "conflicted"
            insert_memory_object(connection, memory)
            insert_memory_sources(
                connection,
                [MemorySource(memory_id=memory.memory_id, event_id=event_id) for event_id in memory.source_event_ids],
            )
            insert_policy_action(
                connection,
                PolicyAction(
                    action_type="RECONCILE",
                    tenant_id=memory.tenant_id,
                    project_id=memory.project_id,
                    memory_id=memory.memory_id,
                    decision="CONFLICT",
                    reason=str(relation["reason"]),
                    confidence=float(relation["confidence"]),
                    candidate_payload=memory.model_dump(),
                ),
            )
            return memory, relation

        insert_memory_object(connection, memory)
        insert_memory_sources(
            connection,
            [MemorySource(memory_id=memory.memory_id, event_id=event_id) for event_id in memory.source_event_ids],
        )
        insert_policy_action(
            connection,
            PolicyAction(
                action_type="WRITE",
                tenant_id=memory.tenant_id,
                project_id=memory.project_id,
                memory_id=memory.memory_id,
                decision="CREATE",
                reason="Inserted new memory candidate without superseding an existing active memory.",
                confidence=1.0,
                candidate_payload=memory.model_dump(),
            ),
        )
        return memory, {"relation": "created", "reason": "New memory inserted.", "confidence": 1.0}

    def _select_relation(
        self,
        memory: MemoryObject,
        related_candidates: list[MemoryObject],
    ) -> tuple[dict[str, str | float], MemoryObject | None]:
        """Judge one candidate at a time so supersede targets stay precise."""
        if not related_candidates:
            return {"relation": "unrelated", "reason": "No related active memories.", "confidence": 1.0}, None

        judged: list[tuple[dict[str, str | float], MemoryObject]] = []
        for candidate in related_candidates:
            relation = self.llm.judge_relation(
                memory.model_dump(),
                [candidate.model_dump()],
            )
            judged.append((relation, candidate))

        best_supersede = self._pick_best(judged, "supersedes")
        if best_supersede is not None:
            return best_supersede

        best_duplicate = self._pick_best(judged, "duplicate")
        if best_duplicate is not None:
            return best_duplicate

        best_conflict = self._pick_best(judged, "conflict")
        if best_conflict is not None:
            return best_conflict

        best_update = self._pick_best(judged, "update")
        if best_update is not None:
            return best_update

        best_support = self._pick_best(judged, "support")
        if best_support is not None:
            return best_support

        best_unrelated = max(
            judged,
            key=lambda item: (
                float(item[0].get("confidence", 0.0)),
                item[1].version,
                item[1].updated_at,
                item[1].created_at,
            ),
        )
        return best_unrelated

    def _pick_best(
        self,
        judged: list[tuple[dict[str, str | float], MemoryObject]],
        relation_name: str,
    ) -> tuple[dict[str, str | float], MemoryObject] | None:
        """Pick the strongest match for one relation type."""
        matches = [
            item
            for item in judged
            if str(item[0].get("relation", "")) == relation_name
        ]
        if not matches:
            return None
        return max(
            matches,
            key=lambda item: (
                float(item[0].get("confidence", 0.0)),
                item[1].version,
                item[1].updated_at,
                item[1].created_at,
            ),
        )
