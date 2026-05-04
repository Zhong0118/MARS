from __future__ import annotations

"""Merge fragmented extracted memories into stronger consolidated candidates.

This layer sits after extraction/post-processing and before reconciliation.
Its job is not to do long-term state transitions, but to reduce noisy
same-batch fragments into fewer, stronger candidates.

Consolidation uses a three-level prefilter before calling LLM:
  Level 1: hard filter (project / version_group / topic)
  Level 2: type filter (high-priority pairs default to independent)
  Level 3: cheap signals (source overlap, token overlap, time proximity)
Only pairs that pass all three levels are sent to judge_consolidation.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from app.core.window_builder import tokenize_text
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

HIGH_PRIORITY_TYPES = {"decision", "risk", "procedure"}
SUPPORT_TYPES = {"fact", "preference", "episode"}


@dataclass(slots=True)
class ConsolidationTrace:
    """One pairwise judgment record for observability."""

    primary_memory_id: str
    candidate_memory_id: str
    merge_decision: bool
    relation: str
    confidence: float
    reason: str
    keep_separate_reason: str | None = None
    filter_stage: str = "llm"


@dataclass(slots=True)
class ConsolidationResult:
    """Output of consolidation: fewer memories plus a full trace."""

    memories: list[MemoryObject] = field(default_factory=list)
    traces: list[ConsolidationTrace] = field(default_factory=list)


class MemoryConsolidator:
    """Collapse related extracted memories before reconciliation."""

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm or get_llm_provider()

    def consolidate(self, memories: list[MemoryObject]) -> ConsolidationResult:
        """Return fewer, stronger candidates with a full trace of merge decisions."""
        result = ConsolidationResult()
        if not memories:
            return result

        grouped: dict[tuple[str | None, str | None], list[MemoryObject]] = defaultdict(list)
        for memory in memories:
            grouped[(memory.project_id, memory.version_group_id or memory.topic)].append(memory)

        for group_memories in grouped.values():
            group_result = self._consolidate_group(group_memories)
            result.memories.extend(group_result.memories)
            result.traces.extend(group_result.traces)
        return result

    def _consolidate_group(self, memories: list[MemoryObject]) -> ConsolidationResult:
        """Merge memories in one topic/version group."""
        result = ConsolidationResult()
        if len(memories) <= 1:
            result.memories = list(memories)
            return result

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
                merge, trace = self._should_merge(primary, memory)
                if trace is not None:
                    result.traces.append(trace)
                if merge:
                    clusters[index] = self._merge_support_into_primary(primary, [memory])
                    attached = True
                    break
            if not attached:
                clusters.append(memory)

        result.memories = clusters
        return result

    def _should_merge(
        self, primary: MemoryObject, candidate: MemoryObject,
    ) -> tuple[bool, ConsolidationTrace | None]:
        """Three-level prefilter, then LLM judgment."""
        if primary.memory_id == candidate.memory_id:
            return False, None

        # --- Level 1: hard filter ---
        if primary.project_id != candidate.project_id:
            return False, self._trace(primary, candidate, False, "unrelated", 1.0,
                                      "Different projects.", filter_stage="L1_hard")

        if (primary.version_group_id and candidate.version_group_id
                and primary.version_group_id != candidate.version_group_id):
            return False, self._trace(primary, candidate, False, "unrelated", 1.0,
                                      "Different version groups.", filter_stage="L1_hard")

        if primary.topic and candidate.topic and primary.topic != candidate.topic:
            return False, self._trace(primary, candidate, False, "unrelated", 1.0,
                                      "Different topics.", filter_stage="L1_hard")

        # --- Level 2: type filter ---
        both_high = (primary.memory_type in HIGH_PRIORITY_TYPES
                     and candidate.memory_type in HIGH_PRIORITY_TYPES)
        if both_high:
            title_overlap = self._token_overlap(primary.title, candidate.title)
            content_overlap = self._token_overlap(primary.content, candidate.content)
            if title_overlap < 0.6 and content_overlap < 0.5:
                return False, self._trace(
                    primary, candidate, False, "independent", 0.8,
                    f"Two high-priority types ({primary.memory_type} + {candidate.memory_type}) "
                    f"with low similarity (title={title_overlap:.2f}, content={content_overlap:.2f}).",
                    keep_separate="High-priority memories default to independent unless near-duplicate.",
                    filter_stage="L2_type",
                )

        # --- Level 3: cheap signals ---
        source_overlap = bool(set(primary.source_event_ids) & set(candidate.source_event_ids))
        title_overlap = self._token_overlap(primary.title, candidate.title)
        content_overlap = self._token_overlap(primary.content, candidate.content)
        time_close = self._minutes_between(primary.transaction_time, candidate.transaction_time) <= 30
        shared_tags = bool(set(primary.tags) & set(candidate.tags))

        has_signal = (
            source_overlap
            or title_overlap >= 0.25
            or content_overlap >= 0.2
            or (time_close and shared_tags)
        )

        if not has_signal:
            return False, self._trace(
                primary, candidate, False, "unrelated", 0.7,
                f"No cheap merge signal (source_overlap={source_overlap}, "
                f"title_overlap={title_overlap:.2f}, content_overlap={content_overlap:.2f}, "
                f"time_close={time_close}, shared_tags={shared_tags}).",
                filter_stage="L3_signal",
            )

        # --- LLM judgment ---
        try:
            result = self.llm.judge_consolidation(
                primary.model_dump(),
                candidate.model_dump(),
            )
        except Exception:
            return False, self._trace(primary, candidate, False, "unrelated", 0.0,
                                      "LLM call failed.", filter_stage="llm_error")

        merge = bool(result.get("merge_decision", False))
        relation = str(result.get("relation", "unrelated"))

        if relation in ("independent", "unrelated"):
            merge = False

        return merge, self._trace(
            primary, candidate, merge, relation,
            float(result.get("confidence", 0.0)),
            str(result.get("reason", "")),
            keep_separate=result.get("keep_separate_reason"),
            filter_stage="llm",
        )

    def _token_overlap(self, text_a: str | None, text_b: str | None) -> float:
        """Cheap lexical overlap ratio between two text fields."""
        tokens_a = tokenize_text(text_a)
        tokens_b = tokenize_text(text_b)
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a & tokens_b
        smaller = min(len(tokens_a), len(tokens_b))
        return len(intersection) / smaller if smaller > 0 else 0.0

    def _trace(
        self,
        primary: MemoryObject,
        candidate: MemoryObject,
        merge: bool,
        relation: str,
        confidence: float,
        reason: str,
        *,
        keep_separate: str | None = None,
        filter_stage: str = "llm",
    ) -> ConsolidationTrace:
        return ConsolidationTrace(
            primary_memory_id=primary.memory_id,
            candidate_memory_id=candidate.memory_id,
            merge_decision=merge,
            relation=relation,
            confidence=confidence,
            reason=reason,
            keep_separate_reason=keep_separate,
            filter_stage=filter_stage,
        )

    def _merge_support_into_primary(self, primary: MemoryObject, support_memories: list[MemoryObject]) -> MemoryObject:
        """Fold supporting fragments into one stronger memory."""
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
            if snippet and snippet not in merged_content and support.memory_type in SUPPORT_TYPES:
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
            if left_dt.tzinfo is not None:
                left_dt = left_dt.replace(tzinfo=None)
            if right_dt.tzinfo is not None:
                right_dt = right_dt.replace(tzinfo=None)
        except ValueError:
            return 9999.0
        return abs((left_dt - right_dt).total_seconds()) / 60.0
