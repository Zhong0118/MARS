# MARS Architecture

## 1. System Positioning

MARS is an independent Agentic Memory Engine.

It is not:

- a Feishu chat search tool
- a simple RAG system
- an OpenClaw internal memory folder
- a pure prompt engineering workflow

It is:

- an external memory infrastructure
- a stateful memory governance system
- an Agent-agnostic service that can be called by OpenClaw, Feishu Bot, CLI, or other agents

``` text
Feishu = data source and interaction surface
OpenClaw = agent entrance and tool caller
MARS = memory management engine
```

## 2. High-level Data Flow

```
Feishu chat / docs / meetings / local sample JSON
        ↓
Connectors / Adapters
        ↓
RawEvent
        ↓
Raw Ledger
        ↓
Window Builder
        ↓
Memory Extraction
        ↓
MemoryObject
        ↓
Views: SQLite / Keyword Index / Vector Index / Markdown / Bitable
        ↓
Retrieval / Reconciliation / Summoning / Benchmark
```

## 3. Core Layers

### 3.1 Interface Layer

Responsible for converting external data into the internal RawEvent schema.

Adapters:

```
sample_loader.py
cli_adapter.py
openclaw_adapter.py
feishu_event_adapter.py
```

MVP only requires:

```
sample_loader.py
cli_adapter.py
```

Later phases add:

```
openclaw_adapter.py
feishu_event_adapter.py
```

### 3.2 Raw Ledger Layer

Raw Ledger is the source of truth.

Principles:

- append-only
- auditable
- replayable
- provenance-preserving
- bitemporal
- no physical deletion in MVP

### 3.3 Memory Extraction Layer

Transforms discussion windows into structured memory objects.

LLM is used for:

- candidate memory extraction
- memory normalization
- conflict relation judgment
- push card generation
- onboarding pack generation

Code is used for:

- event ingestion
- persistence
- state transition
- versioning
- retrieval
- benchmark
- provenance tracking

### 3.4 View Layer

Derived views are generated from Raw Ledger and Memory Objects.

MVP views:

```
SQLite memory_objects
Keyword search
Markdown export, optional
```

Later views:

```
Vector index
Feishu Bitable
Timeline view
Version chain view
```

### 3.5 Retrieval Layer

MVP retrieval:

```
keyword search + project filter + status filter
```

Later retrieval:

```
hybrid retrieval = keyword + vector + status + time + rerank
```

### 3.6 Policy Layer

Controls when to read, write, update, forget, and push.

MVP uses rule-based policies plus LLM semantic judgment.

No RL controller in MVP.

### 3.7 Reconciliation Layer

Handles semantic memory version governance.

Relations:

```
duplicate
support
update
conflict
supersede
unrelated
```

If relation is `supersede`:

```
old_memory.status = superseded
new_memory.status = active
write memory_edges
write policy_actions
```

### 3.8 Summoning Layer

MVP only simulates active push.

Later supports:

```
historical decision reminder
forgetting reminder
conflict review reminder
newcomer onboarding memory pack
```

## 4. Git-like Memory Governance

MARS borrows Git-like version governance ideas, but manages semantic memory objects instead of text files.

| Git Concept | MARS Concept                       |
| ----------- | ---------------------------------- |
| commit      | raw_event / policy_action          |
| diff        | semantic memory diff               |
| merge       | memory merge                       |
| conflict    | conflicted memory                  |
| revert      | correction / supersede event       |
| blame       | provenance trace                   |
| log         | memory timeline                    |
| branch      | project / phase / alternative plan |

Important:

```
MARS diff is not text diff. It is semantic memory diff.
```

## 5. Internal Data Schema

### 5.1 RawEvent

```json
{  "event_id": "evt_001",  "event_type": "message.created",  "source_type": "sample_chat",  "source_id": "msg_001",  "tenant_id": "tenant_demo",  "project_id": "carbon_platform",  "chat_id": "chat_001",  "thread_id": null,  "actor_id": "user_001",  "actor_name": "张三",  "content": "一期先用 Streamlit 吧",  "content_type": "text",  "mentions": [],  "reply_to": null,  "raw_payload": {},  "transaction_time": "2026-05-01T10:00:00",  "valid_time_start": "2026-05-01T10:00:00",  "valid_time_end": null,  "source_url": null}
            
                
            
        
```

