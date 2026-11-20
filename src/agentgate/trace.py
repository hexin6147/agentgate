"""Structured trace recorder.

Business-level trace is recorded explicitly; we do not rely on a framework to
export it.  This is the input for hard-rule evaluation and badcase attribution.

P0 adds a span tree on top of the original ``steps`` list.  ``record()`` keeps
its old return shape (and gains a ``span_id`` key); each recorded node becomes
a child span of the run span, so the tree is ``run -> step -> tool/llm``.
"""
from __future__ import annotations

import json
import os
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


_current_recorder: ContextVar[Optional["TraceRecorder"]] = ContextVar(
    "agentgate_current_recorder", default=None
)


def set_current_recorder(recorder: Optional["TraceRecorder"]) -> None:
    _current_recorder.set(recorder)


def current_recorder() -> Optional["TraceRecorder"]:
    return _current_recorder.get()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraceRecorder:
    def __init__(self, run_id: str, case_id: str):
        self.run_id = run_id
        self.case_id = case_id
        self.steps: List[Dict[str, Any]] = []
        self.started_at = _now()
        self.ended_at: Optional[str] = None
        self._spans: List[Dict[str, Any]] = []
        self._root_span_id: Optional[str] = None
        self._current_span_id: Optional[str] = None
        self._current_step_span_id: Optional[str] = None
        self._current_step_status = "ok"

    # ------------------------------------------------------------------ spans
    def set_root_span(self, span_id: str) -> None:
        self._root_span_id = span_id

    def start_span(
        self,
        name: str,
        parent_id: str | None = None,
        **attrs: Any,
    ) -> str:
        if parent_id is None:
            parent_id = self._current_span_id
        span_id = f"span_{uuid.uuid4().hex[:12]}"
        self._spans.append(
            {
                "span_id": span_id,
                "parent_id": parent_id,
                "name": name,
                "start_ts": _now(),
                "end_ts": None,
                "status": "running",
                "attrs": dict(attrs),
            }
        )
        self._current_span_id = span_id
        return span_id

    def end_span(self, span_id: str, status: str = "ok", **attrs: Any) -> None:
        span = next(
            (item for item in self._spans if item["span_id"] == span_id), None
        )
        if span is None:
            return
        span["end_ts"] = _now()
        span["status"] = status
        span["attrs"].update(attrs)
        if self._current_span_id == span_id:
            self._current_span_id = span["parent_id"]
        if self._current_step_span_id == span_id:
            self._current_step_span_id = None

    @property
    def spans(self) -> List[Dict[str, Any]]:
        return [
            {
                **span,
                "attrs": dict(span.get("attrs", {})),
            }
            for span in self._spans
        ]

    # ------------------------------------------------------------------ steps
    def _close_step(self) -> None:
        if self._current_step_span_id is None:
            return
        self.end_span(
            self._current_step_span_id,
            status=self._current_step_status,
        )
        self._current_step_span_id = None
        self._current_step_status = "ok"

    def finish(self) -> None:
        """Close the last open step span; the harness closes the root span."""
        self._close_step()
        self.ended_at = _now()

    def record(self, node: str, **fields: Any) -> Dict[str, Any]:
        # Each recorded node is one step span.  Tools/LLMs called between this
        # record and the next one become children of the current step.
        self._close_step()
        attrs = {"kind": "step", "node": node, **fields}
        span_id = self.start_span(
            node,
            parent_id=self._root_span_id,
            **attrs,
        )
        self._current_step_span_id = span_id
        self._current_step_status = "error" if node == "error" else "ok"

        step: Dict[str, Any] = {
            "seq": len(self.steps) + 1,
            "node": node,
            "ts": datetime.now(timezone.utc).isoformat(),
            "span_id": span_id,
        }
        step.update(fields)
        self.steps.append(step)
        return step

    # ---------------------------------------------------------------- export
    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "trace_id": self.run_id,
            "case_id": self.case_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "steps": self.steps,
            "spans": self.spans,
        }

    def dump(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
