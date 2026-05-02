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
    memory_type: str
    scope: str
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
    version: int = 1
    confidence: float = 0.0
    importance: int = 3
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
    relation_type: str
    reason: str | None = None
    confidence: float = 0.0
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
    action_type: str
    project_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    candidate_payload: dict[str, Any] = Field(default_factory=dict)
    decision: str
    reason: str
    confidence: float = 0.0
    created_at: str = Field(default_factory=utc_now_iso)


class EvidencePack(BaseModel):
    """Search-facing view model returned by retrieval flows."""

    memory_id: str
    title: str
    content: str
    status: MemoryStatus
    score: float = 0.0
    source_event_ids: list[str]
    rationale: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
