# MARS Database Schema

This document explains the current SQLite schema used by the local MARS MVP.

It focuses on:
- what each table is for
- how tables relate to each other
- which indexes exist and why
- which parts are required for the current MVP
- which parts are present now to reduce future migration pain

## 1. Design Principles

The database follows these rules:

- `raw_events` is the source-of-truth raw ledger
- external payloads must be normalized before they enter core logic
- `memory_objects` store structured memories, not raw chat text dumps
- provenance must be explicit through `memory_sources`
- state changes must be represented in data, not hidden in prompts
- database storage is primary; Markdown, reports, or future Feishu views are derived outputs

## 2. Schema Overview

The current schema has five layers:

### 2.1 Collaboration context

- `tenants`
- `users`
- `chats`
- `projects`
- `project_chats`
- `chat_memberships`

These tables are lightweight metadata tables that help future Feishu/OpenClaw
integration without forcing a full server design right now.

### 2.2 Raw ledger

- `raw_events`

This is the append-only event ledger.

### 2.3 Memory layer

- `memory_objects`
- `memory_sources`
- `memory_edges`

These tables store structured memory, provenance, and memory-to-memory
relations such as superseding.

### 2.4 Behavior and audit layer

- `policy_actions`
- `retrieval_logs`
- `push_logs`

These tables explain why the system acted, searched, or pushed.

### 2.5 Evaluation layer

- `benchmark_results`

This stores benchmark outcomes for later reporting.

## 3. Table-by-Table Details

### `raw_events`

Purpose:
- store every normalized external event
- preserve original payload in `raw_payload_json`
- support replay, auditing, and provenance

Important fields:
- `event_id`: internal primary key
- `event_type`: normalized internal event type, for example `message.created`
- `source_type`: where the event came from, for example `sample_chat`
- `source_id`: source-side event/message ID
- `tenant_id`, `project_id`, `chat_id`, `thread_id`
- `actor_id`, `actor_name`
- `content`, `content_type`
- `transaction_time`
- `valid_time_start`, `valid_time_end`
- `raw_payload_json`

Important behavior:
- insertion uses `INSERT OR IGNORE`
- duplicate source events are not allowed to overwrite history

### `memory_objects`

Purpose:
- store structured memories extracted from raw events

Important fields:
- `memory_id`
- `version_group_id`: groups multiple versions of the same long-lived memory
- `memory_type`: `decision`, `fact`, `procedure`, `risk`, `preference`, `episode`, `skill`
- `scope`: `user`, `team`, `project`, `org`
- `tenant_id`, `project_id`, `user_id`
- `topic`
- `title`, `content`
- `rationale_json`, `objections_json`, `tags_json`
- `status`
- `version`
- `confidence`
- `importance`
- `valid_time_start`, `valid_time_end`
- `transaction_time`
- `supersedes`, `superseded_by`
- `created_at`, `updated_at`

Notes:
- `source_event_ids` are not stored here directly
- provenance is stored in `memory_sources`

### `memory_sources`

Purpose:
- connect one memory to one or more raw events

Important fields:
- `memory_id`
- `event_id`
- `evidence_type`
- `quote`
- `source_url`

Why this exists:
- one memory may be supported by many events
- one event may support multiple memories

### `memory_edges`

Purpose:
- store explicit relations between memory objects

Important fields:
- `source_memory_id`
- `target_memory_id`
- `relation_type`
- `reason`
- `confidence`

Example:
- `mem_new` `supersedes` `mem_old`

### `policy_actions`

Purpose:
- audit important system decisions

Important fields:
- `action_type`
- `tenant_id`, `project_id`, `chat_id`, `thread_id`, `actor_id`
- `memory_id`
- `input_json`
- `candidate_json`
- `decision`
- `reason`
- `confidence`

Typical future use:
- extraction accepted or rejected
- reconciliation decision
- push/no-push policy outcome

### `retrieval_logs`

Purpose:
- record memory search behavior

Important fields:
- `query`
- `tenant_id`, `project_id`, `chat_id`, `thread_id`
- `requester_id`
- `query_type`
- `time_scope`
- `top_k`
- `status_filter`
- `retrieval_method`
- `retrieved_memory_ids_json`
- `selected_memory_ids_json`
- `score_json`
- `latency_ms`

Current status:
- schema is ready
- full retrieval logging behavior will come in later phases

### `push_logs`

Purpose:
- record proactive memory pushes or reminders

Important fields:
- `trigger_type`
- `tenant_id`, `project_id`, `chat_id`, `user_id`
- `memory_id`
- `push_channel`
- `push_content`
- `should_push`
- `policy_action_id`
- `user_feedback`

Why it matters:
- frequency control
- push auditing
- later usefulness metrics

### `tenants`

