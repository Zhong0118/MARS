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

from app.storage.models import (
    Chat,
    ChatMembership,
    EvidencePack,
    MemoryEdge,
    MemoryObject,
    MemorySource,
    PolicyAction,
    Project,
    ProjectChat,
    PushLog,
    RawEvent,
    Tenant,
    User,
    make_id,
    utc_now_iso,
)


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
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(db_path: Path | None = None) -> Path:
    """Create the SQLite database file and all required tables."""
    target = db_path or DB_PATH
    ensure_storage_dirs()

    with get_connection(target) as connection:
        cursor = connection.cursor()
        for statement in table_schema_statements():
            cursor.execute(statement)
        migrate_legacy_schema(connection)
        for statement in index_schema_statements():
            cursor.execute(statement)
        connection.commit()

    return target


def table_schema_statements() -> list[str]:
    """Return table DDL statements for the MVP schema."""
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
            version_group_id TEXT,
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
            created_at TEXT,
            FOREIGN KEY(memory_id) REFERENCES memory_objects(memory_id),
            FOREIGN KEY(event_id) REFERENCES raw_events(event_id)
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
            tenant_id TEXT,
            project_id TEXT,
            chat_id TEXT,
            thread_id TEXT,
            actor_id TEXT,
            memory_id TEXT,
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
            tenant_id TEXT,
            project_id TEXT,
            chat_id TEXT,
            thread_id TEXT,
            requester_id TEXT,
            query_type TEXT,
            time_scope TEXT,
            top_k INTEGER,
            status_filter TEXT,
            retrieval_method TEXT,
            retrieved_memory_ids_json TEXT,
            selected_memory_ids_json TEXT,
            score_json TEXT,
            latency_ms INTEGER,
            created_at TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS push_logs (
            push_id TEXT PRIMARY KEY,
            trigger_type TEXT,
            tenant_id TEXT,
            project_id TEXT,
            chat_id TEXT,
            user_id TEXT,
            memory_id TEXT,
            push_channel TEXT,
            push_content TEXT,
            should_push INTEGER,
            policy_action_id TEXT,
            user_feedback TEXT,
            created_at TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS tenants (
            tenant_id TEXT PRIMARY KEY,
            tenant_name TEXT,
            source_type TEXT,
            raw_payload_json TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            tenant_id TEXT,
            display_name TEXT,
            source_type TEXT,
            source_user_id TEXT,
            open_id TEXT,
            union_id TEXT,
            raw_payload_json TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS chats (
            chat_id TEXT PRIMARY KEY,
            tenant_id TEXT,
            chat_name TEXT,
            chat_type TEXT,
            source_type TEXT,
            source_chat_id TEXT,
            raw_payload_json TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            tenant_id TEXT,
            project_name TEXT,
            description TEXT,
            status TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS project_chats (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            relation_type TEXT,
            created_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(project_id),
            FOREIGN KEY(chat_id) REFERENCES chats(chat_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_memberships (
            id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT,
            joined_at TEXT,
            left_at TEXT,
            created_at TEXT,
            FOREIGN KEY(chat_id) REFERENCES chats(chat_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id)
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


def index_schema_statements() -> list[str]:
    """Return index DDL statements for the MVP schema."""
    return [
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_events_source_unique
        ON raw_events(source_type, tenant_id, chat_id, source_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_raw_events_tenant_project_time
        ON raw_events(tenant_id, project_id, transaction_time);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_raw_events_chat_time
        ON raw_events(chat_id, transaction_time);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_raw_events_actor_time
        ON raw_events(actor_id, transaction_time);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_project_status
        ON memory_objects(project_id, status);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_project_topic
        ON memory_objects(project_id, topic);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_type_status
        ON memory_objects(memory_type, status);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_valid_time
        ON memory_objects(valid_time_start, valid_time_end);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_version_group
        ON memory_objects(version_group_id, version);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_sources_memory
        ON memory_sources(memory_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_sources_event
        ON memory_sources(event_id);
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_sources_unique
        ON memory_sources(memory_id, event_id, evidence_type);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_edges_source
        ON memory_edges(source_memory_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_memory_edges_target
        ON memory_edges(target_memory_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_policy_actions_project_time
        ON policy_actions(project_id, created_at);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_retrieval_logs_project_time
        ON retrieval_logs(project_id, created_at);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_push_logs_memory_chat_time
        ON push_logs(memory_id, chat_id, created_at);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_push_logs_project_time
        ON push_logs(project_id, created_at);
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_chats_unique
        ON project_chats(project_id, chat_id);
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_memberships_unique
        ON chat_memberships(chat_id, user_id);
        """,
    ]


def schema_statements() -> list[str]:
    """Return the full ordered schema list for compatibility with old callers."""
    return [*table_schema_statements(), *index_schema_statements()]


def migrate_legacy_schema(connection: sqlite3.Connection) -> None:
    """Add newly introduced columns to existing SQLite tables when needed."""
    add_column_if_missing(connection, "memory_objects", "version_group_id TEXT")
    add_column_if_missing(connection, "policy_actions", "tenant_id TEXT")
    add_column_if_missing(connection, "policy_actions", "chat_id TEXT")
    add_column_if_missing(connection, "policy_actions", "thread_id TEXT")
    add_column_if_missing(connection, "policy_actions", "actor_id TEXT")
    add_column_if_missing(connection, "policy_actions", "memory_id TEXT")
    add_column_if_missing(connection, "retrieval_logs", "tenant_id TEXT")
    add_column_if_missing(connection, "retrieval_logs", "chat_id TEXT")
    add_column_if_missing(connection, "retrieval_logs", "thread_id TEXT")
    add_column_if_missing(connection, "retrieval_logs", "requester_id TEXT")
    add_column_if_missing(connection, "retrieval_logs", "query_type TEXT")
    add_column_if_missing(connection, "retrieval_logs", "top_k INTEGER")
    add_column_if_missing(connection, "retrieval_logs", "status_filter TEXT")
    add_column_if_missing(connection, "retrieval_logs", "retrieval_method TEXT")
    add_column_if_missing(connection, "retrieval_logs", "score_json TEXT")


def add_column_if_missing(connection: sqlite3.Connection, table_name: str, column_definition: str) -> None:
    """Alter a table to add one missing column without dropping existing data."""
    column_name = column_definition.split()[0]
    existing_columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing_columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")


def insert_raw_events(connection: sqlite3.Connection, events: list[RawEvent]) -> None:
    """Persist normalized RawEvent records without rewriting raw ledger history."""
    connection.executemany(
        """
        INSERT OR IGNORE INTO raw_events (
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
    """Persist one structured memory object with SQLite upsert semantics."""
    connection.execute(
        """
        INSERT INTO memory_objects (
            memory_id,
            version_group_id,
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
            :version_group_id,
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
        ON CONFLICT(memory_id) DO UPDATE SET
            version_group_id = excluded.version_group_id,
            memory_type = excluded.memory_type,
            scope = excluded.scope,
            tenant_id = excluded.tenant_id,
            project_id = excluded.project_id,
            user_id = excluded.user_id,
            topic = excluded.topic,
            title = excluded.title,
            content = excluded.content,
            rationale_json = excluded.rationale_json,
            objections_json = excluded.objections_json,
            tags_json = excluded.tags_json,
            status = excluded.status,
            version = excluded.version,
            confidence = excluded.confidence,
            importance = excluded.importance,
            valid_time_start = excluded.valid_time_start,
            valid_time_end = excluded.valid_time_end,
            transaction_time = excluded.transaction_time,
            supersedes = excluded.supersedes,
            superseded_by = excluded.superseded_by,
            updated_at = excluded.updated_at
        """,
        serialize_memory_object(memory),
    )
    connection.commit()


def insert_memory_sources(connection: sqlite3.Connection, sources: list[MemorySource]) -> None:
    """Persist provenance rows that link memories back to raw events."""
    connection.executemany(
        """
        INSERT OR IGNORE INTO memory_sources (
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
        INSERT INTO memory_edges (
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
        ON CONFLICT(edge_id) DO UPDATE SET
            source_memory_id = excluded.source_memory_id,
            target_memory_id = excluded.target_memory_id,
            relation_type = excluded.relation_type,
            reason = excluded.reason,
            confidence = excluded.confidence,
            created_at = excluded.created_at
        """,
        edge.model_dump(),
    )
    connection.commit()


def insert_policy_action(connection: sqlite3.Connection, action: PolicyAction) -> None:
    """Persist a policy audit record for later traceability."""
    connection.execute(
        """
        INSERT INTO policy_actions (
            action_id,
            action_type,
            tenant_id,
            project_id,
            chat_id,
            thread_id,
            actor_id,
            memory_id,
            input_json,
            candidate_json,
            decision,
            reason,
            confidence,
            created_at
        ) VALUES (
            :action_id,
            :action_type,
            :tenant_id,
            :project_id,
            :chat_id,
            :thread_id,
            :actor_id,
            :memory_id,
            :input_json,
            :candidate_json,
            :decision,
            :reason,
            :confidence,
            :created_at
        )
        ON CONFLICT(action_id) DO UPDATE SET
            action_type = excluded.action_type,
            tenant_id = excluded.tenant_id,
            project_id = excluded.project_id,
            chat_id = excluded.chat_id,
            thread_id = excluded.thread_id,
            actor_id = excluded.actor_id,
            memory_id = excluded.memory_id,
            input_json = excluded.input_json,
            candidate_json = excluded.candidate_json,
            decision = excluded.decision,
            reason = excluded.reason,
            confidence = excluded.confidence,
            created_at = excluded.created_at
        """,
        serialize_policy_action(action),
    )
    connection.commit()


def insert_push_log(connection: sqlite3.Connection, push_log: PushLog) -> None:
    """Persist a push/summoning audit record."""
    connection.execute(
        """
        INSERT INTO push_logs (
            push_id,
            trigger_type,
            tenant_id,
            project_id,
            chat_id,
            user_id,
            memory_id,
            push_channel,
            push_content,
            should_push,
            policy_action_id,
            user_feedback,
            created_at
        ) VALUES (
            :push_id,
            :trigger_type,
            :tenant_id,
            :project_id,
            :chat_id,
            :user_id,
            :memory_id,
            :push_channel,
            :push_content,
            :should_push,
            :policy_action_id,
            :user_feedback,
            :created_at
        )
        ON CONFLICT(push_id) DO UPDATE SET
            trigger_type = excluded.trigger_type,
            tenant_id = excluded.tenant_id,
            project_id = excluded.project_id,
            chat_id = excluded.chat_id,
            user_id = excluded.user_id,
            memory_id = excluded.memory_id,
            push_channel = excluded.push_channel,
            push_content = excluded.push_content,
            should_push = excluded.should_push,
            policy_action_id = excluded.policy_action_id,
            user_feedback = excluded.user_feedback,
            created_at = excluded.created_at
        """,
        serialize_push_log(push_log),
    )
    connection.commit()


def upsert_tenant(connection: sqlite3.Connection, tenant: Tenant) -> None:
    """Insert or update tenant metadata used by future Feishu/OpenClaw adapters."""
    connection.execute(
        """
        INSERT INTO tenants (
            tenant_id,
            tenant_name,
            source_type,
            raw_payload_json,
            created_at,
            updated_at
        ) VALUES (
            :tenant_id,
            :tenant_name,
            :source_type,
            :raw_payload_json,
            :created_at,
            :updated_at
        )
        ON CONFLICT(tenant_id) DO UPDATE SET
            tenant_name = excluded.tenant_name,
            source_type = excluded.source_type,
            raw_payload_json = excluded.raw_payload_json,
            updated_at = excluded.updated_at
        """,
        serialize_tenant(tenant),
    )
    connection.commit()


def upsert_user(connection: sqlite3.Connection, user: User) -> None:
    """Insert or update user metadata."""
    connection.execute(
        """
        INSERT INTO users (
            user_id,
            tenant_id,
            display_name,
            source_type,
            source_user_id,
            open_id,
            union_id,
            raw_payload_json,
            created_at,
            updated_at
        ) VALUES (
            :user_id,
            :tenant_id,
            :display_name,
            :source_type,
            :source_user_id,
            :open_id,
            :union_id,
            :raw_payload_json,
            :created_at,
            :updated_at
        )
        ON CONFLICT(user_id) DO UPDATE SET
            tenant_id = excluded.tenant_id,
            display_name = excluded.display_name,
            source_type = excluded.source_type,
            source_user_id = excluded.source_user_id,
            open_id = excluded.open_id,
            union_id = excluded.union_id,
            raw_payload_json = excluded.raw_payload_json,
            updated_at = excluded.updated_at
        """,
        serialize_user(user),
    )
    connection.commit()


def upsert_chat(connection: sqlite3.Connection, chat: Chat) -> None:
    """Insert or update chat metadata."""
    connection.execute(
        """
        INSERT INTO chats (
            chat_id,
            tenant_id,
            chat_name,
            chat_type,
            source_type,
            source_chat_id,
            raw_payload_json,
            created_at,
            updated_at
        ) VALUES (
            :chat_id,
            :tenant_id,
            :chat_name,
            :chat_type,
            :source_type,
            :source_chat_id,
            :raw_payload_json,
            :created_at,
            :updated_at
        )
        ON CONFLICT(chat_id) DO UPDATE SET
            tenant_id = excluded.tenant_id,
            chat_name = excluded.chat_name,
            chat_type = excluded.chat_type,
            source_type = excluded.source_type,
            source_chat_id = excluded.source_chat_id,
            raw_payload_json = excluded.raw_payload_json,
            updated_at = excluded.updated_at
        """,
        serialize_chat(chat),
    )
    connection.commit()


def upsert_project(connection: sqlite3.Connection, project: Project) -> None:
    """Insert or update project metadata."""
    connection.execute(
        """
        INSERT INTO projects (
            project_id,
            tenant_id,
            project_name,
            description,
            status,
            created_at,
            updated_at
        ) VALUES (
            :project_id,
            :tenant_id,
            :project_name,
            :description,
            :status,
            :created_at,
            :updated_at
        )
        ON CONFLICT(project_id) DO UPDATE SET
            tenant_id = excluded.tenant_id,
            project_name = excluded.project_name,
            description = excluded.description,
            status = excluded.status,
            updated_at = excluded.updated_at
        """,
        project.model_dump(),
    )
    connection.commit()


def upsert_project_chat(connection: sqlite3.Connection, project_chat: ProjectChat) -> None:
    """Insert or update the mapping between a project and a chat."""
    connection.execute(
        """
        INSERT INTO project_chats (
            id,
            project_id,
            chat_id,
            relation_type,
            created_at
        ) VALUES (
            :id,
            :project_id,
            :chat_id,
            :relation_type,
            :created_at
        )
        ON CONFLICT(project_id, chat_id) DO UPDATE SET
            relation_type = excluded.relation_type
        """,
        project_chat.model_dump(),
    )
    connection.commit()


def upsert_chat_membership(connection: sqlite3.Connection, membership: ChatMembership) -> None:
    """Insert or update a chat membership relation."""
    connection.execute(
        """
        INSERT INTO chat_memberships (
            id,
            chat_id,
            user_id,
            role,
            joined_at,
            left_at,
            created_at
        ) VALUES (
            :id,
            :chat_id,
            :user_id,
            :role,
            :joined_at,
            :left_at,
            :created_at
        )
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
            role = excluded.role,
            joined_at = excluded.joined_at,
            left_at = excluded.left_at
        """,
        membership.model_dump(),
    )
    connection.commit()


def update_memory_status(
    connection: sqlite3.Connection,
    memory_id: str,
    status: str,
    updated_at: str | None = None,
) -> None:
    """Update only the memory status and audit timestamp."""
    connection.execute(
        """
        UPDATE memory_objects
        SET status = ?, updated_at = ?
        WHERE memory_id = ?
        """,
        (status, updated_at or utc_now_iso(), memory_id),
    )
    connection.commit()


def mark_memory_superseded(
    connection: sqlite3.Connection,
    old_memory_id: str,
    new_memory_id: str,
    updated_at: str | None = None,
) -> None:
    """Link an old memory to its replacement and mark it superseded."""
    timestamp = updated_at or utc_now_iso()
    connection.execute(
        """
        UPDATE memory_objects
        SET status = ?, superseded_by = ?, updated_at = ?
        WHERE memory_id = ?
        """,
        ("superseded", new_memory_id, timestamp, old_memory_id),
    )
    connection.execute(
        """
        UPDATE memory_objects
        SET supersedes = ?, updated_at = ?
        WHERE memory_id = ?
        """,
        (old_memory_id, timestamp, new_memory_id),
    )
    connection.commit()


def get_memory_by_id(connection: sqlite3.Connection, memory_id: str) -> MemoryObject | None:
    """Load one memory object together with its source event IDs."""
    row = connection.execute(
        """
        SELECT *
        FROM memory_objects
        WHERE memory_id = ?
        """,
        (memory_id,),
    ).fetchone()
    if row is None:
        return None
    return deserialize_memory_object(connection, row)


def list_active_memories_by_project_topic(
    connection: sqlite3.Connection,
    project_id: str,
    topic: str | None = None,
) -> list[MemoryObject]:
    """List active memories filtered by project and optionally topic."""
    if topic:
        rows = connection.execute(
            """
            SELECT *
            FROM memory_objects
            WHERE project_id = ? AND status = 'active' AND topic = ?
            ORDER BY updated_at DESC, created_at DESC
            """,
            (project_id, topic),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT *
            FROM memory_objects
            WHERE project_id = ? AND status = 'active'
            ORDER BY updated_at DESC, created_at DESC
            """,
            (project_id,),
    ).fetchall()
    return [deserialize_memory_object(connection, row) for row in rows]


def list_memories(
    connection: sqlite3.Connection,
    project_id: str | None = None,
    status: str | None = "active",
) -> list[MemoryObject]:
    """List memories with optional project and status filters."""
    query = """
        SELECT *
        FROM memory_objects
        WHERE 1 = 1
    """
    params: list[str] = []

    if project_id is not None:
        query += " AND project_id = ?"
        params.append(project_id)

    if status is not None:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY updated_at DESC, created_at DESC"
    rows = connection.execute(query, params).fetchall()
    return [deserialize_memory_object(connection, row) for row in rows]


def insert_retrieval_log(
    connection: sqlite3.Connection,
    *,
    query: str,
    project_id: str | None,
    retrieved_memory_ids: list[str],
    selected_memory_ids: list[str],
    latency_ms: int,
    tenant_id: str | None = None,
    chat_id: str | None = None,
    thread_id: str | None = None,
    requester_id: str | None = None,
    query_type: str = "keyword",
    time_scope: str | None = None,
    top_k: int | None = None,
    status_filter: str | None = "active",
    retrieval_method: str = "keyword",
    score_items: list[dict[str, Any]] | None = None,
) -> None:
    """Persist a retrieval audit row for search debugging and later benchmark use."""
    connection.execute(
        """
        INSERT INTO retrieval_logs (
            log_id,
            query,
            tenant_id,
            project_id,
            chat_id,
            thread_id,
            requester_id,
            query_type,
            time_scope,
            top_k,
            status_filter,
            retrieval_method,
            retrieved_memory_ids_json,
            selected_memory_ids_json,
            score_json,
            latency_ms,
            created_at
        ) VALUES (
            :log_id,
            :query,
            :tenant_id,
            :project_id,
            :chat_id,
            :thread_id,
            :requester_id,
            :query_type,
            :time_scope,
            :top_k,
            :status_filter,
            :retrieval_method,
            :retrieved_memory_ids_json,
            :selected_memory_ids_json,
            :score_json,
            :latency_ms,
            :created_at
        )
        """,
        {
            "log_id": make_id("ret"),
            "query": query,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "chat_id": chat_id,
            "thread_id": thread_id,
            "requester_id": requester_id,
            "query_type": query_type,
            "time_scope": time_scope,
            "top_k": top_k,
            "status_filter": status_filter,
            "retrieval_method": retrieval_method,
            "retrieved_memory_ids_json": json.dumps(retrieved_memory_ids, ensure_ascii=False),
            "selected_memory_ids_json": json.dumps(selected_memory_ids, ensure_ascii=False),
            "score_json": json.dumps(score_items or [], ensure_ascii=False),
            "latency_ms": latency_ms,
            "created_at": utc_now_iso(),
        },
    )
    connection.commit()


def build_evidence_pack(memory: MemoryObject, score: float) -> EvidencePack:
    """Convert a stored MemoryObject into the retrieval-facing response model."""
    return EvidencePack(
        memory_id=memory.memory_id,
        title=memory.title,
        content=memory.content,
        status=memory.status,
        score=score,
        source_event_ids=memory.source_event_ids,
        rationale=memory.rationale,
        objections=memory.objections,
        topic=memory.topic,
        project_id=memory.project_id,
    )


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


def serialize_push_log(push_log: PushLog) -> dict[str, Any]:
    """Convert boolean fields into SQLite-compatible scalars."""
    data = push_log.model_dump()
    data["should_push"] = int(data["should_push"])
    return data


def serialize_tenant(tenant: Tenant) -> dict[str, Any]:
    """Serialize tenant payloads into JSON text."""
    data = tenant.model_dump()
    data["raw_payload_json"] = json.dumps(data.pop("raw_payload"), ensure_ascii=False)
    return data


def serialize_user(user: User) -> dict[str, Any]:
    """Serialize user payloads into JSON text."""
    data = user.model_dump()
    data["raw_payload_json"] = json.dumps(data.pop("raw_payload"), ensure_ascii=False)
    return data


def serialize_chat(chat: Chat) -> dict[str, Any]:
    """Serialize chat payloads into JSON text."""
    data = chat.model_dump()
    data["raw_payload_json"] = json.dumps(data.pop("raw_payload"), ensure_ascii=False)
    return data


def deserialize_memory_object(connection: sqlite3.Connection, row: sqlite3.Row) -> MemoryObject:
    """Build a MemoryObject from a SQLite row plus linked provenance rows."""
    source_rows = connection.execute(
        """
        SELECT event_id
        FROM memory_sources
        WHERE memory_id = ?
        ORDER BY rowid ASC
        """,
        (row["memory_id"],),
    ).fetchall()

    return MemoryObject(
        memory_id=row["memory_id"],
        version_group_id=row["version_group_id"],
        memory_type=row["memory_type"],
        scope=row["scope"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        user_id=row["user_id"],
        topic=row["topic"],
        title=row["title"],
        content=row["content"],
        rationale=json.loads(row["rationale_json"] or "[]"),
        objections=json.loads(row["objections_json"] or "[]"),
        tags=json.loads(row["tags_json"] or "[]"),
        status=row["status"],
        version=row["version"],
        confidence=row["confidence"],
        importance=row["importance"],
        valid_time_start=row["valid_time_start"],
        valid_time_end=row["valid_time_end"],
        transaction_time=row["transaction_time"],
        source_event_ids=[source_row["event_id"] for source_row in source_rows],
        supersedes=row["supersedes"],
        superseded_by=row["superseded_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
