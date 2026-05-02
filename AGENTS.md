# AGENTS.md

# MARS Agent Instructions

You are working on MARS: Memory Agent for Reconciliation and Summoning.

MARS is an Agentic Memory Engine for enterprise collaboration memory. It is designed to manage Feishu/OpenClaw project memories such as decisions, facts, procedures, risks, preferences, and onboarding context.

## 1. Project Positioning

MARS is independent from OpenClaw.

Do not store core memory data inside OpenClaw folders.

OpenClaw is only a caller / client.

MARS owns:

```text
Raw Ledger
Memory Objects
Derived Views
Policy
Reconciliation
Summoning
Benchmark
```

## 2. MVP First

Always implement the local MVP first.

Do not implement real Feishu API, real OpenClaw runtime, Feishu Bitable sync, vector search, TKG, RL controller, or multimodal memory until the MVP is working.

MVP must work with:

```
local sample JSON
SQLite
MockLLM
CLI scripts
FastAPI local server
```

## 3. Core Architecture Rules

### 3.1 Raw Event First

All external data must be converted into RawEvent.

Sources include:

```
sample JSON
CLI input
OpenClaw payload
Feishu event
```

Every adapter must preserve the original payload in `raw_payload`.

### 3.2 No Direct External Format Dependency

Do not let Feishu or OpenClaw payload format leak into core modules.

Only connector / adapter modules may know external formats.

Core modules should consume only internal models.

### 3.3 No Physical Deletion

Do not physically delete memories in MVP.

Use status transitions:

```
pending
active
superseded
expired
archived
conflicted
rejected
```

### 3.4 Provenance Required

Every MemoryObject must have source_event_ids.

Every answer should be able to trace back to raw_events.

### 3.5 Supersede Must Be Logged

When a memory supersedes another memory:

1. Update old memory status to superseded.
2. Insert new memory as active.
3. Create memory_edges relation.
4. Create policy_actions record.
5. Preserve source_event_ids.

### 3.6 LLM Boundary

LLM is used for:

```
semantic memory extraction
memory normalization
conflict relation judgment
push card generation
onboarding pack generation
```

Code is responsible for:

```
database writes
state transitions
versioning
retrieval filtering
frequency control
benchmark metrics
provenance tracking
```

Summary:

```
LLM does semantics.
Code does governance.
Database does state.
Policy does orchestration.
```

## 4. Coding Rules

Use:

```
Python
FastAPI
SQLite
Pydantic
```

Prefer simple, readable code.

Do not add unnecessary frameworks.

Do not introduce async complexity unless required.

Keep modules small and testable.

## 5. Required Project Layout

Use this layout:

```
app/
  api/
  connectors/
  core/
  llm/
  storage/
data/
  sample_chats/
  benchmark/
scripts/
memory_store/
reports/
docs/
```

## 6. Required Models

Implement and use Pydantic models for:

```
RawEvent
MemoryObject
MemoryEdge
MemorySource
PolicyAction
EvidencePack
```

## 7. Required Tables

SQLite tables:

```
raw_events
memory_objects
memory_sources
memory_edges
policy_actions
retrieval_logs
benchmark_results
```

## 8. Required Commands

These commands must keep working:

```
python scripts/init_db.py

python scripts/run_extract.py \
  --input data/sample_chats/project_day1_decision.json

python scripts/search_memory.py \
  "之前为什么不用 Vue？" \
  --project-id carbon_platform

python scripts/run_benchmark.py

uvicorn app.main:app --reload --port 8000
```

## 9. MVP Acceptance Criteria

The MVP is valid only if:

1. It ingests sample chat JSON into raw_events.
2. It extracts at least one decision memory.
3. Search returns memory with source_event_ids.
4. Conflict update marks old memory as superseded and new memory as active.
5. memory_edges records supersedes relation.
6. policy_actions records the update decision.
7. benchmark outputs report files.
8. FastAPI starts and /health returns ok.

## 10. Non-goals

Do not implement these in MVP:

```
real Feishu event subscription
real OpenClaw integration
Feishu Bitable sync
production permission system
full vector database
TKG
RL controller
latent memory token
logit modulation
multimodal memory
```

Create placeholders only if needed.

## 11. Style

Use clear names.

Do not hide important logic inside prompts.

All state-changing operations must be explicit in code.

All LLM outputs must be validated with Pydantic.

If JSON parsing fails, return a clear error or mark memory as pending.

## 12. When Unsure

If a design choice is unclear:

1. Prefer simpler MVP implementation.
2. Preserve provenance.
3. Avoid deleting data.
4. Keep adapters separate from core.
5. Add TODO comments for future Feishu/OpenClaw integration.
