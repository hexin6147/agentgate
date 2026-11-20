"""Case validation without external dependencies.

Mirrors `eval/dataset/schema.json` closely enough for the prototype.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .models import (
    BEHAVIORS,
    DIFFICULTIES,
    JUDGE_TYPES,
    LABELS,
    ROUTES,
    Case,
    Message,
    Topic,
)

REQUIRED_FIELDS = [
    "case_id",
    "agent_id",
    "label",
    "scene",
    "raw_chat_history",
    "trigger_query",
    "available_tools",
    "expected_intent",
    "expected_behavior",
    "expected_route",
    "golden_expected_behavior",
    "forbidden_behavior",
    "judge_type",
    "source",
]


class CaseValidationError(ValueError):
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _require(raw: Dict[str, Any], field: str) -> Any:
    if field not in raw or raw[field] in (None, "", []):
        raise KeyError(field)
    return raw[field]


def validate_case(raw: Dict[str, Any]) -> Case:
    errors: List[str] = []

    for field in REQUIRED_FIELDS:
        if field not in raw:
            errors.append(f"missing required field: {field}")
        elif field != "available_tools" and raw[field] in (None, "", []):
            errors.append(f"missing required field: {field}")

    if "available_tools" in raw and not isinstance(raw["available_tools"], list):
        errors.append("available_tools must be a list")

    if errors:
        raise CaseValidationError(errors)

    if raw["label"] not in LABELS:
        errors.append(f"label must be one of {LABELS}")
    if raw["expected_behavior"] not in BEHAVIORS:
        errors.append(f"expected_behavior must be one of {BEHAVIORS}")
    if raw["expected_route"] not in ROUTES:
        errors.append(f"expected_route must be one of {ROUTES}")
    if raw["judge_type"] not in JUDGE_TYPES:
        errors.append(f"judge_type must be one of {JUDGE_TYPES}")
    if raw.get("difficulty", "medium") not in DIFFICULTIES:
        errors.append(f"difficulty must be one of {DIFFICULTIES}")

    source = raw["source"]
    for field in ("origin", "license", "rewritten"):
        if field not in source:
            errors.append(f"source missing field: {field}")

    messages: List[Message] = []
    for idx, item in enumerate(raw["raw_chat_history"]):
        for field in ("message_id", "user", "ts", "msg"):
            if field not in item:
                errors.append(f"raw_chat_history[{idx}] missing field: {field}")
        if all(f in item for f in ("message_id", "user", "ts", "msg")):
            messages.append(
                Message(
                    message_id=item["message_id"],
                    user=item["user"],
                    ts=item["ts"],
                    msg=item["msg"],
                )
            )

    known_ids = {m.message_id for m in messages}
    for mid in raw.get("relevant_message_ids", []):
        if mid not in known_ids:
            errors.append(f"relevant_message_id not found in history: {mid}")

    topics: List[Topic] = []
    for item in raw.get("topics", []):
        missing = [f for f in ("topic_id", "message_ids", "label") if f not in item]
        if missing:
            errors.append(f"topic missing fields: {missing}")
            continue
        topics.append(
            Topic(
                topic_id=item["topic_id"],
                message_ids=list(item["message_ids"]),
                label=item["label"],
            )
        )

    if errors:
        raise CaseValidationError(errors)

    return Case(
        case_id=raw["case_id"],
        agent_id=raw["agent_id"],
        label=raw["label"],
        scene=raw["scene"],
        raw_chat_history=messages,
        trigger_query=raw["trigger_query"],
        available_tools=list(raw["available_tools"]),
        expected_intent=raw["expected_intent"],
        expected_behavior=raw["expected_behavior"],
        expected_route=raw["expected_route"],
        golden_expected_behavior=list(raw["golden_expected_behavior"]),
        forbidden_behavior=list(raw["forbidden_behavior"]),
        judge_type=raw["judge_type"],
        source=dict(raw["source"]),
        topics=topics,
        relevant_message_ids=list(raw.get("relevant_message_ids", [])),
        difficulty=raw.get("difficulty", "medium"),
        notes=raw.get("notes", ""),
        context=dict(raw.get("context", {})),
    )
