from __future__ import annotations

"""SQLite helpers for the local MARS MVP.

This module owns:
- database file location
- schema initialization
- serialization boundaries between Pydantic models and SQLite rows
- lightweight insert helpers used by early-phase scripts
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.storage.models import MemoryEdge, MemoryObject, MemorySource, PolicyAction, RawEvent


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_DIR = PROJECT_ROOT / "memory_store"
DB_PATH = DB_DIR / "mars.db"


def ensure_storage_dirs() -> None:
    """Create local storage directories used by the MVP."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "reports").mkdir(parents=True, exist_ok=True)


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with row access by column name."""
    ensure_storage_dirs()
    connection = sqlite3.connect(str(db_path or DB_PATH))
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(db_path: Path | None = None) -> Path:
    """Create the SQLite database file and all required tables."""
    target = db_path or DB_PATH
    ensure_storage_dirs()

    with get_connection(target) as connection:
        cursor = connection.cursor()
        for statement in schema_statements():
            cursor.execute(statement)
        connection.commit()

    return target


def schema_statements() -> list[str]:
    """Return the ordered list of DDL statements for the MVP schema."""
    return [
        """
        CREATE TABLE IF NOT EXISTS raw_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT,
            tenant_id TEXT,
            project_id TEXT,
            chat_id TEXT,
            thread_id TEXT,
            actor_id TEXT,
            actor_name TEXT,
            content TEXT,
            content_type TEXT,
            mentions_json TEXT,
            reply_to TEXT,
            raw_payload_json TEXT,
            transaction_time TEXT,
            valid_time_start TEXT,
            valid_time_end TEXT,
            source_url TEXT,
            created_at TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS memory_objects (
            memory_id TEXT PRIMARY KEY,
            memory_type TEXT NOT NULL,
            scope TEXT NOT NULL,
            tenant_id TEXT,
            project_id TEXT,
            user_id TEXT,
            topic TEXT,
            title TEXT,
            content TEXT,
            rationale_json TEXT,
            objections_json TEXT,
            tags_json TEXT,
            status TEXT,
            version INTEGER,
            confidence REAL,
            importance INTEGER,
            valid_time_start TEXT,
            valid_time_end TEXT,
            transaction_time TEXT,
            supersedes TEXT,
            superseded_by TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS memory_sources (
            id TEXT PRIMARY KEY,
            memory_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            evidence_type TEXT,
            quote TEXT,
            source_url TEXT,
            created_at TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS memory_edges (
            edge_id TEXT PRIMARY KEY,
            source_memory_id TEXT NOT NULL,
            target_memory_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            reason TEXT,
            confidence REAL,
            created_at TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS policy_actions (
            action_id TEXT PRIMARY KEY,
            action_type TEXT NOT NULL,
            project_id TEXT,
            input_json TEXT,
            candidate_json TEXT,
            decision TEXT,
            reason TEXT,
            confidence REAL,
            created_at TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS retrieval_logs (
            log_id TEXT PRIMARY KEY,
            query TEXT,
            project_id TEXT,
            time_scope TEXT,
            retrieved_memory_ids_json TEXT,
            selected_memory_ids_json TEXT,
            latency_ms INTEGER,
            created_at TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS benchmark_results (
            result_id TEXT PRIMARY KEY,
            benchmark_type TEXT,
            case_id TEXT,
            metric_json TEXT,
            passed INTEGER,
            created_at TEXT
        );
        """,
    ]


def insert_raw_events(connection: sqlite3.Connection, events: list[RawEvent]) -> None:
    """Persist normalized RawEvent records into the raw ledger."""
    connection.executemany(
        """
        INSERT OR REPLACE INTO raw_events (
            event_id,
            event_type,
            source_type,
            source_id,
            tenant_id,
            project_id,
            chat_id,
            thread_id,
            actor_id,
            actor_name,
            content,
            content_type,
            mentions_json,
            reply_to,
            raw_payload_json,
            transaction_time,
            valid_time_start,
            valid_time_end,
            source_url,
            created_at
        ) VALUES (
            :event_id,
            :event_type,
            :source_type,
            :source_id,
            :tenant_id,
            :project_id,
            :chat_id,
            :thread_id,
            :actor_id,
            :actor_name,
            :content,
            :content_type,
            :mentions_json,
            :reply_to,
            :raw_payload_json,
            :transaction_time,
            :valid_time_start,
            :valid_time_end,
            :source_url,
            :created_at
        )
        """,
        [serialize_raw_event(event) for event in events],
    )
    connection.commit()


def insert_memory_object(connection: sqlite3.Connection, memory: MemoryObject) -> None:
    """Persist one structured memory object."""
    connection.execute(
        """
        INSERT OR REPLACE INTO memory_objects (
            memory_id,
            memory_type,
            scope,
            tenant_id,
            project_id,
            user_id,
            topic,
            title,
            content,
            rationale_json,
            objections_json,
            tags_json,
            status,
            version,
            confidence,
            importance,
            valid_time_start,
            valid_time_end,
            transaction_time,
            supersedes,
            superseded_by,
            created_at,
            updated_at
        ) VALUES (
            :memory_id,
            :memory_type,
            :scope,
            :tenant_id,
            :project_id,
            :user_id,
            :topic,
            :title,
            :content,
            :rationale_json,
            :objections_json,
            :tags_json,
            :status,
            :version,
            :confidence,
            :importance,
            :valid_time_start,
            :valid_time_end,
            :transaction_time,
            :supersedes,
            :superseded_by,
            :created_at,
            :updated_at
        )
        """,
        serialize_memory_object(memory),
    )
    connection.commit()


def insert_memory_sources(connection: sqlite3.Connection, sources: list[MemorySource]) -> None:
    """Persist provenance rows that link memories back to raw events."""
    connection.executemany(
        """
        INSERT OR REPLACE INTO memory_sources (
            id,
            memory_id,
            event_id,
            evidence_type,
            quote,
            source_url,
            created_at
        ) VALUES (
            :id,
            :memory_id,
            :event_id,
            :evidence_type,
            :quote,
            :source_url,
            :created_at
        )
        """,
        [source.model_dump() for source in sources],
    )
    connection.commit()


def insert_memory_edge(connection: sqlite3.Connection, edge: MemoryEdge) -> None:
    """Persist a relation edge between memory objects."""
    connection.execute(
        """
        INSERT OR REPLACE INTO memory_edges (
            edge_id,
            source_memory_id,
            target_memory_id,
            relation_type,
            reason,
            confidence,
            created_at
        ) VALUES (
            :edge_id,
            :source_memory_id,
            :target_memory_id,
            :relation_type,
            :reason,
            :confidence,
            :created_at
        )
        """,
        edge.model_dump(),
    )
    connection.commit()


def insert_policy_action(connection: sqlite3.Connection, action: PolicyAction) -> None:
    """Persist a policy audit record for later traceability."""
    connection.execute(
        """
        INSERT OR REPLACE INTO policy_actions (
            action_id,
            action_type,
            project_id,
            input_json,
            candidate_json,
            decision,
            reason,
            confidence,
            created_at
        ) VALUES (
            :action_id,
            :action_type,
            :project_id,
            :input_json,
            :candidate_json,
            :decision,
            :reason,
            :confidence,
            :created_at
        )
        """,
        serialize_policy_action(action),
    )
    connection.commit()


def serialize_raw_event(event: RawEvent) -> dict[str, Any]:
    """Convert list/dict fields into JSON strings before SQLite insertion."""
    data = event.model_dump()
    data["mentions_json"] = json.dumps(data.pop("mentions"), ensure_ascii=False)
    data["raw_payload_json"] = json.dumps(data.pop("raw_payload"), ensure_ascii=False)
    return data


def serialize_memory_object(memory: MemoryObject) -> dict[str, Any]:
    """Serialize MemoryObject fields that SQLite stores as JSON text.

    Note that source_event_ids are stored in the dedicated memory_sources table
    rather than duplicated inside memory_objects.
    """
    data = memory.model_dump()
    data["rationale_json"] = json.dumps(data.pop("rationale"), ensure_ascii=False)
    data["objections_json"] = json.dumps(data.pop("objections"), ensure_ascii=False)
    data["tags_json"] = json.dumps(data.pop("tags"), ensure_ascii=False)
    data.pop("source_event_ids")
    return data


def serialize_policy_action(action: PolicyAction) -> dict[str, Any]:
    """Serialize structured policy inputs for SQLite audit storage."""
    data = action.model_dump()
    data["input_json"] = json.dumps(data.pop("input_payload"), ensure_ascii=False)
    data["candidate_json"] = json.dumps(data.pop("candidate_payload"), ensure_ascii=False)
    return data
