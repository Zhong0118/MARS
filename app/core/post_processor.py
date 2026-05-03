from __future__ import annotations

"""Post-processing for extracted memories before reconciliation.

This layer keeps semantic extraction and system governance separate:
- normalize topics into stable internal labels
- rewrite unstable LLM-generated IDs
- fill version_group_id
- downgrade or drop low-value memories
"""

from dataclasses import dataclass
import hashlib
import re

from app.config import load_json_config
from app.storage.models import DiscussionWindow, MemoryObject, TopicAssignment


DEFAULT_HIGH_PRIORITY_TYPES = {"decision", "fact", "procedure", "risk"}
DEFAULT_LOW_PRIORITY_TYPES = {"preference", "episode"}

DEFAULT_TOPIC_NORMALIZATION_RULES = {
    "tech_route": ["tech", "technology", "stack", "frontend", "backend", "streamlit", "vue", "fastapi", "architecture", "react", "api"],
    "timeline": ["timeline", "deadline", "schedule", "milestone", "eta", "review", "ship", "launch"],
    "risk": ["risk", "blocker", "issue", "problem", "failure", "deployment", "incident", "unstable"],
    "reporting": ["report", "summary", "weekly", "status update", "slide", "deck", "recap"],
    "onboarding": ["onboarding", "handoff", "new member", "context", "background"],
    "ownership": ["owner", "responsible", "follow up", "follow-up", "assignee"],
}

DEFAULT_POST_PROCESSOR_CONFIG = {
    "high_priority_types": sorted(DEFAULT_HIGH_PRIORITY_TYPES),
    "low_priority_types": sorted(DEFAULT_LOW_PRIORITY_TYPES),
    "topic_normalization_rules": DEFAULT_TOPIC_NORMALIZATION_RULES,
    "pending_confidence_threshold": 0.6,
    "pending_importance_threshold": 2,
    "drop_confidence_threshold": 0.45,
}


@dataclass(slots=True)
class PostProcessDecision:
    """Internal result bundle for one processed memory."""

    memory: MemoryObject | None
    dropped_reason: str | None = None


class ExtractionPostProcessor:
    """Normalize and filter extracted memories before persistence."""

    def __init__(self) -> None:
        loaded = load_json_config("post_processor_rules.json", DEFAULT_POST_PROCESSOR_CONFIG)
        self.high_priority_types = set(loaded["high_priority_types"])
        self.low_priority_types = set(loaded["low_priority_types"])
        self.topic_normalization_rules = {
            key: tuple(value)
            for key, value in loaded["topic_normalization_rules"].items()
        }
        self.pending_confidence_threshold = float(loaded["pending_confidence_threshold"])
        self.pending_importance_threshold = int(loaded["pending_importance_threshold"])
        self.drop_confidence_threshold = float(loaded["drop_confidence_threshold"])

    def process_window_memories(
        self,
        memories: list[MemoryObject],
        *,
        window: DiscussionWindow,
        assignment: TopicAssignment | None = None,
    ) -> list[MemoryObject]:
        """Normalize a batch of memories extracted from one discussion window."""
        processed: list[MemoryObject] = []
        for index, memory in enumerate(memories, start=1):
            decision = self._process_one(memory, window=window, assignment=assignment, ordinal=index)
            if decision.memory is not None:
                processed.append(decision.memory)
        return processed

    def _process_one(
        self,
        memory: MemoryObject,
        *,
        window: DiscussionWindow,
        assignment: TopicAssignment | None,
        ordinal: int,
    ) -> PostProcessDecision:
        normalized_topic = self.normalize_topic(memory.topic, assignment=assignment, window=window)
        memory.topic = normalized_topic
        memory.version_group_id = self.build_version_group_id(memory)
        memory.memory_id = self.build_memory_id(memory, ordinal=ordinal)
        memory.status = self.adjust_status(memory, window=window)

        if self.should_drop(memory, window=window):
            return PostProcessDecision(memory=None, dropped_reason="low_value_memory")

        return PostProcessDecision(memory=memory)

    def normalize_topic(
        self,
        topic: str | None,
        *,
        assignment: TopicAssignment | None,
        window: DiscussionWindow,
    ) -> str:
        """Normalize free-form LLM topics into stable internal labels."""
        candidates = [topic or "", assignment.label if assignment else "", window.topic_hint or "", window.raw_summary or ""]
        combined = " ".join(candidate.lower() for candidate in candidates if candidate)

        if assignment is not None and assignment.assignment_reason == "llm_topic_classification" and assignment.label:
            return slugify(assignment.label)

        for normalized_label, keywords in self.topic_normalization_rules.items():
            if any(keyword in combined for keyword in keywords):
                return normalized_label

        if assignment is not None and assignment.label:
            return slugify(assignment.label)
        if window.topic_hint:
            return slugify(window.topic_hint)
        return "general"

    def build_version_group_id(self, memory: MemoryObject) -> str:
        """Create a stable version-group label for future supersede chains."""
        project = slugify(memory.project_id or "global")
        topic = slugify(memory.topic or "general")
        return f"vg_{project}_{topic}"

    def build_memory_id(self, memory: MemoryObject, *, ordinal: int) -> str:
        """Create a stable deterministic ID instead of trusting the LLM."""
        project = slugify(memory.project_id or "global")
        topic = slugify(memory.topic or "general")
        memory_type = slugify(memory.memory_type)
        content_key = slugify(memory.title or memory.content)[:48]
        fingerprint_source = "|".join(
            [
                memory.project_id or "",
                memory.topic or "",
                memory.memory_type,
                memory.title,
                memory.content,
                ",".join(memory.source_event_ids),
                str(ordinal),
            ]
        )
        fingerprint = hashlib.sha1(fingerprint_source.encode("utf-8")).hexdigest()[:8]
        return f"mem_{project}_{topic}_{memory_type}_{content_key}_{fingerprint}"

    def adjust_status(self, memory: MemoryObject, *, window: DiscussionWindow) -> str:
        """Downgrade low-confidence or question-like outputs to pending."""
        text = f"{memory.title} {memory.content}".strip().lower()
        is_question_like = "?" in text or text.startswith("should ") or "proposal" in text or "preference" in text

        if memory.memory_type in self.low_priority_types:
            return "pending"

        if is_question_like and len(memory.source_event_ids) <= 1:
            return "pending"

        if memory.confidence < self.pending_confidence_threshold or memory.importance <= self.pending_importance_threshold:
            return "pending"

        if memory.memory_type not in self.high_priority_types and len(memory.source_event_ids) <= 1:
            return "pending"

        return memory.status if memory.status != "active" else "active"

    def should_drop(self, memory: MemoryObject, *, window: DiscussionWindow) -> bool:
        """Drop very low-value memories that should not be persisted at all."""
        text = f"{memory.title} {memory.content}".strip().lower()
        if memory.memory_type == "episode" and len(memory.source_event_ids) <= 1:
            return True
        if memory.memory_type == "preference" and len(memory.source_event_ids) <= 1 and "?" in (window.raw_summary or ""):
            return True
        if memory.status == "pending" and memory.confidence < self.drop_confidence_threshold and len(memory.source_event_ids) <= 1:
            return True
        if text.count("proposal") and len(memory.source_event_ids) <= 1:
            return True
        return False


def slugify(value: str) -> str:
    """Build compact ASCII slugs for stable IDs and internal labels."""
    lowered = value.lower().strip()
    lowered = lowered.replace("+", " plus ")
    slug = re.sub(r"[^a-z0-9]+", "_", lowered)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "item"
