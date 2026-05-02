from __future__ import annotations

"""Keyword-based local memory retrieval for the MVP.
在 memory_objects 里做本地关键词检索
"""

import re
import time

from app.storage.db import build_evidence_pack, get_connection, insert_retrieval_log, list_memories
from app.storage.models import EvidencePack, MemoryObject


class MemoryRetriever:
    """Search stored memories with lightweight keyword matching."""

    def __init__(self, top_k: int = 5, status_filter: str = "active") -> None:
        self.top_k = top_k
        self.status_filter = status_filter

    def search(self, query: str, project_id: str | None = None) -> list[EvidencePack]:
        """Search memories and return ranked EvidencePack results."""
        started_at = time.perf_counter()
        query_tokens = tokenize_query(query)

        with get_connection() as connection:
            candidate_memories = list_memories(
                connection,
                project_id=project_id,
                status=self.status_filter,
            )

            scored_results = [
                (memory, score_memory(memory, query_tokens, query))
                for memory in candidate_memories
            ]
            scored_results = [
                (memory, score)
                for memory, score in scored_results
                if score > 0
            ]
            scored_results = deduplicate_scored_results(scored_results)
            scored_results.sort(
                key=lambda item: (item[1], item[0].importance, item[0].updated_at, item[0].created_at),
                reverse=True,
            )

            selected_results = scored_results[: self.top_k]
            evidence_packs = [
                build_evidence_pack(memory, score)
                for memory, score in selected_results
            ]

            latency_ms = int((time.perf_counter() - started_at) * 1000)
            insert_retrieval_log(
                connection,
                query=query,
                project_id=project_id,
                retrieved_memory_ids=[memory.memory_id for memory, _ in scored_results],
                selected_memory_ids=[pack.memory_id for pack in evidence_packs],
                latency_ms=latency_ms,
                top_k=self.top_k,
                status_filter=self.status_filter,
                retrieval_method="keyword",
                score_items=[
                    {"memory_id": memory.memory_id, "score": score}
                    for memory, score in selected_results
                ],
            )

        return evidence_packs


def tokenize_query(query: str) -> list[str]:
    """Extract simple searchable tokens from Chinese/English mixed text."""
    lowered = query.lower()
    tokens = re.findall(r"[a-z0-9_+\-#.]+|[\u4e00-\u9fff]+", lowered)
    return [token for token in tokens if token.strip()]


def score_memory(memory: MemoryObject, query_tokens: list[str], query: str) -> float:
    """Compute a transparent keyword score for one memory."""
    haystacks = {
        "title": (memory.title or "").lower(),
        "content": (memory.content or "").lower(),
        "topic": (memory.topic or "").lower(),
        "tags": " ".join(memory.tags).lower(),
        "rationale": " ".join(memory.rationale).lower(),
        "objections": " ".join(memory.objections).lower(),
    }

    score = 0.0
    for token in query_tokens:
        if token in haystacks["title"]:
            score += 4.0
        if token in haystacks["content"]:
            score += 3.0
        if token in haystacks["topic"]:
            score += 2.0
        if token in haystacks["tags"]:
            score += 2.0
        if token in haystacks["rationale"]:
            score += 1.5
        if token in haystacks["objections"]:
            score += 1.0

    lowered_query = query.lower()
    if lowered_query and lowered_query in haystacks["content"]:
        score += 2.0
    if lowered_query and lowered_query in haystacks["title"]:
        score += 3.0

    return round(score, 3)


def deduplicate_scored_results(
    scored_results: list[tuple[MemoryObject, float]],
) -> list[tuple[MemoryObject, float]]:
    """Keep only the strongest hit per version group to reduce duplicate returns."""
    best_by_group: dict[str, tuple[MemoryObject, float]] = {}

    for memory, score in scored_results:
        group_key = memory.version_group_id or memory.memory_id
        existing = best_by_group.get(group_key)
        if existing is None:
            best_by_group[group_key] = (memory, score)
            continue

        existing_memory, existing_score = existing
        if (score, memory.version, memory.updated_at, memory.created_at) > (
            existing_score,
            existing_memory.version,
            existing_memory.updated_at,
            existing_memory.created_at,
        ):
            best_by_group[group_key] = (memory, score)

    return list(best_by_group.values())
