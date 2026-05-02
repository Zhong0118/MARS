# IMPLEMENTATION_PLAN.md

# MARS MVP Implementation Plan

This file defines the phased implementation plan for Codex.

Important principle:

```text
Build local MVP first.
Do not implement real Feishu/OpenClaw integration before the local MVP passes.
```

## Global MVP Goal

The MVP must prove the following five capabilities:

1. Extract a decision memory from sample chat JSON.
2. Search memory by query and return sources.
3. Handle conflict update: old memory becomes superseded, new memory becomes active.
4. Retrieve target memory after noise injection.
5. Run benchmark and output metrics.

## Phase 0: Project Scaffold

### Goal

Create a runnable Python project skeleton.

### Requirements

1. Use Python.
2. Use FastAPI.
3. Use SQLite.
4. Use Pydantic.
5. Use local file-based sample data.
6. Do not implement real Feishu/OpenClaw integration.
7. Do not call real LLM.
8. Use MockLLM to make the pipeline runnable.

### Files to create

```
app/main.py
app/api/__init__.py
app/connectors/__init__.py
app/connectors/sample_loader.py
app/core/__init__.py
app/core/extractor.py
app/core/retriever.py
app/core/reconciler.py
app/core/policy.py
app/llm/__init__.py
app/llm/provider.py
app/storage/__init__.py
app/storage/db.py
app/storage/models.py
scripts/init_db.py
scripts/run_extract.py
scripts/search_memory.py
scripts/run_benchmark.py
data/sample_chats/project_day1_decision.json
data/sample_chats/conflict_update.json
data/sample_chats/project_day7_noise.json
data/benchmark/anti_noise_cases.json
data/benchmark/conflict_cases.json
data/benchmark/efficiency_cases.json
memory_store/.gitkeep
reports/.gitkeep
```

### Acceptance Criteria

```
python scripts/init_db.py
```

must create:

```
memory_store/mars.db
```

The project must import successfully:

```
python -c "from app.storage.models import RawEvent, MemoryObject"
```

------

## Phase 1: Data Models and SQLite Storage

### Goal

Implement core Pydantic models and SQLite persistence.

### Models

Implement:

```
RawEvent
MemoryObject
MemoryEdge
MemorySource
PolicyAction
EvidencePack
```

### Database Tables

Implement SQLite initialization for:

```
raw_events
memory_objects
memory_sources
memory_edges
policy_actions
retrieval_logs
benchmark_results
```

### Requirements

1. All JSON-like fields should be stored as JSON strings in SQLite.
2. Every MemoryObject must have at least one source_event_id.
3. No physical deletion of memories.
4. Status update must be done by updating status field.

### Acceptance Criteria

Running:

```
python scripts/init_db.py
```

creates all tables.

------

## Phase 2: Sample Loader and RawEvent Ingestion

### Goal

Load sample chat JSON and convert it into RawEvent.

### Input Sample Format

```
[  {    "message_id": "msg_001",    "project_id": "carbon_platform",    "chat_id": "chat_demo",    "user_id": "u_001",    "user_name": "张三",    "time": "2026-05-01T10:00:00",    "content": "我们一期是不是直接 Vue + FastAPI？"  }]
            
                
            
            运行
        
```

### Output

Each message becomes a RawEvent.

### Requirements

1. Preserve original message in raw_payload.
2. Fill source_type as sample_chat.
3. Fill event_type as message.created.
4. Fill valid_time_start with message time.
5. Store into raw_events table.

### Acceptance Criteria

```
python scripts/run_extract.py --input data/sample_chats/project_day1_decision.json --ingest-only
```

must insert raw events into SQLite.

------

## Phase 3: MockLLM and Memory Extraction

### Goal

Use MockLLM to extract MemoryObjects from discussion windows.

### Requirements

1. Implement MockLLM in app/llm/provider.py.
2. MockLLM should return deterministic structured JSON for sample data.
3. Implement app/core/extractor.py.
4. Extractor reads RawEvents and generates MemoryObjects.
5. All LLM outputs must pass Pydantic validation.
6. If parsing fails, return error or mark memory as pending.

### Memory Types

MVP supports:

```
decision
fact
procedure
risk
preference
```

### Acceptance Criteria

```
python scripts/run_extract.py --input data/sample_chats/project_day1_decision.json
```

must create at least one active decision memory:

```
一期 Demo 采用 Streamlit
```

and store it in memory_objects.

------

## Phase 4: Keyword Retrieval

### Goal

Implement local keyword-based memory search.

### Requirements

1. Implement app/core/retriever.py.
2. Search memory_objects by query keywords.
3. Default status filter: active only.
4. Support project_id filter.
5. Return EvidencePack.
6. EvidencePack must include memory_id, title, content, status, score, source_event_ids.

### Script

Implement:

```
scripts/search_memory.py
```

