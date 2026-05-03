from __future__ import annotations

"""Shared ingestion helpers used by both CLI scripts and HTTP routes."""

from app.core.extractor import MemoryExtractor
from app.core.consolidator import MemoryConsolidator
from app.core.reconciler import MemoryReconciler
from app.core.topic_tracker import TopicTracker
from app.core.window_builder import WindowBuilder
from app.storage.db import (
    get_processing_cursor,
    insert_raw_events,
    list_recent_raw_events,
    upsert_processing_cursor,
    upsert_chat,
    upsert_chat_membership,
    upsert_project,
    upsert_project_chat,
    upsert_tenant,
    upsert_user,
)
from app.storage.models import (
    Chat,
    ChatMembership,
    DiscussionWindow,
    MemoryObject,
    ProcessingCursor,
    Project,
    ProjectChat,
    RawEvent,
    Tenant,
    TopicAssignment,
    User,
)


def sync_context_entities(connection, events: list[RawEvent]) -> None:
    """Persist lightweight tenant/project/chat/user metadata from an event batch."""
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


def ingest_events(connection, events: list[RawEvent]) -> None:
    """Write raw events and related lightweight context entities."""
    insert_raw_events(connection, events)
    sync_context_entities(connection, events)


def extract_and_reconcile(
    connection,
    events: list[RawEvent],
    extractor: MemoryExtractor | None = None,
    reconciler: MemoryReconciler | None = None,
) -> list[MemoryObject]:
    """Extract memories from bounded discussion windows and reconcile them."""
    extractor = extractor or MemoryExtractor()
    consolidator = MemoryConsolidator()
    reconciler = reconciler or MemoryReconciler()
    memories: list[MemoryObject] = []
    for stream_events in group_events_by_stream(events):
        memories.extend(
            _extract_stream_memories(
                connection,
                stream_events,
                extractor=extractor,
            )
        )

    memories = consolidator.consolidate(memories)

    reconciled_memories: list[MemoryObject] = []
    for memory in memories:
        reconciled_memory, _ = reconciler.reconcile(connection, memory)
        reconciled_memories.append(reconciled_memory)

    return reconciled_memories


def group_events_by_stream(events: list[RawEvent]) -> list[list[RawEvent]]:
    """Group events by project/chat stream so cursors can advance independently."""
    buckets: dict[tuple[str | None, str | None], list[RawEvent]] = {}
    for event in sorted(events, key=lambda item: (item.project_id or "", item.chat_id or "", item.transaction_time, item.event_id)):
        key = (event.project_id, event.chat_id)
        buckets.setdefault(key, []).append(event)
    return list(buckets.values())


def _extract_stream_memories(
    connection,
    stream_events: list[RawEvent],
    *,
    extractor: MemoryExtractor,
) -> list[MemoryObject]:
    """Extract memories for one stream using cursor-aware incremental windows."""
    if not stream_events:
        return []

    window_builder = WindowBuilder()
    topic_tracker = TopicTracker()
    project_id = stream_events[0].project_id
    chat_id = stream_events[0].chat_id
    cursor = get_processing_cursor(connection, project_id, chat_id)
    history_tail = list_recent_raw_events(
        connection,
        project_id=project_id,
        chat_id=chat_id,
        before_time=cursor.last_event_time if cursor else None,
        limit=6,
    )
    combined_events = deduplicate_events(history_tail + stream_events)
    event_index = {event.event_id: event for event in combined_events}
    new_event_ids = {event.event_id for event in stream_events}

    windows = window_builder.build_windows(combined_events)
    topic_assignments = assign_topics_for_windows(topic_tracker, windows)
    merged_windows, merged_assignments = merge_windows_for_extraction(windows, topic_assignments, event_index)
    selected_windows = [window for window in merged_windows if any(event_id in new_event_ids for event_id in window.event_ids)]
    selected_assignments = {
        window.window_id: merged_assignments[window.window_id]
        for window in selected_windows
        if window.window_id in merged_assignments
    }
    extracted = extractor.extract_from_windows(selected_windows, event_index, selected_assignments)

    last_event = max(stream_events, key=lambda event: (event.transaction_time, event.event_id))
    upsert_processing_cursor(
        connection,
        ProcessingCursor(
            project_id=project_id,
            chat_id=chat_id,
            last_event_id=last_event.event_id,
            last_event_time=last_event.transaction_time,
        ),
    )
    return extracted


