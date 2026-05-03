"""FastAPI entrypoint for the local MARS MVP."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.connectors.sample_loader import message_to_raw_event
from app.core.answerer import MemoryAnswerer
from app.core.ingestion import extract_and_reconcile, ingest_events
from app.core.query_planner import QueryPlanner
from app.core.retriever import MemoryRetriever
from app.storage.db import get_connection, initialize_database
from app.storage.models import EvidencePack, MemoryObject


# Ensure scripts/ is importable for the benchmark runner
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))


class IngestMessagesRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(default_factory=list)


class ExtractRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    project_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResponse(BaseModel):
    answer: str
    results: list[EvidencePack]


class ExtractResponse(BaseModel):
    raw_event_count: int
    extracted_count: int
    memories: list[MemoryObject]



app = FastAPI(title="MARS", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Return a simple liveness signal for local development."""
    return {"status": "ok"}


@app.post("/api/ingest/messages")
def ingest_messages(request: IngestMessagesRequest) -> dict[str, int]:
    """Normalize messages into RawEvent rows and persist them."""
    initialize_database()
    events = [message_to_raw_event(message) for message in request.messages]
    with get_connection() as connection:
        ingest_events(connection, events)
    return {"raw_event_count": len(events)}


@app.post("/api/memory/extract", response_model=ExtractResponse)
def extract_memories(request: ExtractRequest) -> ExtractResponse:
    """Ingest messages, run extraction and reconciliation, return stored memories.

    Reconciliation is always applied as part of extraction — there is no
    separate reconcile endpoint.
    """
    initialize_database()
    events = [message_to_raw_event(message) for message in request.messages]
    with get_connection() as connection:
        ingest_events(connection, events)
        memories = extract_and_reconcile(connection, events)
    return ExtractResponse(raw_event_count=len(events), extracted_count=len(memories), memories=memories)


@app.post("/api/memory/search", response_model=SearchResponse)
def search_memories(request: SearchRequest) -> SearchResponse:
    """Run local keyword search over stored active memories."""
    initialize_database()
    retriever = MemoryRetriever(top_k=request.top_k)
    planner = QueryPlanner()
    answerer = MemoryAnswerer()
    results = retriever.search(request.query, project_id=request.project_id)
    bundle = answerer.compose(planner.plan(request.query, top_k=request.top_k), results)
    return SearchResponse(answer=bundle.answer, results=results)


@app.post("/api/benchmark/run")
def run_benchmark() -> dict:
    """Run all benchmark groups and return a summary.

    Executes anti-noise, conflict, efficiency, and mixed-topic benchmark
    cases, writes CSV and Markdown reports, and returns pass/fail counts.
    """
    try:
        import run_benchmark as benchmark_module  # type: ignore[import]
        summary = benchmark_module.run_all_benchmarks()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Benchmark run failed: {exc}") from exc
    return summary
