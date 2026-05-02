# MARS Project Structure

This document explains what each folder is responsible for, which files are in
it today, and how those files fit into the MVP plan.

The goal is to make the repository easy to navigate while the project grows
from a local MVP into a fuller memory engine.

## 1. Top-level folders

### `app/`

Application source code for the MARS engine.

Current role:
- keep external adapters separate from core logic
- hold internal models and storage code
- expose a minimal FastAPI app for local verification

Subfolders:
- `api/`: reserved for HTTP route modules
- `connectors/`: adapters that translate external input into `RawEvent`
- `core/`: extraction, retrieval, reconciliation, and policy logic
- `llm/`: mock or real LLM providers behind a stable interface
- `storage/`: Pydantic models and SQLite persistence helpers

### `data/`

Static local input data used by the MVP.

Current role:
- provide sample chat payloads for ingestion
- provide simple benchmark case files for later phases

Subfolders:
- `sample_chats/`: chat transcripts used to drive extraction and conflict demos
- `benchmark/`: case definitions for anti-noise, conflict, and efficiency tests

### `scripts/`

Command-line entrypoints for local development and MVP verification.

Current role:
- create the database
- ingest sample chat files
- define stable script interfaces for later search and benchmark logic

### `memory_store/`

Local generated storage.

Current role:
- holds the SQLite database file `mars.db`

Notes:
- this is runtime state, not source code
- `.gitkeep` exists so the folder is present in the repository

### `reports/`

Generated outputs from evaluation and reporting.

Current role:
- reserved for future benchmark reports and exports

### `docs/`

Project documents and planning materials.

Current role:
- explain system goals, architecture, proposal, and implementation phases
- now also includes this repository structure guide

## 2. Current source files

### `app/main.py`

Purpose:
- FastAPI application entrypoint
- exposes `GET /health` for local liveness checks

Why it exists now:
- Phase 0 needs a runnable app skeleton before real API routes are added

### `app/api/__init__.py`

Purpose:
- marks `app/api` as a Python package

Why it exists now:
- keeps the package layout aligned with the architecture and plan even before
  concrete route modules are added

### `app/connectors/__init__.py`

Purpose:
- marks `app/connectors` as a Python package

### `app/connectors/sample_loader.py`

Purpose:
- read local sample JSON files
- convert sample messages into internal `RawEvent` objects

Key functions:
- `load_sample_messages`: loads raw JSON messages
- `message_to_raw_event`: maps one external message into the internal schema
- `load_raw_events`: loads and normalizes a whole file

Architectural importance:
- this is the MVP adapter boundary
- sample JSON format stays here and does not leak into core modules

### `app/core/__init__.py`

Purpose:
- marks `app/core` as a Python package

### `app/core/extractor.py`

Purpose:
- placeholder for turning `RawEvent` windows into `MemoryObject` records

Current status:
- scaffold only

Later phase:
- will own memory extraction workflow with `MockLLM`

### `app/core/retriever.py`

Purpose:
- placeholder for keyword memory retrieval

Current status:
- scaffold only

Later phase:
- will implement project-aware search returning `EvidencePack`

### `app/core/reconciler.py`

Purpose:
- placeholder for memory relation judgment and supersede handling

Current status:
- scaffold only

Later phase:
- will compare new memories with existing ones and update statuses, edges, and
  policy actions

### `app/core/policy.py`

Purpose:
- placeholder for policy-layer orchestration

Current status:
- returns a no-op `PolicyAction`

Later phase:
- will coordinate write/update behavior and audit policy decisions

### `app/llm/__init__.py`

Purpose:
- marks `app/llm` as a Python package

### `app/llm/provider.py`

Purpose:
- defines the local `MockLLM` provider interface

Current status:
- deterministic placeholder methods only

Later phase:
- will return structured extraction and relation-judgment outputs for sample
  scenarios

### `app/storage/__init__.py`

Purpose:
- marks `app/storage` as a Python package

### `app/storage/models.py`

Purpose:
- defines internal Pydantic models shared across the system

Current models:
- `RawEvent`
- `MemoryObject`
- `MemoryEdge`
- `MemorySource`
- `PolicyAction`
- `EvidencePack`

Architectural importance:
- this file is the internal contract for connectors, core logic, and storage
- provenance requirements are enforced here, for example `MemoryObject` must
  include at least one `source_event_id`

