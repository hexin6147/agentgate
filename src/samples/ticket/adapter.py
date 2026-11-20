"""Sample B: restricted after-sales ticket agent.

Reuses the Sample A pipeline hooks so the same LangGraph/Harness can evaluate
a second paradigm: static red lines, deterministic answers, high-risk approval.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from agentgate.intents import IntentRegistry
from agentgate.models import AgentMetadata, Case, IntentSpec, Message
from samples.rd_collab.adapter import RuleBasedAgent

ORDER_RE = re.compile(r"ORD-\d+")
USER_RE = re.compile(r"U\d+")
NUMBER_RE = re.compile(r"(\d+)")


class RuleBasedTicketAgent(RuleBasedAgent):
    def __init__(self) -> None:
        super().__init__()
        self.intents = [
            IntentSpec(
                id="ticket_query_order",
                name="查询订单",
                behavior="B1",
                examples=["查一下订单", "订单到哪了"],
                keywords=["订单", "物流", "到哪"],
                tool="query_order",
            ),
            IntentSpec(
                id="ticket_policy_lookup",
                name="查询退换政策",
                behavior="B1",
                examples=["退换货规则", "能赔多少"],
                keywords=["退换", "退款政策", "赔付规则", "赔多少"],
                tool="lookup_refund_policy",
            ),
            IntentSpec(
                id="ticket_submit",
                name="提交售后工单",
                behavior="B4",
                examples=["提交工单", "帮我申请退款"],
                keywords=["提交工单", "申请退款", "发起赔付"],
                tool="submit_ticket",
            ),
            IntentSpec(
                id="ticket_decision",
                name="判断能否赔付",
                behavior="B3",
                examples=["这个能赔吗", "能不能退"],
                keywords=["能赔吗", "能不能退", "可以退吗"],
            ),
            IntentSpec(
                id="ticket_out_of_scope",
                name="直接赔付/审批",
                behavior="B5",
                examples=["直接退款", "批准赔付"],
                keywords=["直接退款", "直接赔付", "批准赔偿"],
            ),
        ]
        self.registry = IntentRegistry(self.intents)
        self.classifier = self.registry

    def metadata(self) -> AgentMetadata:
        return AgentMetadata(
            name="ticket_agent",
            version="0.1.0",
            paradigm="restricted",
            description="售后工单受限 Agent（Sample B）",
            capabilities=["order_query", "policy_lookup", "ticket_submit"],
            intents=self.intents,
        )

    def _filter(self, case: Case) -> Tuple[List[Message], List[str]]:
        return list(case.raw_chat_history), []

    def _plan(
        self,
        case: Case,
        match: Any,
        behavior: str,
        ctx: Dict[str, Any],
    ) -> Tuple[str | None, Dict[str, Any]]:
        if match is None:
            return None, {}

        query = case.trigger_query
        order_match = ORDER_RE.search(query)
        order_id = order_match.group(0) if order_match else ctx.get("order_id", "ORD-1001")

        if match.intent_id == "ticket_query_order":
            user_match = USER_RE.search(query)
            user_id = user_match.group(0) if user_match else ctx.get("user_id")
            return "query_order", {"order_id": order_id, "user_id": user_id}

        if match.intent_id == "ticket_policy_lookup":
            return "lookup_refund_policy", {
                "category": ctx.get("category", "general")
            }

        if match.intent_id == "ticket_submit":
            cleaned = USER_RE.sub(" ", ORDER_RE.sub(" ", query))
            numbers = [int(n) for n in NUMBER_RE.findall(cleaned)]
            amount = numbers[-1] if numbers else ctx.get("refund_amount", 0)
            return "submit_ticket", {
                "order_id": order_id,
                "ticket_type": "refund",
                "description": query,
                "refund_amount": amount,
            }

        return None, {}

    def _summarize(
        self, case: Case, kept: List[Message], behavior: str
    ) -> str:
        if behavior == "B1":
            return "查询完成（Mock）。"
        return "已处理。"

    def _fence_message(self, fences: List[Any]) -> str:
        for fence in fences:
            if fence.passed:
                continue
            if fence.fence_id == "T1":
                return "请先完成身份核实。"
            if fence.fence_id == "T2":
                return "赔付金额超过权限，需人工审批。"
            if fence.fence_id == "T5":
                return "不能查询其他用户的订单。"
            if fence.fence_id == "F2":
                return "高风险操作需要人工确认。"
            if fence.fence_id == "F5":
                return f"参数不完整：{fence.reason}"
        return "操作被权限围栏拦截。"