Purpose:
- store workspace or organization metadata

Current role:
- lightweight metadata table for future real integrations

### `users`

Purpose:
- store participant metadata

Current role:
- lightweight user identity layer for future chat membership, onboarding, and permissions

### `chats`

Purpose:
- store group or conversation metadata

Current role:
- attach events and pushes to stable chat records

### `projects`

Purpose:
- store project-level scopes

Current role:
- make memory and retrieval flows project-aware

### `project_chats`

Purpose:
- map a project to one or more chats

Why it matters:
- a real project often spans several Feishu groups

### `chat_memberships`

Purpose:
- map users to chats

Why it matters:
- future onboarding
- future access filtering
- future push targeting

### `benchmark_results`

Purpose:
- store benchmark outcomes for anti-noise, conflict, efficiency, and later tests

## 4. Key Relationships

Main relationships:

```text
tenants -> users
tenants -> chats
tenants -> projects

projects <-> chats via project_chats
users <-> chats via chat_memberships

raw_events -> memory_sources -> memory_objects
memory_objects -> memory_edges -> memory_objects
policy_actions -> memory_objects
push_logs -> memory_objects
retrieval_logs -> project/chat/user context
```

Most important provenance path:

```text
memory_objects
    ->
memory_sources
    ->
raw_events
```

This is how MARS proves where a memory came from.

## 5. Current Index Strategy

The schema includes indexes for the most likely early queries.

### Raw event indexes

- `idx_raw_events_source_unique`
- `idx_raw_events_tenant_project_time`
- `idx_raw_events_chat_time`
- `idx_raw_events_actor_time`

These help with:
- deduplicating incoming events
- building discussion windows
- filtering by tenant, project, chat, or actor

### Memory indexes

- `idx_memory_project_status`
- `idx_memory_project_topic`
- `idx_memory_type_status`
- `idx_memory_valid_time`
- `idx_memory_version_group`

These help with:
- active-memory retrieval
- topic-level comparison
- version-chain lookup

### Provenance and relation indexes

- `idx_memory_sources_memory`
- `idx_memory_sources_event`
- `idx_memory_sources_unique`
- `idx_memory_edges_source`
- `idx_memory_edges_target`

These help with:
- tracing sources
- finding relation chains
- avoiding duplicate provenance rows

### Audit and push indexes

- `idx_policy_actions_project_time`
- `idx_retrieval_logs_project_time`
- `idx_push_logs_memory_chat_time`
- `idx_push_logs_project_time`

These help with:
- project-scoped audits
- retrieval inspection
- push frequency control

### Mapping table unique indexes

- `idx_project_chats_unique`
- `idx_chat_memberships_unique`

These prevent duplicate mappings.

## 6. MVP vs Future-Ready Parts

### Required for current MVP

- `raw_events`
- `memory_objects`
- `memory_sources`
- `memory_edges`
- `policy_actions`
- `retrieval_logs`
- `benchmark_results`

### Added now to reduce later refactoring

- `push_logs`
- `tenants`
- `users`
- `chats`
- `projects`
- `project_chats`
- `chat_memberships`
- `version_group_id`
- extra audit metadata fields

These additions are still lightweight. They do not require real Feishu
integration, but they make the schema much easier to evolve.

## 7. Migration Strategy

The project currently uses simple schema initialization plus lightweight
compatibility migrations inside `initialize_database()`.

What it does now:
- create missing tables
- add newly introduced columns to older local databases when needed
- create indexes after table/column checks

Why this exists:
- local development already produced older `mars.db` files
- `CREATE TABLE IF NOT EXISTS` alone does not add new columns

Current migration helper:
- `migrate_legacy_schema()`

This is intentionally simple for the MVP. If the project later becomes a
long-running service, it should move to a more explicit migration system.

## 8. Storage Boundary Rules

The schema is designed around these boundaries:

- connectors know external payload formats
- `RawEvent` is the normalized boundary object
- core logic operates on internal models
- `db.py` is the serialization boundary into SQLite

This separation is what will let MARS evolve from:

```text
local sample JSON + SQLite
```

into:

```text
Feishu events + OpenClaw + server deployment + larger databases
```

without rewriting the whole system.

## 9. What Phase 2 and Phase 3 Use Today

When `scripts/run_extract.py` runs:

1. sample JSON is loaded
2. messages are normalized into `RawEvent`
3. `raw_events` rows are inserted
4. lightweight tenant/project/chat/user metadata is upserted
5. `MockLLM` produces deterministic memory candidates
6. validated `MemoryObject` rows are inserted
7. provenance rows are written to `memory_sources`

This means the current MVP data path is now:

```text
sample JSON
    ->
RawEvent
    ->
raw_events
    ->
MockLLM extraction
    ->
memory_objects + memory_sources
```
