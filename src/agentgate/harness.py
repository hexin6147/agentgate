"""Harness: outer runtime control around an agent adapter.

Owns run_id, error handling, trace persistence and the final RunResult.
P0 adds structured logging, a root span, and SQLite persistence.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from . import logging as ag_log
from .models import Case, RunResult
from .store import init_db, save_run, save_spans, save_usage
from .trace import TraceRecorder, set_current_recorder
from .usage import collect_usage


class Harness:
    def __init__(
        self,
        tools: Any,
        trace_dir: Optional[str] = None,
        scenario: Optional[str] = None,
    ):
        self.tools = tools
        self.trace_dir = trace_dir
        self.scenario = scenario

    def run_case(
        self,
        agent: Any,
        case: Case,
        ctx: Optional[Dict[str, Any]] = None,
        scenario: Optional[str] = None,
    ) -> RunResult:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        scenario = scenario if scenario is not None else self.scenario
        trace = TraceRecorder(run_id=run_id, case_id=case.case_id)

        set_current_recorder(trace)
        ag_log.set_trace(run_id, run_id)
        root_span = trace.start_span(
            "run",
            kind="root",
            case_id=case.case_id,
            scenario=scenario,
        )
        trace.set_root_span(root_span)
        ag_log.log_event(
            "run_start", case_id=case.case_id, scenario=scenario
        )

        started = time.perf_counter()
        status = "FAILED"
        route = "ERROR"
        output = ""
        error: Optional[str] = None
        error_type: Optional[str] = None

        usage_rows: List[Dict[str, Any]] = []
        try:
            with collect_usage() as usage_rows:
                merged_ctx = {**(ctx or {}), **case.context}
                result = agent.run(case, self.tools, trace, merged_ctx)
                status = result.state
                route = result.route
                output = result.output
        except Exception as exc:  # noqa: BLE001 - harness must isolate case failures
            error = str(exc)
            error_type = ag_log.classify_error(exc)
            trace.record("error", error=error)
            ag_log.log_event(
                "run_error",
                level="error",
                error_type=error_type,
                msg=error,
            )
        finally:
            trace.finish()
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            root_attrs: Dict[str, Any] = {"latency_ms": latency_ms}
            if error_type is not None:
                root_attrs["error_type"] = error_type
            trace.end_span(
                root_span,
                status="error" if error is not None else "ok",
                **root_attrs,
            )
            set_current_recorder(None)

        run_result = RunResult(
            run_id=run_id,
            case_id=case.case_id,
            status=status,
            route=route,
            output=output,
            trace=trace.to_dict(),
            error=error,
        )

        for row in usage_rows:
            if not row.get("run_id"):
                row["run_id"] = run_id

        try:
            init_db()
            save_run(run_result, scenario=scenario)
            save_spans(run_id, trace.spans)
            save_usage(usage_rows)
        except Exception as exc:  # noqa: BLE001 - storage must not mask the run
            ag_log.log_event(
                "persist_error",
                level="error",
                error_type="internal",
                msg=str(exc),
            )

        if self.trace_dir:
            trace.dump(f"{self.trace_dir}/{run_id}/{case.case_id}.json")

        ag_log.log_event(
            "run_end",
            status=status,
            route=route,
            latency_ms=latency_ms,
            error_type=error_type,
        )
        ag_log.set_trace("-", None)
        return run_result
