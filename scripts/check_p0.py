#!/usr/bin/env python
"""P0 acceptance check.

Runs three real cases through the LLM-backed agent (real Ollama), then verifies
the observability chain end to end: run/span/usage persistence, structured
logs, and step recovery from the span tree.

Usage:
    python scripts/check_p0.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from typing import Any, Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.factory import build_agent  # noqa: E402
from agentgate.harness import Harness  # noqa: E402
from agentgate.runner import Runner  # noqa: E402
from agentgate.store import (  # noqa: E402
    get_run,
    get_spans,
    init_db,
    query_runs,
    save_report,
)
from agentgate.tools import ToolRegistry  # noqa: E402

DB_PATH = os.path.join(ROOT, "data", "agentgate_p0_check.db")
LOG_PATH = os.path.join(ROOT, "logs", "agentgate.jsonl")
TRACE_DIR = os.path.join(ROOT, "eval", "results", "run_p0")
SCENARIO = "S1"

CASES: List[Tuple[str, Dict[str, Any]]] = [
    ("eval/dataset/golden/sample_rd_001.json", {"project_id": "pay"}),
    ("eval/dataset/golden/gen_normal_ci_000.json", {"project_id": "pay"}),
    (
        "eval/dataset/adversarial/sample_adv_001.json",
        {"project_id": "pay", "incident_leveled": False},
    ),
]


class Checker:
    def __init__(self) -> None:
        self.results: List[Tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append((name, bool(ok), detail))

    def report(self) -> int:
        failed = 0
        for name, ok, detail in self.results:
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))
            if not ok:
                failed += 1
        print(
            f"\nP0 CHECK: {len(self.results) - failed}/{len(self.results)} PASS"
        )
        return 0 if failed == 0 else 1


def span_depth(spans: List[Dict[str, Any]]) -> int:
    by_id = {span["span_id"]: span for span in spans}
    best = 0
    for span in spans:
        depth = 1
        parent = span.get("parent_id")
        guard = 0
        while parent and parent in by_id and guard <= len(spans):
            depth += 1
            parent = by_id[parent].get("parent_id")
            guard += 1
        best = max(best, depth)
    return best


def step_names_from_spans(spans: List[Dict[str, Any]]) -> List[str]:
    return [
        span["name"]
        for span in spans
        if span.get("attrs", {}).get("kind") == "step"
    ]


def usage_for_run(run_id: str) -> List[Tuple[int, int, float]]:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            "SELECT prompt_tokens, completion_tokens, latency_ms "
            "FROM usage WHERE run_id = ?",
            (run_id,),
        ).fetchall()


def report_metrics_for_run(run_id: str) -> Dict[str, Any] | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT metrics_json FROM reports WHERE run_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (run_id,),
        ).fetchone()
    return json.loads(row[0]) if row else None


def main() -> int:
    checker = Checker()

    os.environ["AGENTGATE_DB"] = DB_PATH
    os.environ["AGENTGATE_LOG"] = LOG_PATH
    for path in (DB_PATH, LOG_PATH):
        if os.path.exists(path):
            os.remove(path)
    init_db()

    agent = build_agent("llm", context="rule")
    tools = ToolRegistry()
    runner = Runner(
        Harness(tools, trace_dir=TRACE_DIR, scenario=SCENARIO)
    )

    runs = []
    for index, (rel_path, ctx) in enumerate(CASES, start=1):
        path = os.path.join(ROOT, rel_path)
        checker.check(f"case {index} file exists", os.path.exists(path), path)
        if not os.path.exists(path):
            continue
        try:
            result = runner.run_case_file(
                path, agent, ctx, scenario=SCENARIO
            )
            runs.append((rel_path, result))
            checker.check(
                f"case {index} run completed",
                result.run_id.startswith("run_"),
                f"{result.run_id} status={result.status} route={result.route}",
            )
        except Exception as exc:  # noqa: BLE001 - keep checking other cases
            checker.check(
                f"case {index} run completed",
                False,
                f"{type(exc).__name__}: {exc}",
            )

    checker.check("three cases ran", len(runs) == 3, f"ran={len(runs)}")

    for index, (rel_path, result) in enumerate(runs, start=1):
        prefix = f"run {index} ({os.path.basename(rel_path)})"
        run = get_run(result.run_id)
        checker.check(f"{prefix}: stored by run_id", run is not None, result.run_id)

        trace_id = result.trace.get("trace_id") or result.run_id
        by_trace = query_runs(trace_id=trace_id)
        checker.check(
            f"{prefix}: query by trace_id",
            any(row["run_id"] == result.run_id for row in by_trace),
            f"trace_id={trace_id}",
        )

        by_scenario = query_runs(scenario=SCENARIO)
        checker.check(
            f"{prefix}: query by scenario",
            any(row["run_id"] == result.run_id for row in by_scenario),
            f"scenario={SCENARIO}",
        )

        spans = get_spans(result.run_id)
        depth = span_depth(spans)
        checker.check(
            f"{prefix}: span depth >= 3", depth >= 3, f"depth={depth}"
        )

        recovered = step_names_from_spans(spans)
        expected = [step["node"] for step in result.trace.get("steps", [])]
        checker.check(
            f"{prefix}: steps recoverable from spans",
            recovered == expected and bool(expected),
            f"spans={recovered}",
        )

        usage = usage_for_run(result.run_id)
        total_latency = sum(row[2] or 0.0 for row in usage)
        checker.check(
            f"{prefix}: usage recorded",
            bool(usage) and total_latency > 0,
            f"rows={len(usage)} latency_ms={total_latency:.1f}",
        )

        metrics = {
            "prompt_tokens": sum(row[0] or 0 for row in usage),
            "completion_tokens": sum(row[1] or 0 for row in usage),
            "latency_ms": round(total_latency, 3),
            "usage_calls": len(usage),
        }
        save_report(
            {
                "run_id": result.run_id,
                "scenario": SCENARIO,
                "metrics": metrics,
            },
            run_id=result.run_id,
        )
        stored_metrics = report_metrics_for_run(result.run_id)
        checker.check(
            f"{prefix}: report has token/latency",
            stored_metrics is not None
            and "prompt_tokens" in stored_metrics
            and "latency_ms" in stored_metrics,
            str(stored_metrics),
        )

    run_ids = {result.run_id for _, result in runs}
    log_records: List[Dict[str, Any]] = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    log_records.append(json.loads(line))

    checker.check(
        "logs: every line has trace_id",
        bool(log_records)
        and all(record.get("trace_id") for record in log_records),
        f"lines={len(log_records)}",
    )
    logged_runs = {record.get("run_id") for record in log_records}
    checker.check(
        "logs: every run appears",
        run_ids <= logged_runs,
        f"missing={sorted(run_ids - logged_runs)}",
    )

    return checker.report()


if __name__ == "__main__":
    raise SystemExit(main())
