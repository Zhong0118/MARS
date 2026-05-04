from __future__ import annotations

"""Keyword-based local memory retrieval for the MVP.
在 memory_objects 里做本地关键词检索
"""

import time
from pathlib import Path

from app.core.query_planner import QueryPlan, normalize_query_topic
from app.core.window_builder import tokenize_query
from app.storage.db import build_evidence_pack, get_connection, get_memory_usage_counts, insert_retrieval_log, list_memories
from app.storage.models import EvidencePack, MemoryObject


class MemoryRetriever:
    """Search stored memories with lightweight keyword matching."""

    def __init__(self, top_k: int = 5, status_filter: str = "active", db_path: Path | None = None) -> None:
        self.top_k = top_k
        self.status_filter = status_filter
        self.db_path = db_path

    def search(self, query: str, project_id: str | None = None, *, plan: QueryPlan) -> list[EvidencePack]:
        """Search memories and return ranked EvidencePack results."""
        started_at = time.perf_counter()
        query_tokens = tokenize_query(query)

        with get_connection(self.db_path) as connection:
            candidate_memories = list_memories(
                connection,
                project_id=project_id,
                status=self.status_filter,
            )
            usage_counts = get_memory_usage_counts(connection, [memory.memory_id for memory in candidate_memories])

            scored_results = [
                (memory, score_memory(memory, query_tokens, query, plan, usage_counts.get(memory.memory_id, 0)))
                for memory in candidate_memories
            ]
            scored_results = [
                (memory, score)
                for memory, score in scored_results
                if score > 0
            ]
            scored_results = deduplicate_scored_results(scored_results)
            scored_results = apply_plan_priority(scored_results, plan)
            scored_results.sort(
                key=lambda item: (
                    plan_priority(item[0], plan),
                    item[1],
                    item[0].importance,
                    item[0].version,
                    item[0].updated_at,
                    item[0].created_at,
                ),
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
                retrieval_method="hybrid_heuristic",
                score_items=[
                    {"memory_id": memory.memory_id, "score": score}
                    for memory, score in selected_results
                ],
            )

        return evidence_packs


def score_memory(
    memory: MemoryObject,
    query_tokens: list[str],
    query: str,
    plan: QueryPlan,
    usage_count: int,
) -> float:
    """Compute a transparent hybrid score for one memory."""
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

    score += semantic_score(memory, query_tokens, plan)
    score += value_score(memory, plan)
    score += frequency_score(usage_count)

    return round(score, 3)


def semantic_score(memory: MemoryObject, query_tokens: list[str], plan: QueryPlan) -> float:
    """Score coarse semantic alignment using topics and token overlap."""
    score = 0.0
    memory_topic = normalize_query_topic(memory.topic)
    if plan.normalized_topic and memory_topic == plan.normalized_topic:
        score += 5.0

    memory_tokens = set(tokenize_query(" ".join([memory.title, memory.content, memory.topic or "", " ".join(memory.tags)])))
    overlap = len(memory_tokens.intersection(query_tokens))
    score += min(4.0, overlap * 1.2)
    return score


def value_score(memory: MemoryObject, plan: QueryPlan) -> float:
    """Score durable value using type priority, status, and confidence."""
    score = 0.0
    if memory.memory_type in plan.preferred_types:
        score += 4.0
    if memory.memory_type in plan.primary_types:
        score += 5.0
    if memory.status == "active":
        score += 2.0
    score += min(2.0, memory.confidence * 2.0)
    score += min(2.0, memory.importance * 0.3)

    if plan.query_type == "current_state":
        if memory.memory_type == "decision":
            score += 6.0
        elif memory.memory_type == "fact":
            score -= 1.0
        elif memory.memory_type == "procedure":
            score += 1.0

        lowered = f"{memory.title} {memory.content}".lower()
        if any(keyword in lowered for keyword in ["selected", "use ", "will use", "chosen", "instead of", "route"]):
            score += 3.0

    return score


def frequency_score(usage_count: int) -> float:
    """Score retrieval frequency to favor commonly useful memories without domination."""
    if usage_count <= 0:
        return 0.0
    return min(2.0, usage_count * 0.25)


def plan_priority(memory: MemoryObject, plan: QueryPlan) -> int:
    """Return a coarse priority bucket for sorting under the current query plan."""
    priority = 0
    memory_topic = normalize_query_topic(memory.topic)

    if plan.normalized_topic and memory_topic == plan.normalized_topic:
        priority += 4
    elif plan.strict_topic and plan.normalized_topic is not None:
        priority -= 4

    if memory.memory_type in plan.primary_types:
        priority += 4
    elif memory.memory_type in plan.preferred_types:
        priority += 1
    else:
        priority -= 2

    if memory.status == "active":
        priority += 1
    return priority


def apply_plan_priority(
    scored_results: list[tuple[MemoryObject, float]],
    plan: QueryPlan,
) -> list[tuple[MemoryObject, float]]:
    """Optionally narrow current-state style searches to the most relevant topic bucket."""
    if not scored_results or not plan.strict_topic or plan.normalized_topic is None:
        return scored_results

    primary_bucket = [
        item
        for item in scored_results
        if normalize_query_topic(item[0].topic) == plan.normalized_topic
    ]
    if primary_bucket:
        return primary_bucket
    return scored_results


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
