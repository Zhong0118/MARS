## Current Status

This file is the shortest handoff document for continuing MARS work in a new chat window.

### What is already working

- `Phase 0-1`: project scaffold, core models, SQLite schema, CLI/FastAPI entrypoints.
- `Phase 2`: sample JSON ingestion into `raw_events`.
- `Phase 3`: memory extraction through provider boundary.
- `Phase 4`: keyword retrieval from `memory_objects` with `source_event_ids`.
- `Phase 5`: reconciliation and supersede flow with `memory_edges` and `policy_actions`.
- `Phase 6`: local FastAPI routes for ingest, extract, search, reconcile.

### Provider modes

- `mock`
  - deterministic local baseline
  - best for schema and pipeline testing
- `glm`
  - real API mode through the OpenAI-compatible GLM endpoint
  - configured by environment variables, not hard-coded secrets

Relevant files:

- [provider.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/app/llm/provider.py)
- [.env.example](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/.env.example)

### Extraction flow right now

The extraction path is now:

```text
sample JSON / future adapter input
-> RawEvent
-> raw_events
-> WindowBuilder
-> TopicTracker
-> MemoryExtractor
-> MemoryReconciler
-> memory_objects / memory_sources / memory_edges / policy_actions
```

Relevant files:

- [ingestion.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/app/core/ingestion.py)
- [window_builder.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/app/core/window_builder.py)
- [topic_tracker.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/app/core/topic_tracker.py)
- [extractor.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/app/core/extractor.py)
- [reconciler.py](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/app/core/reconciler.py)

### What still needs work

- `Phase 7`
  - real benchmark data and benchmark runner
  - anti-noise / conflict / efficiency evaluation
- `Phase 8`
  - vector retrieval placeholder
- `Phase 9`
  - OpenClaw / Feishu adapter placeholders
- `Phase 10`
  - onboarding pack generation

### Recommended next engineering steps

1. Add benchmark datasets beyond the tiny sample chats.
2. Add provider fallback and error handling for real GLM calls.
3. Evolve `window_builder` from stateless batch segmentation to incremental chat processing.
4. Introduce configurable marker files such as `config/window_builder.json`.

### How to continue in a new chat window

When the current chat context gets full, start a new chat and point it to these files first:

- [README.md](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/README.md)
- [IMPLEMENTATION_PLAN_CN.md](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/docs/IMPLEMENTATION_PLAN_CN.md)
- [DB_SCHEMA.md](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/docs/DB_SCHEMA.md)
- [WINDOW_TOPIC_BENCHMARK_DESIGN.md](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/docs/WINDOW_TOPIC_BENCHMARK_DESIGN.md)
- [CURRENT_STATUS.md](/abs/path/c:/Users/zx/Desktop/0-Inbox/1-Projects/memory_engine/docs/CURRENT_STATUS.md)

Also mention the current active modules:

- `app/core/ingestion.py`
- `app/core/window_builder.py`
- `app/core/topic_tracker.py`
- `app/llm/provider.py`
- `app/core/extractor.py`
- `app/core/reconciler.py`

Do not paste API keys into the new chat. Keep them only in local environment variables or a local `.env` file ignored by git.
