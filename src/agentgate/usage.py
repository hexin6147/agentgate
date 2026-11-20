"""LLM/embedding usage collection.

``record_usage`` appends to the active ``collect_usage()`` list.  The harness
opens that context around ``agent.run`` and persists the rows afterwards.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from .logging import get_context, log_event

_collector: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar(
    "agentgate_usage_collector", default=None
)


@contextmanager
def collect_usage() -> Iterator[List[Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    token = _collector.set(rows)
    try:
        yield rows
    finally:
        _collector.reset(token)


def record_usage(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
) -> None:
    context = get_context()
    row = {
        "run_id": context["run_id"],
        "span_id": context["span_id"],
        "model": model,
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "latency_ms": float(latency_ms or 0.0),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    rows = _collector.get()
    if rows is not None:
        rows.append(row)
        return

    # A direct call outside a harness run still leaves an audit line; it is not
    # persisted because there is no run to attach it to.
    log_event(
        "usage_uncollected",
        level="warning",
        model=model,
        prompt_tokens=row["prompt_tokens"],
        completion_tokens=row["completion_tokens"],
        latency_ms=row["latency_ms"],
    )
