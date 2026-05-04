from __future__ import annotations

"""Run lightweight local benchmarks for the MARS MVP."""

import csv
import gc
import json
import sqlite3
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.ingestion import extract_and_reconcile, ingest_events
from app.core.query_planner import QueryPlanner
from app.core.retriever import MemoryRetriever
from app.connectors.sample_loader import load_raw_events
from app.storage.db import ensure_storage_dirs, get_connection, initialize_database, insert_benchmark_result
from app.storage.models import BenchmarkResult


BENCHMARK_DB = PROJECT_ROOT / "memory_store" / "mars_benchmark.db"
REPORT_MD = PROJECT_ROOT / "reports" / "benchmark_report.md"
REPORT_CSV = PROJECT_ROOT / "reports" / "benchmark_results.csv"


def reset_benchmark_db() -> None:
    """Delete and re-create the benchmark database, handling Windows file locks."""
    gc.collect()
    for _ in range(5):
        try:
            if BENCHMARK_DB.exists():
                BENCHMARK_DB.unlink()
            break
        except PermissionError:
            gc.collect()
            time.sleep(0.2)
    initialize_database(BENCHMARK_DB)


def load_json(path: Path) -> list[dict]:
    """Load one JSON array file."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def run_anti_noise_case(case: dict) -> BenchmarkResult:
    """Benchmark whether the system still retrieves the target memory under noise."""
    reset_benchmark_db()
    with get_connection(BENCHMARK_DB) as connection:
        ingest_events(connection, load_raw_events(PROJECT_ROOT / "data/sample_chats/project_day1_decision.json"))
        extract_and_reconcile(connection, load_raw_events(PROJECT_ROOT / "data/sample_chats/project_day1_decision.json"))
        ingest_events(connection, load_raw_events(PROJECT_ROOT / case["noise_file"]))

    planner = QueryPlanner()
    plan = planner.plan(case["query"], top_k=3)
    results = MemoryRetriever(top_k=3, db_path=BENCHMARK_DB).search(case["query"], project_id=case["project_id"], plan=plan)
    top_result = results[0] if results else None
    top_title = top_result.title if top_result else None
    top_content = (top_result.content or "").lower() if top_result else ""
    passed = bool(
        top_result
        and top_result.topic == case["expected_topic"]
        and all(keyword.lower() in top_content for keyword in case["required_keywords"])
    )
    return BenchmarkResult(
        benchmark_type="anti_noise",
        case_id=case["case_id"],
        metric={
            "query": case["query"],
            "top_title": top_title,
            "top_topic": top_result.topic if top_result else None,
            "result_count": len(results),
            "expected_topic": case["expected_topic"],
            "required_keywords": case["required_keywords"],
        },
        passed=passed,
    )


def run_conflict_case(case: dict) -> BenchmarkResult:
    """Benchmark whether supersede handling leaves the expected active memory."""
    reset_benchmark_db()
    with get_connection(BENCHMARK_DB) as connection:
        ingest_events(connection, load_raw_events(PROJECT_ROOT / "data/sample_chats/project_day1_decision.json"))
        extract_and_reconcile(connection, load_raw_events(PROJECT_ROOT / "data/sample_chats/project_day1_decision.json"))
        ingest_events(connection, load_raw_events(PROJECT_ROOT / "data/sample_chats/conflict_update.json"))
        conflict_result = extract_and_reconcile(connection, load_raw_events(PROJECT_ROOT / "data/sample_chats/conflict_update.json"))
        active_memory = conflict_result.memories[0] if conflict_result.memories else None

    active_title = active_memory.title if active_memory else None
    active_content = (active_memory.content or "").lower() if active_memory else ""
    passed = bool(
        active_memory
        and active_memory.topic == case["expected_topic"]
        and all(keyword.lower() in active_content for keyword in case["required_keywords"])
    )
    return BenchmarkResult(
        benchmark_type="conflict",
        case_id=case["case_id"],
        metric={
            "old_statement": case["old_statement"],
            "new_statement": case["new_statement"],
            "active_title": active_title,
            "active_topic": active_memory.topic if active_memory else None,
            "expected_topic": case["expected_topic"],
            "required_keywords": case["required_keywords"],
        },
        passed=passed,
    )


def run_efficiency_case(case: dict) -> BenchmarkResult:
    """Benchmark the expected relative workflow savings claimed by the MVP."""
    time_reduction = case["manual_time_sec"] - case["mars_time_sec"]
    step_reduction = case["manual_steps"] - case["mars_steps"]
    passed = time_reduction > 0 and step_reduction > 0
    return BenchmarkResult(
        benchmark_type="efficiency",
        case_id=case["case_id"],
        metric={
            "task": case["task"],
            "manual_time_sec": case["manual_time_sec"],
            "mars_time_sec": case["mars_time_sec"],
            "time_reduction_sec": time_reduction,
            "manual_steps": case["manual_steps"],
            "mars_steps": case["mars_steps"],
            "step_reduction": step_reduction,
        },
        passed=passed,
    )


def run_mixed_topic_case(case: dict) -> BenchmarkResult:
    """Benchmark whether mixed-topic chats still retain a usable tech-route memory."""
    reset_benchmark_db()
    with get_connection(BENCHMARK_DB) as connection:
        events = load_raw_events(PROJECT_ROOT / case["input_file"])
        ingest_events(connection, events)
        mixed_result = extract_and_reconcile(connection, events)

    active_topics = [memory.topic for memory in mixed_result.memories if memory.status == "active"]
    tech_route_count = sum(1 for topic in active_topics if topic == case["expected_active_topic"])
    passed = tech_route_count >= 1
    return BenchmarkResult(
        benchmark_type="mixed_topic",
        case_id=case["case_id"],
        metric={
            "active_topics": active_topics,
            "tech_route_count": tech_route_count,
            "expected_active_topic": case["expected_active_topic"],
        },
        passed=passed,
    )


def write_reports(results: list[BenchmarkResult]) -> None:
    """Write markdown and CSV benchmark summaries."""
    ensure_storage_dirs()
    REPORT_MD.write_text(build_markdown_report(results), encoding="utf-8")
    with REPORT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["benchmark_type", "case_id", "passed", "metric_json"])
        for result in results:
            writer.writerow([result.benchmark_type, result.case_id, int(result.passed), json.dumps(result.metric, ensure_ascii=False)])


def build_markdown_report(results: list[BenchmarkResult]) -> str:
    """Render a compact markdown benchmark report."""
    lines = ["# Benchmark Report", ""]
    for result in results:
        lines.append(f"## {result.benchmark_type} / {result.case_id}")
        lines.append(f"- passed: {result.passed}")
        lines.append(f"- metric: `{json.dumps(result.metric, ensure_ascii=False)}`")
        lines.append("")
    return "\n".join(lines)


def run_all_benchmarks() -> dict:
    """Run all benchmark groups and return a summary dict.

    This is the callable entry point used by the FastAPI route.
    Returns a dict with keys: total, passed, failed, report_md, report_csv.
    """
    anti_noise_cases = load_json(PROJECT_ROOT / "data/benchmark/anti_noise_cases.json")
    conflict_cases = load_json(PROJECT_ROOT / "data/benchmark/conflict_cases.json")
    efficiency_cases = load_json(PROJECT_ROOT / "data/benchmark/efficiency_cases.json")
    mixed_topic_cases = load_json(PROJECT_ROOT / "data/benchmark/mixed_topic_cases.json")

    results: list[BenchmarkResult] = []
    results.extend(run_anti_noise_case(case) for case in anti_noise_cases)
    results.extend(run_conflict_case(case) for case in conflict_cases)
    results.extend(run_efficiency_case(case) for case in efficiency_cases)
    results.extend(run_mixed_topic_case(case) for case in mixed_topic_cases)

    with get_connection(BENCHMARK_DB) as connection:
        for result in results:
            insert_benchmark_result(connection, result)

    write_reports(results)
    passed_count = sum(1 for result in results if result.passed)
    return {
        "total": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "report_md": str(REPORT_MD),
        "report_csv": str(REPORT_CSV),
    }


def main() -> None:
    """Run all local benchmark groups and persist their reports."""
    summary = run_all_benchmarks()
    print(f"Ran {summary['total']} benchmark cases. Passed {summary['passed']}.")
    print(f"Reports written to {summary['report_md']} and {summary['report_csv']}.")


if __name__ == "__main__":
    main()
