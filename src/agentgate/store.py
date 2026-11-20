"""SQLite persistence for P0 observability.

Four tables: runs, spans, usage, reports.  Only the standard library is used.
The database path defaults to ``data/agentgate.db`` and can be overridden with
``AGENTGATE_DB``.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models import RunResult

_DEFAULT_DB_PATH = os.path.join("data", "agentgate.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, case_id TEXT NOT NULL,
  scenario TEXT, status TEXT, route TEXT, output TEXT, error TEXT,
  started_at TEXT, ended_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_trace ON runs(trace_id);
CREATE INDEX IF NOT EXISTS idx_runs_scenario ON runs(scenario);

CREATE TABLE IF NOT EXISTS spans (
  span_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, parent_id TEXT,
  name TEXT NOT NULL, start_ts TEXT, end_ts TEXT, status TEXT, attrs_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_spans_run ON spans(run_id);

CREATE TABLE IF NOT EXISTS usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, span_id TEXT,
  model TEXT, prompt_tokens INTEGER, completion_tokens INTEGER,
  latency_ms REAL, created_at TEXT
);

CREATE TABLE IF NOT EXISTS reports (
  report_id TEXT PRIMARY KEY, run_id TEXT, scenario TEXT,
  metrics_json TEXT, created_at TEXT
);
"""


def db_path() -> str:
    return os.getenv("AGENTGATE_DB", _DEFAULT_DB_PATH)


def _connect() -> sqlite3.Connection:
    path = db_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


def save_run(run: RunResult, scenario: str | None = None) -> None:
    trace = run.trace or {}
    trace_id = trace.get("trace_id") or run.run_id
    started_at = trace.get("started_at") or _now()
    ended_at = trace.get("ended_at") or _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO runs (
              run_id, trace_id, case_id, scenario, status, route, output,
              error, started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                trace_id,
                run.case_id,
                scenario,
                run.status,
                run.route,
                run.output,
                run.error,
                started_at,
                ended_at,
            ),
        )


def save_spans(run_id: str, spans: List[Dict[str, Any]]) -> None:
    if not spans:
        return
    rows = [
        (
            span.get("span_id"),
            run_id,
            span.get("parent_id"),
            span.get("name", ""),
            span.get("start_ts"),
            span.get("end_ts"),
            span.get("status", "ok"),
            json.dumps(span.get("attrs", {}), ensure_ascii=False, default=str),
        )
        for span in spans
    ]
    with _connect() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO spans (
              span_id, run_id, parent_id, name, start_ts, end_ts,
              status, attrs_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def save_usage(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    created = _now()
    values = [
        (
            row.get("run_id"),
            row.get("span_id"),
            row.get("model"),
            int(row.get("prompt_tokens") or 0),
            int(row.get("completion_tokens") or 0),
            float(row.get("latency_ms") or 0.0),
            row.get("created_at") or created,
        )
        for row in rows
    ]
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO usage (
              run_id, span_id, model, prompt_tokens, completion_tokens,
              latency_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )


def save_report(report: Dict[str, Any], run_id: str | None = None) -> None:
    report_id = report.get("report_id") or f"rep_{uuid.uuid4().hex[:12]}"
    metrics = report.get("metrics", report)
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO reports (
              report_id, run_id, scenario, metrics_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                report_id,
                run_id or report.get("run_id"),
                report.get("scenario"),
                json.dumps(metrics, ensure_ascii=False, default=str),
                report.get("created_at") or _now(),
            ),
        )


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    return dict(row) if row is not None else None


def get_spans(run_id: str) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM spans WHERE run_id = ? ORDER BY rowid", (run_id,)
        ).fetchall()
    spans = []
    for row in rows:
        span = dict(row)
        span["attrs"] = json.loads(span.pop("attrs_json") or "{}")
        spans.append(span)
    return spans


def query_runs(
    scenario: str | None = None,
    trace_id: str | None = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    clauses = []
    params: List[Any] = []
    if scenario is not None:
        clauses.append("scenario = ?")
        params.append(scenario)
    if trace_id is not None:
        clauses.append("trace_id = ?")
        params.append(trace_id)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(int(limit))
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM runs {where}
            ORDER BY started_at DESC, rowid DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]
