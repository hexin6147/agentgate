"""Rule engine: behaviour class -> action.

Rules are keyed on the platform behaviour taxonomy (B1-B6), never on
business-specific task names.
"""
from __future__ import annotations

from .models import RuleDecision

RULE_MAP = {
    "B1": ("R1", "AUTO", "low", "read-only retrieval"),
    "B2": ("R1", "AUTO", "low", "draft from facts; human reviews"),
    "B3": ("R2", "CONFIRM", "high", "conclusion / rating / recommendation"),
    "B4": ("R5", "CONFIRM", "high", "write or change action"),
    "B5": ("R4", "REJECT", "high", "out of scope"),
    "B6": ("R3", "ASK", "low", "insufficient information"),
}


def decide(behavior: str) -> RuleDecision:
    if behavior not in RULE_MAP:
        raise ValueError(f"unknown behaviour: {behavior}")
    rule_id, action, risk, reason = RULE_MAP[behavior]
    return RuleDecision(rule_id=rule_id, action=action, risk=risk, reason=reason)
