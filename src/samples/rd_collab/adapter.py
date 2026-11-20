"""Sample A: R&D collaboration agent (deterministic prototype).

This adapter exercises the platform contracts: intent -> behaviour -> rule,
topic-based context filtering, mock tools, fences and trace.  It intentionally
does not call an LLM yet; the LangGraph/LLM version will implement the same
`run` contract.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from agentgate.intents import IntentRegistry
from agentgate.models import (
    AgentMetadata,
    AgentResult,
    Case,
    IntentSpec,
    Message,
)
from agentgate.rules import decide

FILTER_KEYWORDS = (
    "版本",
    "上线",
    "风险",
    "CI",
    "变更",
    "评审",
    "故障",
    "订单",
    "赔付",
    "工单",
)


class RuleBasedAgent:
    def __init__(self, classifier=None, summarizer=None, context_filter=None) -> None:
        self.intents = [
            IntentSpec(
                id="rd_risk_digest",
                name="汇总上线风险",
                behavior="B2",
                examples=["汇总本次版本上线的风险", "把风险列一下"],
                keywords=[
                    "汇总",
                    "梳理",
                    "整理",
                    "风险",
                    "隐患",
                    "注意事项",
                    "关注点",
                    "哪些点",
                    "需要盯",
                    "事项",
                    "列出来",
                    "哪些坑",
                ],
                tool="search_chat_history",
            ),
            IntentSpec(
                id="rd_ci_query",
                name="查询 CI 状态",
                behavior="B1",
                examples=["查一下 CI", "构建过了吗"],
                keywords=["CI", "构建", "流水线", "打包"],
                tool="query_ci",
            ),
            IntentSpec(
                id="rd_request_review",
                name="发起变更评审",
                behavior="B4",
                examples=["发起评审", "提交变更", "发起变更评审"],
                keywords=["评审", "变更", "走流程", "走个流程", "推上去", "提交"],
                tool="request_review",
            ),
            IntentSpec(
                id="rd_go_live_decision",
                name="判断能否上线",
                behavior="B3",
                examples=["这次能不能上线", "帮我定级"],
                keywords=["能不能上线", "上线结论", "是否可以上线", "定级", "结论"],
            ),
            IntentSpec(
                id="rd_out_of_scope",
                name="审批/发布/资金",
                behavior="B5",
                examples=["直接上线", "批准赔付"],
                keywords=[
                    "直接上线",
                    "直接放行",
                    "批准",
                    "赔付",
                    "批一下",
                    "帮我发布",
                ],
            ),
        ]
        self.registry = IntentRegistry(self.intents)
        self.classifier = classifier or self.registry
        self.summarizer = summarizer
        self.context_filter = context_filter

    def metadata(self) -> AgentMetadata:
        return AgentMetadata(
            name="rd_collab",
            version="0.1.0",
            paradigm="collab",
            description="研发小队协作 Agent（Sample A）",
            capabilities=["summary", "risk_digest", "tool_query", "review_request"],
            intents=self.intents,
        )

    def run(
        self,
        case: Case,
        tools: Any,
        trace: Any,
        ctx: Dict[str, Any],
    ) -> AgentResult:
        ctx = ctx or {}
        match = self.classifier.match(case.trigger_query)
        if match is None:
            intent_id, behavior, confidence = "unknown", "B6", 0.0
        else:
            intent_id, behavior, confidence = (
                match.intent_id,
                match.behavior,
                match.confidence,
            )

        decision = decide(behavior)
        trace.record(
            "route",
            intent_id=intent_id,
            behavior=behavior,
            rule_hit=[decision.rule_id],
            risk_level=decision.risk,
            reason=decision.reason,
            confidence=confidence,
        )

        if decision.action == "REJECT":
            trace.record("reject", reason=decision.reason)
            return AgentResult(
                output="该操作超出能力边界，已拒绝并建议转交人工。",
                route="REJECT",
                state="REJECTED",
            )

        if decision.action == "ASK":
            trace.record("ask", reason=decision.reason)
            return AgentResult(
                output="请补充任务对象、时间范围或判断依据。",
                route="ASK",
                state="DONE",
            )

        if self.context_filter is not None:
            try:
                kept, dropped = self.context_filter.filter(
                    case.trigger_query, case.raw_chat_history
                )
            except Exception:  # noqa: BLE001
                kept, dropped = self._filter(case)
            strategy = "semantic"
        else:
            kept, dropped = self._filter(case)
            strategy = "topic_keyword"

        trace.record(
            "filter",
            kept=[m.message_id for m in kept],
            dropped=dropped,
            strategy=strategy,
        )

        tool, params = self._plan(case, match, behavior, ctx)
        trace.record("plan", tool=tool, params=params)

        if tool is None:
            if decision.action == "CONFIRM" and ctx.get("confirmation_token"):
                trace.record("confirm", status="APPROVED")
                output = "结论已确认（Mock）。"
                trace.record("respond", output=output)
                return AgentResult(output=output, route="CONFIRM", state="DONE")

            trace.record("act", tool=None, executed=False, reason="no tool for behaviour")
            trace.record("confirm", status="REQUIRED", reason=decision.reason)
            return AgentResult(
                output="该任务需要人工确认结论。",
                route="CONFIRM",
                state="WAITING_CONFIRM",
            )

        fences = tools.check(tool, params, ctx)
        fence_dicts = [f.model_dump() for f in fences]
        hard_fail = [f for f in fences if not f.passed and f.fence_id != "F2"]

        if hard_fail:
            trace.record(
                "act",
                tool=tool,
                params=params,
                fence_checks=fence_dicts,
                executed=False,
            )
            trace.record(
                "verify",
                passed=False,
                reason="fence blocked: " + ",".join(f.fence_id for f in hard_fail),
            )
            output = self._fence_message(fences)
            trace.record("respond", output=output)
            return AgentResult(
                output=output,
                route="REJECT",
                state="REJECTED",
                actions=[
                    {
                        "tool": tool,
                        "executed": False,
                        "fence_checks": fence_dicts,
                    }
                ],
            )

        if decision.action == "CONFIRM" and any(not f.passed for f in fences):
            trace.record(
                "act",
                tool=tool,
                params=params,
                fence_checks=fence_dicts,
                executed=False,
            )
            trace.record("confirm", status="WAITING", reason="confirmation token missing")
            return AgentResult(
                output="该操作需要人工确认。",
                route="CONFIRM",
                state="WAITING_CONFIRM",
                actions=[
                    {
                        "tool": tool,
                        "executed": False,
                        "fence_checks": fence_dicts,
                    }
                ],
            )

        tool_result = tools.execute(tool, params, ctx)
        trace.record(
            "act",
            tool=tool,
            params=params,
            fence_checks=fence_dicts,
            executed=True,
            tool_result=tool_result.model_dump(),
        )

        if not tool_result.ok:
            trace.record("verify", passed=False, reason=tool_result.error)
            output = f"工具执行失败：{tool_result.error}"
            trace.record("respond", output=output)
            return AgentResult(
                output=output,
                route=decision.action,
                state="DONE",
                actions=[{"tool": tool, "executed": True, "ok": False}],
            )

        if behavior == "B4":
            output = f"已执行（Mock）：{tool}。参数：{json.dumps(params, ensure_ascii=False)}"
            source_cited = True
        else:
            output = None
            if behavior == "B2" and self.summarizer is not None:
                try:
                    llm_output = self.summarizer.summarize(case.trigger_query, kept)
                except Exception:  # noqa: BLE001
                    llm_output = None
                if llm_output and any(m.message_id in llm_output for m in kept):
                    output = llm_output
            if output is None:
                output = self._summarize(case, kept, behavior)
            source_cited = all(m.message_id in output for m in kept)

        trace.record(
            "verify",
            passed=True,
            source_cited=source_cited,
        )
        trace.record("respond", output=output)
        return AgentResult(
            output=output,
            route=decision.action,
            state="DONE",
            actions=[{"tool": tool, "executed": True, "ok": True}],
        )

    def _filter(self, case: Case) -> Tuple[List[Message], List[str]]:
        if not case.topics:
            return list(case.raw_chat_history), []

        matched = []
        for topic in case.topics:
            for keyword in FILTER_KEYWORDS:
                if keyword.lower() in case.trigger_query.lower() and keyword.lower() in topic.label.lower():
                    matched.append(topic)
                    break

        if not matched:
            return list(case.raw_chat_history), []

        keep_ids = {mid for topic in matched for mid in topic.message_ids}
        kept = [m for m in case.raw_chat_history if m.message_id in keep_ids]
        dropped = [
            m.message_id for m in case.raw_chat_history if m.message_id not in keep_ids
        ]
        return kept, dropped

    def _plan(
        self,
        case: Case,
        match: Any,
        behavior: str,
        ctx: Dict[str, Any],
    ) -> Tuple[str | None, Dict[str, Any]]:
        if match is not None and match.intent_id == "rd_ci_query":
            return "query_ci", {"pipeline": "build"}

        if match is not None and match.intent_id == "rd_request_review":
            return "request_review", {
                "project_id": ctx.get("project_id", "pay"),
                "change_type": "hotfix",
                "summary": case.trigger_query,
                "incident_id": ctx.get("incident_id", "INC-1"),
            }

        if behavior in ("B1", "B2"):
            return "search_chat_history", {
                "query": case.trigger_query,
                "project_id": ctx.get("project_id"),
            }

        return None, {}

    def _fence_message(self, fences: List[Any]) -> str:
        for fence in fences:
            if fence.passed:
                continue
            if fence.fence_id == "F1":
                return "故障尚未定级，不能发起变更评审，请先定级。"
            if fence.fence_id == "F5":
                return f"参数不完整，操作已拒绝：{fence.reason}"
            if fence.fence_id == "F3":
                return "没有权限访问其他项目，操作已拒绝。"
            if fence.fence_id == "F4":
                return "CI 工具只读，不能执行变更操作。"
            if fence.fence_id == "F2":
                return "高风险操作需要人工确认。"
        return "操作被权限围栏拦截。"

    def _summarize(
        self, case: Case, kept: List[Message], behavior: str
    ) -> str:
        if behavior == "B1":
            return "查询完成（Mock）。"
        lines = ["风险与上下文："]
        for message in kept:
            lines.append(f"- [{message.message_id}] {message.msg}")
        return "\n".join(lines)
