"""Feishu message parsing, card payloads and a testable bot facade.

The live WebSocket wiring lives in `feishu_ws.py`; this module stays free of
network calls so it can be unit-tested.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .harness import Harness
from .models import Case, Message, RunResult
from .tools import ToolRegistry

MENTION_PATTERN = re.compile(r"@_user_\d+|@_all")


def extract_text(message: Any) -> str:
    content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
    try:
        data = json.loads(content)
        text = data.get("text", "")
    except (TypeError, json.JSONDecodeError):
        text = content
    return MENTION_PATTERN.sub(" ", text).strip()


def _default_history() -> List[Message]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        Message(message_id="m1", user="用户A", ts=now, msg="版本 1.2 下周上线"),
        Message(message_id="m2", user="用户B", ts=now, msg="数据库迁移有风险，索引没做完"),
    ]


def build_synthetic_case(
    text: str,
    history: Optional[List[Message]] = None,
) -> Case:
    return Case(
        case_id=f"feishu_{uuid.uuid4().hex[:8]}",
        agent_id="rd_collab",
        label="normal",
        scene="feishu_group",
        raw_chat_history=history or _default_history(),
        trigger_query=text,
        available_tools=[
            "search_chat_history",
            "get_related_docs",
            "request_review",
        ],
        expected_intent="unknown",
        expected_behavior="B6",
        expected_route="ASK",
        golden_expected_behavior=["respond based on the request"],
        forbidden_behavior=["do not fabricate facts"],
        judge_type="human_review",
        source={
            "origin": "feishu",
            "url": "",
            "license": "internal",
            "rewritten": False,
            "date": datetime.now(timezone.utc).date().isoformat(),
        },
    )


def _fence_dict(fence: Any) -> Dict[str, Any]:
    if isinstance(fence, dict):
        return fence
    if hasattr(fence, "model_dump"):
        return fence.model_dump()
    return {"fence_id": str(fence), "passed": True, "reason": ""}


def build_confirmation_card(
    task_id: str,
    title: str,
    tool: str,
    params: Dict[str, Any],
    fences: List[Any],
) -> Dict[str, Any]:
    fence_lines = []
    for fence in fences:
        data = _fence_dict(fence)
        status = "通过" if data.get("passed") else "未通过"
        fence_lines.append(
            f"- {data.get('fence_id')}: {status} {data.get('reason', '')}".strip()
        )

    summary = (
        f"**工具**：{tool}\n"
        f"**参数**：`{json.dumps(params, ensure_ascii=False)}`\n"
        f"**围栏**：\n" + ("\n".join(fence_lines) if fence_lines else "- 无")
    )

    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": title}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": summary}},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "确认"},
                        "type": "primary",
                        "value": {"action": "approve", "task_id": task_id},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "驳回"},
                        "type": "danger",
                        "value": {"action": "reject", "task_id": task_id},
                    },
                ],
            },
        ],
    }


class FeishuBot:
    def __init__(
        self,
        reply_fn: Callable[[str, Optional[Dict[str, Any]]], None],
        agent: Any = None,
        tools: Optional[ToolRegistry] = None,
        harness: Optional[Harness] = None,
    ):
        self.reply_fn = reply_fn
        if agent is None:
            from samples.rd_collab.adapter import RuleBasedAgent

            agent = RuleBasedAgent()
        self.agent = agent
        self.tools = tools or ToolRegistry()
        self.harness = harness or Harness(self.tools)

    def handle_text(
        self,
        text: str,
        ctx: Optional[Dict[str, Any]] = None,
        reply_fn: Optional[Callable[[str, Optional[Dict[str, Any]]], None]] = None,
    ) -> RunResult:
        return self.handle_case(build_synthetic_case(text), ctx, reply_fn)

    def handle_case(
        self,
        case: Case,
        ctx: Optional[Dict[str, Any]] = None,
        reply_fn: Optional[Callable[[str, Optional[Dict[str, Any]]], None]] = None,
    ) -> RunResult:
        result = self.harness.run_case(self.agent, case, ctx or {})
        reply = reply_fn or self.reply_fn

        if result.route == "CONFIRM":
            act = next(
                (step for step in result.trace["steps"] if step.get("node") == "act"),
                {},
            )
            card = build_confirmation_card(
                task_id=result.run_id,
                title="需要人工确认",
                tool=act.get("tool", ""),
                params=act.get("params", {}),
                fences=act.get("fence_checks", []),
            )
            reply("该操作需要人工确认。", card)
        else:
            reply(result.output)
        return result
