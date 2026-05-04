from __future__ import annotations

"""Evaluate consolidator merge quality against the consolidation eval set.

Measures:
  - merge_precision: of pairs the system merged, how many were expected
  - merge_recall: of pairs expected to merge, how many did the system merge
  - over_merge_rate: pairs merged that should have stayed separate
  - under_merge_rate: pairs that should have merged but stayed separate
  - cluster_count_accuracy: whether final cluster count matches expected
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.consolidator import MemoryConsolidator
from app.storage.models import MemoryObject


CASES_FILE = PROJECT_ROOT / "data" / "benchmark" / "consolidation_cases.json"


def load_cases() -> list[dict]:
    with CASES_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_memory(raw: dict) -> MemoryObject:
    return MemoryObject(**raw)


def find_cluster_id(memory_id: str, clusters: list[MemoryObject]) -> int | None:
    for idx, cluster in enumerate(clusters):
        if cluster.memory_id == memory_id:
            return idx
        if memory_id in cluster.source_event_ids:
            return idx
    return None


def compute_actual_merges(
    input_ids: list[str],
    clusters: list[MemoryObject],
    input_memories: list[MemoryObject],
    traces: list,
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    explicit_merges: set[tuple[str, str]] = set()
    for t in traces:
        if t.merge_decision:
            pair = (min(t.primary_memory_id, t.candidate_memory_id),
                    max(t.primary_memory_id, t.candidate_memory_id))
            explicit_merges.add(pair)

    all_pairs: set[tuple[str, str]] = set()
    for i in range(len(input_ids)):
        for j in range(i + 1, len(input_ids)):
            all_pairs.add((min(input_ids[i], input_ids[j]), max(input_ids[i], input_ids[j])))

    separate_pairs = all_pairs - explicit_merges
    return explicit_merges, separate_pairs


def normalize_pair(pair: list[str]) -> tuple[str, str]:
    return (min(pair[0], pair[1]), max(pair[0], pair[1]))


def run_case(case: dict, consolidator: MemoryConsolidator) -> dict:
    input_memories = [build_memory(raw) for raw in case["input_memories"]]
    input_ids = [m.memory_id for m in input_memories]

    result = consolidator.consolidate(input_memories)
    clusters = result.memories

    expected_merge = {normalize_pair(p) for p in case["expected_merge_pairs"]}
    expected_separate = {normalize_pair(p) for p in case["expected_separate_pairs"]}

    actual_merged, actual_separate = compute_actual_merges(input_ids, clusters, input_memories, result.traces)

    true_merge = expected_merge & actual_merged
    false_merge = actual_merged - expected_merge
    missed_merge = expected_merge - actual_merged

    merge_precision = len(true_merge) / len(actual_merged) if actual_merged else 1.0
    merge_recall = len(true_merge) / len(expected_merge) if expected_merge else 1.0
    over_merge = len(false_merge) / max(len(expected_separate), 1)
    under_merge = len(missed_merge) / max(len(expected_merge), 1)
    cluster_match = len(clusters) == case["expected_cluster_count"]

    return {
        "case_id": case["case_id"],
        "description": case["description"],
        "expected_cluster_count": case["expected_cluster_count"],
        "actual_cluster_count": len(clusters),
        "cluster_count_match": cluster_match,
        "merge_precision": round(merge_precision, 3),
        "merge_recall": round(merge_recall, 3),
        "over_merge_rate": round(over_merge, 3),
        "under_merge_rate": round(under_merge, 3),
        "expected_merge_pairs": [list(p) for p in sorted(expected_merge)],
        "actual_merged_pairs": [list(p) for p in sorted(actual_merged)],
        "false_merges": [list(p) for p in sorted(false_merge)],
        "missed_merges": [list(p) for p in sorted(missed_merge)],
        "traces": [
            {
                "primary": t.primary_memory_id,
                "candidate": t.candidate_memory_id,
                "merge": t.merge_decision,
                "relation": t.relation,
                "confidence": t.confidence,
                "filter_stage": t.filter_stage,
                "reason": t.reason,
            }
            for t in result.traces
        ],
    }


def run_all() -> None:
    cases = load_cases()
    consolidator = MemoryConsolidator()

    results = []
    total = 0
    passed = 0
    total_precision = 0.0
    total_recall = 0.0

    for case in cases:
        total += 1
        r = run_case(case, consolidator)
        results.append(r)

        status = "PASS" if r["cluster_count_match"] and r["merge_precision"] == 1.0 and r["merge_recall"] == 1.0 else "FAIL"
        if status == "PASS":
            passed += 1

        print(f"[{status}] {r['case_id']}: {r['description']}")
        print(f"       clusters: {r['actual_cluster_count']}/{r['expected_cluster_count']}  "
              f"precision={r['merge_precision']}  recall={r['merge_recall']}  "
              f"over_merge={r['over_merge_rate']}  under_merge={r['under_merge_rate']}")
        if r["false_merges"]:
            print(f"       false merges: {r['false_merges']}")
        if r["missed_merges"]:
            print(f"       missed merges: {r['missed_merges']}")
        for t in r["traces"]:
            print(f"       trace: {t['primary']}<->{t['candidate']}  "
                  f"merge={t['merge']}  relation={t['relation']}  "
                  f"stage={t['filter_stage']}  conf={t['confidence']}")

    print(f"\n{'='*60}")
    print(f"Total: {total}  Passed: {passed}  Failed: {total - passed}")
    avg_p = sum(r["merge_precision"] for r in results) / total if total else 0
    avg_r = sum(r["merge_recall"] for r in results) / total if total else 0
    print(f"Avg merge_precision: {avg_p:.3f}  Avg merge_recall: {avg_r:.3f}")

    report_path = PROJECT_ROOT / "reports" / "consolidation_eval.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Detailed results: {report_path}")


if __name__ == "__main__":
    run_all()