### `app/storage/db.py`

Purpose:
- owns SQLite file paths
- initializes database schema
- serializes Pydantic objects into SQLite-friendly rows
- provides insert helpers for early-phase scripts

Key functions:
- `ensure_storage_dirs`
- `get_connection`
- `initialize_database`
- `schema_statements`
- `insert_raw_events`
- `insert_memory_object`
- `insert_memory_sources`
- `insert_memory_edge`
- `insert_policy_action`

Architectural importance:
- this is the boundary where Python models are converted into database rows
- JSON-like fields are explicitly serialized into SQLite text fields here

## 3. Current CLI scripts

### `scripts/init_db.py`

Purpose:
- create `memory_store/mars.db`
- create all required SQLite tables

Phase:
- Phase 0 and Phase 1

### `scripts/run_extract.py`

Purpose:
- ingest a sample chat file into `raw_events`

Current behavior:
- initializes the database
- loads local sample JSON
- converts messages into `RawEvent`
- inserts them into SQLite

Later phase:
- will also trigger memory extraction

### `scripts/search_memory.py`

Purpose:
- stable CLI shape for future local memory retrieval

Current behavior:
- placeholder only

### `scripts/run_benchmark.py`

Purpose:
- stable CLI shape for future benchmark runs

Current behavior:
- placeholder only
- ensures the `reports/` directory exists

## 4. Current data files

### `data/sample_chats/project_day1_decision.json`

Purpose:
- base discussion sample for the first technical-route decision

Use later:
- extraction demo
- retrieval demo

### `data/sample_chats/conflict_update.json`

Purpose:
- follow-up sample used to simulate a superseding decision

Use later:
- reconciliation demo

### `data/sample_chats/project_day7_noise.json`

Purpose:
- unrelated messages used to test anti-noise retrieval behavior

### `data/benchmark/anti_noise_cases.json`

Purpose:
- benchmark case definitions for noisy retrieval

### `data/benchmark/conflict_cases.json`

Purpose:
- benchmark case definitions for conflict and supersede behavior

### `data/benchmark/efficiency_cases.json`

Purpose:
- benchmark case definitions for time/step savings comparisons

## 5. Supporting files

### `requirements.txt`

Purpose:
- local Python dependencies for the MVP skeleton

Current packages:
- `fastapi`
- `pydantic`
- `uvicorn`

### `AGENTS.md`

Purpose:
- repository-level implementation constraints for the coding agent

Highlights:
- local MVP first
- no real Feishu/OpenClaw integration yet
- provenance is mandatory
- no physical deletion of memories

### `README.md`

Purpose:
- high-level project introduction and run instructions

### `docs/ARCHITECTURE.md`

Purpose:
- system architecture and schema definitions

### `docs/IMPLEMENTATION_PLAN.md`

Purpose:
- phased implementation checklist for the MVP

### `docs/PROJECT_PROPOSAL.md`

Purpose:
- broader project narrative and positioning

## 6. What is implemented vs placeholder

Implemented in Phase 0/1:
- package structure
- internal Pydantic models
- SQLite schema initialization
- sample JSON ingestion into `raw_events`
- FastAPI app skeleton with `/health`

Placeholder for later phases:
- memory extraction
- keyword retrieval
- reconciliation logic
- benchmark execution
- richer API routes

## 7. Where new work should go

When continuing the MVP, the next changes should mostly land here:

- Phase 2: `app/connectors/sample_loader.py`, `scripts/run_extract.py`,
  `app/storage/db.py`
- Phase 3: `app/llm/provider.py`, `app/core/extractor.py`
- Phase 4: `app/core/retriever.py`, `scripts/search_memory.py`
- Phase 5: `app/core/reconciler.py`, `app/core/policy.py`, `app/storage/db.py`
- Phase 6: `app/api/` and `app/main.py`
- Phase 7: `scripts/run_benchmark.py`, `reports/`, `data/benchmark/`

## 8. Quick mental model

If you only remember one thing about the repository structure, use this:

- `connectors` translate outside data into internal events
- `storage` defines and persists those internal objects
- `core` decides how memories are extracted, searched, and updated
- `llm` provides semantics
- `scripts` and `api` are the ways humans or other systems call MARS