### Acceptance Criteria

After extraction, running:

```
python scripts/search_memory.py "之前为什么不用 Vue？" --project-id carbon_platform
```

returns:

```
一期 Demo 采用 Streamlit
source_event_ids
```

------

## Phase 5: Reconciliation and Supersede

### Goal

Implement semantic conflict handling with MockLLM relation judgment.

### Requirements

1. Implement app/core/reconciler.py.
2. Input new memory or new statement.
3. Retrieve old memories from same project and same topic.
4. Use MockLLM to judge relation.
5. Relations:

```
duplicate
support
update
conflict
supersede
unrelated
```

1. If relation=supersede:
   - old memory status becomes superseded
   - new memory status becomes active
   - new memory version = old version + 1
   - insert memory_edges relation supersedes
   - insert policy_actions action UPDATE/SUPERSEDE

### Acceptance Criteria

Given:

```
old: 一期 Demo 采用 Streamlit
new: 不对，一期改成 Vue + FastAPI
```

the system must produce:

```
old.status = superseded
new.status = active
memory_edges contains supersedes
policy_actions contains SUPERSEDE
```

------

## Phase 6: FastAPI Routes

### Goal

Expose MVP functions as HTTP APIs.

### Routes

Implement:

```
POST /api/ingest/messages
POST /api/memory/extract
POST /api/memory/search
POST /api/memory/reconcile
POST /api/benchmark/run
GET  /health
```

### Requirements

1. Use Pydantic request and response models.
2. Do not expose internal SQLite connection details.
3. Return clear error messages.
4. All routes should be testable locally.

### Acceptance Criteria

```
uvicorn app.main:app --reload --port 8000
```

Then:

```
curl http://127.0.0.1:8000/health
```

returns:

```
{"status":"ok"}
```

------

## Phase 7: Benchmark

### Goal

Implement benchmark scripts.

### Benchmark Types

1. anti_noise
2. conflict
3. efficiency

### Files

```
data/benchmark/anti_noise_cases.json
data/benchmark/conflict_cases.json
data/benchmark/efficiency_cases.json
```

### Output

```
reports/benchmark_report.md
reports/benchmark_results.csv
```

### Metrics

Anti-noise:

```
Recall@1
Recall@3
Source Accuracy
```

Conflict:

```
Conflict Detection Accuracy
Supersede Accuracy
Status Accuracy
```

Efficiency:

```
Time Reduction
Step Reduction
Input Character Reduction
```

### Acceptance Criteria

```
python scripts/run_benchmark.py
```

must output benchmark results and write files under reports/.

------

## Phase 8: Vector Store Placeholder

### Goal

Prepare vector retrieval interface but do not require full vector search yet.

### Requirements

Create:

```
app/storage/vector_store.py
```

with interface:

```
class VectorStore:
    def add_memory(self, memory): ...
    def search(self, query: str, top_k: int = 5): ...
```

MVP can use a no-op or simple placeholder.

### Acceptance Criteria

Code imports successfully and does not break retrieval.

------

## Phase 9: OpenClaw and Feishu Adapter Placeholders

### Goal

Create adapter placeholders without real integration.

### Files

```
app/connectors/openclaw_adapter.py
app/connectors/feishu_event_adapter.py
```

### Requirements

1. Define functions that convert external payloads into RawEvent.
2. Preserve raw_payload.
3. Add TODO comments for real fields.

### Acceptance Criteria

Adapters can be imported and unit-tested with fake payloads.

------

## Phase 10: Optional Onboarding Pack

### Goal

Implement local newcomer onboarding generation using existing memories.

### Requirements

1. Add API:

```
POST /api/memory/onboarding
```

1. Input:

```
{
  "project_id": "carbon_platform",
  "query": "给新人生成项目上下文包"
}
```

1. Output sections:

```
项目背景
关键决策
历史争议
当前有效结论
风险提醒
推荐阅读
来源链接
```

### Acceptance Criteria

Returns a structured onboarding pack from existing MemoryObjects.

------

# Final MVP Done Criteria

The MVP is done only if all commands pass:

```
python scripts/init_db.py

python scripts/run_extract.py \
  --input data/sample_chats/project_day1_decision.json

python scripts/search_memory.py \
  "之前为什么不用 Vue？" \
  --project-id carbon_platform

python scripts/run_extract.py \
  --input data/sample_chats/conflict_update.json

python scripts/search_memory.py \
  "现在一期技术路线是什么？" \
  --project-id carbon_platform

python scripts/run_benchmark.py

uvicorn app.main:app --reload --port 8000
```

Expected behavior:

1. Extracts Streamlit decision.
2. Search returns Streamlit memory with sources.
3. Conflict update supersedes Streamlit and activates Vue + FastAPI.
4. Search returns current active Vue + FastAPI decision.
5. Benchmark writes report.
6. FastAPI starts successfully.