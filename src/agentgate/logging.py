"""Structured JSON Lines logging.

Every event is one JSON object on its own line.  Trace/run/span ids live in
context variables so call sites (tools, LLM client, harness) do not have to
thread them through function signatures.
"""
from __future__ import annotations

import json
import os
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

ERROR_TYPES = ("timeout", "validation", "upstream", "internal")

_TRACE_ID: ContextVar[Optional[str]] = ContextVar("agentgate_trace_id", default=None)
_RUN_ID: ContextVar[Optional[str]] = ContextVar("agentgate_run_id", default=None)
_SPAN_ID: ContextVar[Optional[str]] = ContextVar("agentgate_span_id", default=None)

_DEFAULT_LOG_PATH = os.path.join("logs", "agentgate.jsonl")


def log_path() -> str:
    """Path override for tests / check scripts; default is logs/agentgate.jsonl."""
    return os.getenv("AGENTGATE_LOG", _DEFAULT_LOG_PATH)


def set_trace(trace_id: str, run_id: str | None = None) -> None:
    _TRACE_ID.set(trace_id)
    _RUN_ID.set(run_id)
    _SPAN_ID.set(None)


def set_span(span_id: str | None) -> None:
    _SPAN_ID.set(span_id)


def current_span_id() -> Optional[str]:
    return _SPAN_ID.get()


def get_context() -> Dict[str, Optional[str]]:
    return {
        "trace_id": _TRACE_ID.get(),
        "run_id": _RUN_ID.get(),
        "span_id": _SPAN_ID.get(),
    }


def classify_error(exc: BaseException) -> str:
    """Map an exception to the P0 error enum."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timed out" in text:
        return "timeout"
    if "validation" in name or "valueerror" in name or "keyerror" in name:
        return "validation"
    if any(
        token in name
        for token in ("api", "connection", "http", "ratelimit", "upstream")
    ):
        return "upstream"
    return "internal"


def log_event(event: str, level: str = "info", **fields: Any) -> None:
    error_type = fields.get("error_type")
    if error_type is not None and error_type not in ERROR_TYPES:
        fields["error_type"] = "internal"

    record: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        "trace_id": _TRACE_ID.get() or "-",
        "run_id": _RUN_ID.get() or "-",
    }

    span_id = fields.pop("span_id", None) or _SPAN_ID.get()
    if span_id:
        record["span_id"] = span_id
    record.update(fields)

    path = log_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
