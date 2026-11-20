"""Mock tool registry and permission fences.

The registry is deliberately dependency-free and deterministic.  Real
integrations can replace `execute` behind the same contract.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .logging import classify_error, log_event
from .models import FenceResult, ToolResult
from .trace import current_recorder

HIGH_RISK_TOOLS = {"create_issue", "request_review", "update_ticket_status"}

DEFAULT_SPECS: Dict[str, Dict[str, Any]] = {
    "search_chat_history": {
        "risk": "low",
        "required": ["query"],
        "requires_confirmation": False,
    },
    "get_related_docs": {
        "risk": "low",
        "required": ["doc_id"],
        "requires_confirmation": False,
    },
    "read_fault_logs": {
        "risk": "low",
        "required": ["service"],
        "requires_confirmation": False,
    },
    "query_ci": {
        "risk": "low",
        "required": ["pipeline"],
        "requires_confirmation": False,
    },
    "fetch_code_docs": {
        "risk": "low",
        "required": ["repo"],
        "requires_confirmation": False,
    },
    "create_issue": {
        "risk": "high",
        "required": ["project_id", "title", "description"],
        "requires_confirmation": True,
    },
    "request_review": {
        "risk": "high",
        "required": ["project_id", "change_type", "summary", "incident_id"],
        "requires_confirmation": True,
    },
    "update_ticket_status": {
        "risk": "high",
        "required": ["ticket_id", "status"],
        "requires_confirmation": True,
    },
    "ask_human": {
        "risk": "low",
        "required": ["question"],
        "requires_confirmation": False,
    },
    "reply_message": {
        "risk": "medium",
        "required": ["text"],
        "requires_confirmation": False,
    },
}


class ToolRegistry:
    def __init__(
        self,
        specs: Optional[Dict[str, Dict[str, Any]]] = None,
        fixtures: Optional[Dict[str, Dict[str, Any]]] = None,
        faults: Optional[Dict[str, str]] = None,
        fence_enabled: bool = True,
    ):
        self.specs = specs or DEFAULT_SPECS
        self.fixtures = fixtures or {}
        self.faults = faults or {}
        # Ablation switch: when False, `check()` returns no fences so every
        # call is treated as permitted.  Used only by eval/scripts/ablation_fence.py.
        self.fence_enabled = fence_enabled

    def spec(self, name: str) -> Dict[str, Any]:
        if name not in self.specs:
            raise KeyError(f"unknown tool: {name}")
        return self.specs[name]

    def check(
        self, name: str, params: Dict[str, Any], ctx: Dict[str, Any]
    ) -> List[FenceResult]:
        if not self.fence_enabled:
            return []
        spec = self.spec(name)
        results: List[FenceResult] = []

        missing = [
            f for f in spec["required"] if f not in params or params[f] in (None, "")
        ]
        results.append(
            FenceResult(
                fence_id="F5",
                passed=not missing,
                reason="ok" if not missing else f"missing required fields: {missing}",
            )
        )

        if name == "search_chat_history":
            requested = params.get("project_id")
            allowed = ctx.get("project_id")
            passed = requested is None or allowed is None or requested == allowed
            results.append(
                FenceResult(
                    fence_id="F3",
                    passed=passed,
                    reason="ok" if passed else f"cross-project access: {requested} != {allowed}",
                )
            )

        if name == "query_ci":
            passed = params.get("action") in (None, "read")
            results.append(
                FenceResult(
                    fence_id="F4",
                    passed=passed,
                    reason="ok" if passed else "CI tool is read-only; mutation blocked",
                )
            )

        if name == "request_review":
            passed = bool(ctx.get("incident_leveled"))
            results.append(
                FenceResult(
                    fence_id="F1",
                    passed=passed,
                    reason="ok" if passed else "incident not leveled; review blocked",
                )
            )

        if spec.get("requires_confirmation"):
            passed = bool(ctx.get("confirmation_token"))
            results.append(
                FenceResult(
                    fence_id="F2",
                    passed=passed,
                    reason="ok" if passed else "missing confirmation token",
                )
            )

        return results

    def all_passed(self, results: List[FenceResult]) -> bool:
        return all(r.passed for r in results)

    def execute(
        self, name: str, params: Dict[str, Any], ctx: Dict[str, Any]
    ) -> ToolResult:
        recorder = current_recorder()
        span_id = (
            recorder.start_span(
                f"tool:{name}", kind="tool", tool=name, params=params
            )
            if recorder is not None
            else None
        )
        log_event("tool_call", tool=name)

        try:
            self.spec(name)  # validate name
            fault = self.faults.get(name)
            if fault == "error_500":
                result = ToolResult(ok=False, error="simulated 500")
            elif fault == "timeout":
                result = ToolResult(ok=False, error="timeout")
            else:
                fixture = self.fixtures.get(name)
                if fixture is not None:
                    result = ToolResult(ok=True, data=dict(fixture))
                else:
                    result = ToolResult(
                        ok=True,
                        data={"tool": name, "params": dict(params), "ok": True},
                    )
        except Exception as exc:  # noqa: BLE001 - keep harness isolation
            error_type = classify_error(exc)
            if recorder is not None and span_id is not None:
                recorder.end_span(
                    span_id, status="error", error_type=error_type
                )
            log_event(
                "tool_error",
                level="error",
                tool=name,
                error_type=error_type,
                msg=str(exc),
            )
            raise

        error_type = None
        if not result.ok:
            error_type = "timeout" if result.error == "timeout" else "upstream"

        if recorder is not None and span_id is not None:
            recorder.end_span(
                span_id,
                status="ok" if result.ok else "error",
                ok=result.ok,
                error_type=error_type,
            )
        log_event(
            "tool_result",
            tool=name,
            ok=result.ok,
            error_type=error_type,
            msg=result.error,
        )
        return result
