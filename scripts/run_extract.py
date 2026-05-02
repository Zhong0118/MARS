from __future__ import annotations

"""CLI entrypoint for sample-chat ingestion and extraction.

Phase 2 stores normalized RawEvent records.
Phase 3 runs deterministic MockLLM extraction and persists MemoryObject plus
MemorySource rows.
"""

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.extractor import MemoryExtractor
from app.connectors.sample_loader import load_raw_events
from app.storage.db import (
    get_connection,
    initialize_database,
    insert_memory_object,
    insert_memory_sources,
    insert_raw_events,
    upsert_chat,
    upsert_chat_membership,
    upsert_project,
    upsert_project_chat,
    upsert_tenant,
    upsert_user,
)
from app.storage.models import Chat, ChatMembership, MemoryObject, MemorySource, Project, ProjectChat, Tenant, User


def build_parser() -> argparse.ArgumentParser:
    """Build command-line arguments for the extraction script."""
    parser = argparse.ArgumentParser(description="Ingest sample chat JSON and optionally extract memories.")
    parser.add_argument("--input", required=True, help="Path to sample chat JSON file.")
    parser.add_argument("--ingest-only", action="store_true", help="Only persist raw events, skip memory extraction.")
    return parser


def sync_context_entities(connection, events) -> None:
    """Persist lightweight tenant/project/chat/user metadata from the event batch."""
    seen_tenants: set[str] = set()
    seen_projects: set[str] = set()
    seen_chats: set[str] = set()
    seen_users: set[str] = set()
    seen_project_chats: set[tuple[str, str]] = set()
    seen_memberships: set[tuple[str, str]] = set()

    for event in events:
        if event.tenant_id and event.tenant_id not in seen_tenants:
            upsert_tenant(
                connection,
                Tenant(
                    tenant_id=event.tenant_id,
                    tenant_name=event.tenant_id,
                    source_type=event.source_type,
                ),
            )
            seen_tenants.add(event.tenant_id)

        if event.project_id and event.project_id not in seen_projects:
            upsert_project(
                connection,
                Project(
                    project_id=event.project_id,
                    tenant_id=event.tenant_id,
                    project_name=event.project_id,
                    status="active",
                ),
            )
            seen_projects.add(event.project_id)

        if event.chat_id and event.chat_id not in seen_chats:
            upsert_chat(
                connection,
                Chat(
                    chat_id=event.chat_id,
                    tenant_id=event.tenant_id,
                    chat_name=event.chat_id,
                    chat_type="group",
                    source_type=event.source_type,
                    source_chat_id=event.chat_id,
                ),
            )
            seen_chats.add(event.chat_id)

        if event.actor_id and event.actor_id not in seen_users:
            upsert_user(
                connection,
                User(
                    user_id=event.actor_id,
                    tenant_id=event.tenant_id,
                    display_name=event.actor_name,
                    source_type=event.source_type,
                    source_user_id=event.actor_id,
                ),
            )
            seen_users.add(event.actor_id)

        if event.project_id and event.chat_id:
            project_chat_key = (event.project_id, event.chat_id)
            if project_chat_key not in seen_project_chats:
                upsert_project_chat(
                    connection,
                    ProjectChat(
                        project_id=event.project_id,
                        chat_id=event.chat_id,
                        relation_type="primary",
                    ),
                )
                seen_project_chats.add(project_chat_key)

        if event.chat_id and event.actor_id:
            membership_key = (event.chat_id, event.actor_id)
            if membership_key not in seen_memberships:
                upsert_chat_membership(
                    connection,
                    ChatMembership(
                        chat_id=event.chat_id,
                        user_id=event.actor_id,
                        role="member",
                        joined_at=event.transaction_time,
                    ),
                )
                seen_memberships.add(membership_key)


def persist_extracted_memories(connection, memories) -> None:
    """Persist memory objects and their provenance links together."""
    for memory in memories:
        insert_memory_object(connection, memory)
        insert_memory_sources(
            connection,
            [
                MemorySource(memory_id=memory.memory_id, event_id=event_id)
                for event_id in memory.source_event_ids
            ],
        )


def print_memory_summary(memories: list[MemoryObject]) -> None:
    """Print a compact summary of extracted memories for developer feedback."""
    if not memories:
        print("No memories were extracted.")
        return

    print("Extracted memory summary:")
    for index, memory in enumerate(memories, start=1):
        print(f"[{index}] {memory.title}")
        print(f"memory_id: {memory.memory_id}")
        print(f"version_group_id: {memory.version_group_id}")
        print(f"memory_type: {memory.memory_type}")
        print(f"status: {memory.status}")
        print(f"topic: {memory.topic}")
        print(f"content: {memory.content}")
        print(f"source_event_count: {len(memory.source_event_ids)}")
        print(f"source_event_ids: {', '.join(memory.source_event_ids)}")
        if index != len(memories):
            print()


def main() -> None:
    """Initialize storage, ingest events, and optionally extract structured memories."""
    args = build_parser().parse_args()
    initialize_database()
    events = load_raw_events(args.input)

    with get_connection() as connection:
        insert_raw_events(connection, events)
        sync_context_entities(connection, events)

        if args.ingest_only:
            print(f"Ingested {len(events)} raw events from {args.input}")
            return

        extractor = MemoryExtractor()
        memories = extractor.extract(events)
        persist_extracted_memories(connection, memories)

    print(f"Ingested {len(events)} raw events and extracted {len(memories)} memories from {args.input}")
    print_memory_summary(memories)


if __name__ == "__main__":
    main()