### 5.2 MemoryObject

```json
{  "memory_id": "mem_001",  "memory_type": "decision",  "scope": "project",  "tenant_id": "tenant_demo",  "project_id": "carbon_platform",  "user_id": null,  "topic": "技术路线",  "title": "一期 Demo 采用 Streamlit",  "content": "一期 Demo 先采用 Streamlit，正式版再考虑 Vue + FastAPI。",  "rationale": ["比赛周期短", "已有 Python 数据处理代码"],  "objections": ["Streamlit 工程化程度弱于 Vue + FastAPI"],  "status": "active",  "version": 1,  "confidence": 0.86,  "importance": 4,  "valid_time_start": "2026-05-01T10:00:00",  "valid_time_end": null,  "transaction_time": "2026-05-01T10:30:00",  "source_event_ids": ["evt_001", "evt_002"],  "supersedes": null,  "superseded_by": null}
            
                
            
            运行
        
```

### 5.3 MemoryEdge

```
{
  "edge_id": "edge_001",
  "source_memory_id": "mem_002",
  "target_memory_id": "mem_001",
  "relation_type": "supersedes",
  "reason": "新消息明确表示“不对，一期改为 Vue + FastAPI”，覆盖旧技术路线。",
  "confidence": 0.91
}
```

### 5.4 PolicyAction

```
{
  "action_id": "act_001",
  "action_type": "UPDATE",
  "project_id": "carbon_platform",
  "decision": "SUPERSEDE",
  "reason": "同项目同主题且存在明确覆盖语义",
  "confidence": 0.91
}
```

## 6. Database Schema

### 6.1 raw_events

```
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
```

### 6.2 memory_objects

```
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
```

### 6.3 memory_sources

```
CREATE TABLE IF NOT EXISTS memory_sources (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    evidence_type TEXT,
    quote TEXT,
    source_url TEXT,
    created_at TEXT
);
```

### 6.4 memory_edges

```sqlite
CREATE TABLE IF NOT EXISTS memory_edges (
    edge_id TEXT PRIMARY KEY,
    source_memory_id TEXT NOT NULL,
    target_memory_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    reason TEXT,
    confidence REAL,
    created_at TEXT
);
```

### 6.5 policy_actions

```
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
```

### 6.6 retrieval_logs

```
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
```

### 6.7 benchmark_results

```
CREATE TABLE IF NOT EXISTS benchmark_results (
    result_id TEXT PRIMARY KEY,
    benchmark_type TEXT,
    case_id TEXT,
    metric_json TEXT,
    passed INTEGER,
    created_at TEXT
);
```

## 7. Memory Status Machine

Valid statuses:

```
pending
active
superseded
expired
archived
conflicted
rejected
```

Rules:

```
pending -> active
pending -> rejected
active -> superseded
active -> expired
active -> archived
active -> conflicted
conflicted -> active
conflicted -> superseded
conflicted -> rejected
```

MVP must implement:

```
pending
active
superseded
conflicted
rejected
```

## 8. MVP API Routes

### POST /api/ingest/messages

Ingest sample messages or normalized messages.

### POST /api/memory/extract

Extract MemoryObjects from event IDs.

### POST /api/memory/search

Search memory by query.

### POST /api/memory/reconcile

Create or reconcile new memory against existing memories.

### POST /api/benchmark/run

Run benchmark.

## 9. File Structure

```
mars-memory-engine/
├── app/
│   ├── api/
│   ├── connectors/
│   ├── core/
│   ├── llm/
│   └── storage/
├── data/
│   ├── sample_chats/
│   └── benchmark/
├── scripts/
├── memory_store/
├── reports/
├── docs/
├── README.md
├── ARCHITECTURE.md
├── IMPLEMENTATION_PLAN.md
├── AGENTS.md
└── requirements.txt
```

## 10. Non-goals for MVP

MVP does not implement:

- Real Feishu event subscription
- Real OpenClaw runtime integration
- Feishu Bitable sync
- Production permission system
- Vector reranker
- TKG
- RL controller
- latent memory token
- logit modulation
- multimodal memory