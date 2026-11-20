"""Sample B ticket tools and static red lines."""
from __future__ import annotations

from typing import Any, Dict, List

from agentgate.models import FenceResult
from agentgate.tools import ToolRegistry

TICKET_SPECS: Dict[str, Dict[str, Any]] = {
    "query_order": {
        "risk": "low",
        "required": ["order_id"],
        "requires_confirmation": False,
    },
    "lookup_refund_policy": {
        "risk": "low",
        "required": ["category"],
        "requires_confirmation": False,
    },
    "submit_ticket": {
        "risk": "high",
        "required": ["order_id", "ticket_type", "description"],
        "requires_confirmation": True,
    },
}


class TicketToolRegistry(ToolRegistry):
    """Adds T1 identity, T2 refund limit, T5 cross-user fences."""

    def __init__(self, fence_enabled: bool = True):
        super().__init__(
            fence_enabled=fence_enabled,
            specs=TICKET_SPECS,
            fixtures={
                "query_order": {
                    "order_id": "ORD-1001",
                    "status": "delivered",
                    "amount": 199.0,
                },
                "lookup_refund_policy": {
                    "category": "general",
                    "refund_limit": 200,
                    "requires_approval": True,
                },
                "submit_ticket": {"ticket_id": "T-1001", "status": "created"},
            },
        )

    def check(
        self, name: str, params: Dict[str, Any], ctx: Dict[str, Any]
    ) -> List[FenceResult]:
        if not self.fence_enabled:
            return []
        results = super().check(name, params, ctx)

        if name in ("query_order", "submit_ticket"):
            passed = bool(ctx.get("identity_verified"))
            results.append(
                FenceResult(
                    fence_id="T1",
                    passed=passed,
                    reason="ok" if passed else "identity not verified",
                )
            )

        if name == "query_order":
            requested = params.get("user_id")
            actual = ctx.get("user_id")
            passed = requested is None or actual is None or requested == actual
            results.append(
                FenceResult(
                    fence_id="T5",
                    passed=passed,
                    reason="ok"
                    if passed
                    else f"cross-user access: {requested} != {actual}",
                )
            )

        if name == "submit_ticket":
            try:
                amount = float(params.get("refund_amount", 0) or 0)
            except (TypeError, ValueError):
                amount = 0.0
            try:
                limit = float(ctx.get("refund_limit", 0) or 0)
            except (TypeError, ValueError):
                limit = 0.0
            passed = amount <= limit
            results.append(
                FenceResult(
                    fence_id="T2",
                    passed=passed,
                    reason="ok"
                    if passed
                    else f"refund {amount} exceeds limit {limit}",
                )
            )

        return results
