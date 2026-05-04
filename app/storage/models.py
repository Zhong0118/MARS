from __future__ import annotations

"""Core Pydantic models shared across MARS layers.

These models define the internal contract between connectors, core logic, and
storage. External payload shapes should be converted into these models before
they enter the rest of the system.
"""

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now_iso() -> str:
    """Return an ISO-8601 timestamp in UTC for audit fields."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_id(prefix: str) -> str:
    """Generate short readable IDs for MVP records."""
    return f"{prefix}_{uuid4().hex[:12]}"


MemoryStatus = Literal[
    "pending",
    "active",
    "superseded",
    "expired",
    "archived",
    "conflicted",
    "rejected",
]

MemoryType = Literal[
    "decision",
    "fact",
    "procedure",
    "risk",
    "preference",
    "episode",
    "skill",
]

MemoryScope = Literal[
    "user",
    "team",
    "project",
    "org",
]

MemoryRelation = Literal[
    "duplicate",
    "support",
    "update",
    "conflict",
    "supersedes",
    "unrelated",
]

PolicyActionType = Literal[
    "READ",
    "WRITE",
    "UPDATE",
    "DELETE",
    "FORGET",
    "PUSH",
    "RECONCILE",
    "BENCHMARK",
    "NOOP",
]



class RawEvent(BaseModel):
    """Append-only source event stored in the raw ledger."""

    event_id: str
    event_type: str
    source_type: str
    source_id: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    chat_id: str | None = None
    thread_id: str | None = None
    actor_id: str | None = None
    actor_name: str | None = None
    content: str
    content_type: str = "text"
    mentions: list[str] = Field(default_factory=list)
    reply_to: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    transaction_time: str
    valid_time_start: str
    valid_time_end: str | None = None
    source_url: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class MemoryObject(BaseModel):
    """Structured memory extracted from one or more raw events."""

    memory_id: str = Field(default_factory=lambda: make_id("mem"))
    version_group_id: str | None = None
    memory_type: MemoryType
    scope: MemoryScope
    tenant_id: str | None = None
    project_id: str | None = None
    user_id: str | None = None
    topic: str | None = None
    title: str
    content: str
    rationale: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: MemoryStatus = "pending"
    version: int = Field(default=1, ge=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    importance: int = Field(default=3, ge=1, le=5)
    valid_time_start: str
    valid_time_end: str | None = None
    transaction_time: str
    source_event_ids: list[str]
    supersedes: str | None = None
    superseded_by: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    @field_validator("source_event_ids")
    @classmethod
    def validate_source_event_ids(cls, value: list[str]) -> list[str]:
        """Enforce provenance so every memory can trace back to raw events."""
        if not value:
            raise ValueError("MemoryObject must include at least one source_event_id.")
        return value


class MemoryEdge(BaseModel):
    """Relation between two memory objects, such as supersedes."""

    edge_id: str = Field(default_factory=lambda: make_id("edge"))
    source_memory_id: str
    target_memory_id: str
    relation_type: MemoryRelation
    reason: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=utc_now_iso)


class MemorySource(BaseModel):
    """Explicit evidence link from a memory object to a source event."""

    id: str = Field(default_factory=lambda: make_id("src"))
    memory_id: str
    event_id: str
    evidence_type: str = "message"
    quote: str | None = None
    source_url: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class PolicyAction(BaseModel):
    """Audit record for state-changing policy or reconciliation decisions."""

    action_id: str = Field(default_factory=lambda: make_id("act"))
    action_type: PolicyActionType
    tenant_id: str | None = None
    project_id: str | None = None
    chat_id: str | None = None
    thread_id: str | None = None
    actor_id: str | None = None
    memory_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    candidate_payload: dict[str, Any] = Field(default_factory=dict)
    decision: str
    reason: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=utc_now_iso)


class EvidencePack(BaseModel):
    """Search-facing view model returned by retrieval flows."""

    memory_id: str
    title: str
    content: str
    status: MemoryStatus
    score: float = Field(default=0.0, ge=0.0)
    source_event_ids: list[str]
    rationale: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    memory_type: str = ""
    topic: str | None = None
    project_id: str | None = None



class Tenant(BaseModel):
    """Top-level workspace or organization container."""

    tenant_id: str
    tenant_name: str | None = None
    source_type: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class User(BaseModel):
    """Person or service account participating in collaboration events."""

    user_id: str
    tenant_id: str | None = None
    display_name: str | None = None
    source_type: str | None = None
    source_user_id: str | None = None
    open_id: str | None = None
    union_id: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class Chat(BaseModel):
    """Chat or conversation container such as a group, DM, or thread root."""

    chat_id: str
    tenant_id: str | None = None
    chat_name: str | None = None
    chat_type: str | None = None
    source_type: str | None = None
    source_chat_id: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class Project(BaseModel):
    """Business project scope used for memory grouping and retrieval."""

    project_id: str
    tenant_id: str | None = None
    project_name: str | None = None
    description: str | None = None
    status: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class ProjectChat(BaseModel):
    """Mapping between a project and a related chat."""

    id: str = Field(default_factory=lambda: make_id("pc"))
    project_id: str
    chat_id: str
    relation_type: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class ChatMembership(BaseModel):
    """Membership relation for users participating in chats."""

    id: str = Field(default_factory=lambda: make_id("cm"))
    chat_id: str
    user_id: str
    role: str | None = None
    joined_at: str | None = None
    left_at: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class DiscussionWindow(BaseModel):
    """Candidate discussion segment built from contiguous raw events."""

    window_id: str = Field(default_factory=lambda: make_id("win"))
    tenant_id: str | None = None
    project_id: str | None = None
    chat_id: str | None = None
    thread_id: str | None = None
    topic_hint: str | None = None
    split_reason: str | None = None
    start_time: str
    end_time: str
    event_ids: list[str]
    message_count: int = Field(ge=1)
    raw_summary: str | None = None


class TopicAssignment(BaseModel):
    """Topic label assigned to a discussion window."""

    topic_id: str = Field(default_factory=lambda: make_id("topic"))
    label: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    assignment_reason: str
    matched_markers: list[str] = Field(default_factory=list)


class ProcessingCursor(BaseModel):
    """Per-stream cursor used for incremental extraction."""

    cursor_id: str = Field(default_factory=lambda: make_id("cursor"))
    project_id: str | None = None
    chat_id: str | None = None
    last_event_id: str
    last_event_time: str
    updated_at: str = Field(default_factory=utc_now_iso)


class BenchmarkResult(BaseModel):
    """Stored benchmark outcome for one evaluation case."""

    result_id: str = Field(default_factory=lambda: make_id("bench"))
    benchmark_type: str
    case_id: str
    metric: dict[str, Any] = Field(default_factory=dict)
    passed: bool
    created_at: str = Field(default_factory=utc_now_iso)
