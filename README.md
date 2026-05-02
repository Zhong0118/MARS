# MARS: Memory Agent for Reconciliation and Summoning

MARS is an Agentic Memory Engine for enterprise collaboration memory.

It is designed to turn fragmented project history from Feishu chats, notes,
meeting discussions, and agent inputs into structured, governable memory:
decisions, facts, procedures, risks, preferences, and onboarding context.

MARS is not:
- a simple chat search tool
- a plain RAG pipeline
- an internal OpenClaw memory folder

MARS is:
- an independent memory management engine
- a provenance-aware raw ledger plus memory object system
- a service that can later be called by OpenClaw, Feishu bots, CLI tools, or
  other agents

## Project Status

The repository is currently in local MVP mode.

Completed so far:
- Phase 0: project scaffold
- Phase 1: core Pydantic models and SQLite storage

Working now:
- SQLite database initialization
- local sample chat ingestion into `raw_events`
- FastAPI app skeleton with `/health`

Not implemented yet:
- real memory extraction
- keyword retrieval
- reconciliation and supersede flows
- benchmark execution
- real Feishu or OpenClaw integration

## Core Idea

MARS is built around this structure:

```text
Raw Ledger + Derived Views + Policy + Reconciliation + Summoning
```

Meaning:
- `Raw Ledger`: append-only source events with provenance
- `Derived Views`: structured memory objects and later retrieval/export views
- `Policy`: rules for when to read, write, update, and push memory
- `Reconciliation`: logic for duplicate, conflict, update, and supersede
- `Summoning`: active recall of relevant historical decisions

The MVP follows one strict principle:

```text
Build the local version first.
Do not implement real Feishu/OpenClaw integration before the local MVP works.
```

## MVP Scope

The local MVP is designed to prove these capabilities step by step:

1. Load sample chat JSON.
2. Convert every external message into a `RawEvent`.
3. Store raw events in SQLite.
4. Extract structured `MemoryObject` records with `MockLLM`.
5. Search memory locally.
6. Handle conflict updates with supersede relations.
7. Run benchmark scripts and write reports.
8. Expose local HTTP APIs through FastAPI.

At the current stage, only the groundwork for these flows is implemented.

## Current Architecture

High-level flow:

```text
sample JSON / CLI / future adapters
        ->
connectors
        ->
RawEvent
        ->
SQLite raw ledger
        ->
future extraction / retrieval / reconciliation
```

Key architecture rules:
- all external data must first become `RawEvent`
- external payload formats must stay inside connectors/adapters
- no physical deletion of memories
- every `MemoryObject` must keep provenance through `source_event_ids`
- code handles governance and state changes; LLM handles semantics

## Repository Structure

```text
app/
  api/          HTTP route modules
  connectors/   external input adapters -> RawEvent
  core/         extraction, retrieval, reconciliation, policy
  llm/          MockLLM and future provider integrations
  storage/      Pydantic models and SQLite helpers
data/
  sample_chats/ sample discussion inputs
  benchmark/    benchmark case definitions
scripts/        local CLI entrypoints
memory_store/   generated SQLite database
reports/        generated benchmark/report outputs
docs/           architecture, proposal, plan, project structure
```

For a fuller explanation of each folder and file, see:

- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)

## Implemented Files

Important files already in place:
- `app/main.py`: FastAPI app entrypoint with `/health`
- `app/connectors/sample_loader.py`: sample JSON -> `RawEvent`
- `app/storage/models.py`: core internal Pydantic models
- `app/storage/db.py`: SQLite schema and persistence helpers
- `scripts/init_db.py`: create local database and tables
- `scripts/run_extract.py`: ingest sample chats into `raw_events`
- `scripts/search_memory.py`: placeholder CLI for future retrieval
- `scripts/run_benchmark.py`: placeholder CLI for future benchmark flow

## Requirements

Recommended environment:
- Python 3.11+ or 3.12
- a dedicated conda environment, or an existing one such as `dl`

Install dependencies:

```powershell
pip install -r requirements.txt
```

If you use conda:

```powershell
conda run -n dl python -m pip install -r requirements.txt
```

Current dependencies:
- `fastapi`
- `pydantic`
- `uvicorn`

## Quick Start

### 1. Initialize the database

```powershell
python scripts/init_db.py
```

Expected result:
- creates `memory_store/mars.db`
- creates all required MVP tables

### 2. Ingest sample chat JSON into `raw_events`

```powershell
python scripts/run_extract.py --input data/sample_chats/project_day1_decision.json --ingest-only
```

Expected result:
- reads the sample file
- converts each message into a `RawEvent`
- inserts those rows into SQLite

### 3. Verify imports

```powershell
python -c "from app.storage.models import RawEvent, MemoryObject"
```

### 4. Run the FastAPI app

```powershell
uvicorn app.main:app --reload --port 8000
```

Then open:

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Current Commands

These commands are already defined in the project workflow:

```powershell
python scripts/init_db.py

python scripts/run_extract.py --input data/sample_chats/project_day1_decision.json --ingest-only

python scripts/search_memory.py "why did we avoid Vue earlier?" --project-id carbon_platform

python scripts/run_benchmark.py

uvicorn app.main:app --reload --port 8000
```

Notes:
- `search_memory.py` is still a placeholder in Phase 0/1
- `run_benchmark.py` is still a placeholder in Phase 0/1
- full extraction logic arrives in later phases

## Data Model Snapshot

Core internal models:
- `RawEvent`
- `MemoryObject`
- `MemoryEdge`
- `MemorySource`
- `PolicyAction`
- `EvidencePack`

Current SQLite tables:
- `raw_events`
- `memory_objects`
- `memory_sources`
- `memory_edges`
- `policy_actions`
- `retrieval_logs`
- `benchmark_results`

## Sample Data

Included sample chat files:
- `data/sample_chats/project_day1_decision.json`
- `data/sample_chats/conflict_update.json`
- `data/sample_chats/project_day7_noise.json`

Included benchmark case files:
- `data/benchmark/anti_noise_cases.json`
- `data/benchmark/conflict_cases.json`
- `data/benchmark/efficiency_cases.json`

These files are local MVP fixtures used to drive extraction, retrieval,
conflict, and benchmark development without relying on real Feishu data.

## Roadmap

Near-term implementation order:

1. Phase 2: sample loader and raw event ingestion refinement
2. Phase 3: `MockLLM` and memory extraction
3. Phase 4: keyword retrieval
4. Phase 5: reconciliation and supersede handling
5. Phase 6: FastAPI routes
6. Phase 7: benchmark output

## Non-goals for the MVP

The local MVP does not implement:
- real Feishu event subscription
- real OpenClaw runtime integration
- Feishu Bitable sync
- full vector retrieval
- temporal knowledge graph
- RL controller
- latent memory token
- logit modulation
- multimodal memory

## Related Documents

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)
- [docs/PROJECT_PROPOSAL.md](docs/PROJECT_PROPOSAL.md)
- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)
- [AGENTS.md](AGENTS.md)

## Design Summary

If you want the shortest mental model of MARS, use this:

```text
LLM does semantics.
Code does governance.
Database does state.
Policy does orchestration.
```
