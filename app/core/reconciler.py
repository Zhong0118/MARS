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

        relation = self.llm.judge_relation(
            memory.model_dump(),
            [candidate.model_dump() for candidate in related_candidates],
        )

        if relation["relation"] == "supersedes" and related_candidates:
            old_memory = max(
                related_candidates,
                key=lambda candidate: (candidate.version, candidate.updated_at, candidate.created_at),
            )
            memory.version = max(memory.version, old_memory.version + 1)
            memory.supersedes = old_memory.memory_id
            memory.status = "active"

            insert_memory_object(connection, memory)
            insert_memory_sources(
                connection,
                [MemorySource(memory_id=memory.memory_id, event_id=event_id) for event_id in memory.source_event_ids],
            )
            for candidate in related_candidates:
                mark_memory_superseded(connection, candidate.memory_id, memory.memory_id)
                insert_memory_edge(
                    connection,
                    MemoryEdge(
                        source_memory_id=memory.memory_id,
                        target_memory_id=candidate.memory_id,
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