def deduplicate_events(events: list[RawEvent]) -> list[RawEvent]:
    """Keep only the latest occurrence of each event_id while preserving order."""
    ordered: list[RawEvent] = []
    seen: set[str] = set()
    for event in sorted(events, key=lambda item: (item.transaction_time, item.event_id)):
        if event.event_id in seen:
            continue
        ordered.append(event)
        seen.add(event.event_id)
    return ordered


def assign_topics_for_windows(
    topic_tracker: TopicTracker,
    windows: list[DiscussionWindow],
) -> dict[str, TopicAssignment]:
    """Assign coarse topics sequentially across one stream's windows."""
    previous_assignments: list[TopicAssignment] = []
    assignments: dict[str, TopicAssignment] = {}
    for window in windows:
        assignment = topic_tracker.assign_topic(window, previous_assignments)
        assignments[window.window_id] = assignment
        previous_assignments.append(assignment)
    return assignments


def merge_windows_for_extraction(
    windows: list[DiscussionWindow],
    assignments: dict[str, TopicAssignment],
    event_index: dict[str, RawEvent],
) -> tuple[list[DiscussionWindow], dict[str, TopicAssignment]]:
    """Merge adjacent or bridged windows so extraction windows are less fragmented."""
    if not windows:
        return [], {}

    merged_windows: list[DiscussionWindow] = []
    merged_assignments: dict[str, TopicAssignment] = {}
    index = 0
    bridge_labels = {"timeline", "reporting"}

    while index < len(windows):
        current_window = windows[index]
        current_assignment = assignments[current_window.window_id]

        if index + 2 < len(windows):
            middle_window = windows[index + 1]
            next_window = windows[index + 2]
            middle_assignment = assignments[middle_window.window_id]
            next_assignment = assignments[next_window.window_id]
            if (
                current_assignment.label == next_assignment.label
                and middle_assignment.label in bridge_labels
                and middle_window.message_count <= 2
            ):
                merged = merge_window_group([current_window, middle_window, next_window], event_index, split_reason="bridged_topic_merge")
                merged_windows.append(merged)
                merged_assignments[merged.window_id] = TopicAssignment(
                    label=current_assignment.label,
                    confidence=max(current_assignment.confidence, next_assignment.confidence),
                    assignment_reason="bridged_topic_merge",
                    matched_markers=current_assignment.matched_markers or next_assignment.matched_markers,
                )
                index += 3
                continue

        if index + 1 < len(windows):
            next_window = windows[index + 1]
            next_assignment = assignments[next_window.window_id]
            if current_assignment.label == next_assignment.label:
                merged = merge_window_group([current_window, next_window], event_index, split_reason="adjacent_topic_merge")
                merged_windows.append(merged)
                merged_assignments[merged.window_id] = TopicAssignment(
                    label=current_assignment.label,
                    confidence=max(current_assignment.confidence, next_assignment.confidence),
                    assignment_reason="adjacent_topic_merge",
                    matched_markers=current_assignment.matched_markers or next_assignment.matched_markers,
                )
                index += 2
                continue

        merged_windows.append(current_window)
        merged_assignments[current_window.window_id] = current_assignment
        index += 1

    return merged_windows, merged_assignments


def merge_window_group(
    windows: list[DiscussionWindow],
    event_index: dict[str, RawEvent],
    *,
    split_reason: str,
) -> DiscussionWindow:
    """Combine multiple windows into one larger extraction window."""
    merged_event_ids: list[str] = []
    for window in windows:
        for event_id in window.event_ids:
            if event_id not in merged_event_ids:
                merged_event_ids.append(event_id)

    merged_events = [event_index[event_id] for event_id in merged_event_ids if event_id in event_index]
    return DiscussionWindow(
        tenant_id=windows[0].tenant_id,
        project_id=windows[0].project_id,
        chat_id=windows[0].chat_id,
        thread_id=windows[0].thread_id,
        topic_hint=windows[0].topic_hint,
        split_reason=split_reason,
        start_time=windows[0].start_time,
        end_time=windows[-1].end_time,
        event_ids=merged_event_ids,
        message_count=len(merged_event_ids),
        raw_summary=" | ".join(event.content for event in merged_events if event.content),
    )
