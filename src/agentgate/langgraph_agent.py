"""LangGraph orchestration for Sample A.

The graph covers route -> filter -> plan -> act -> verify -> respond, with
branches for reject / ask / confirm.  Business helpers are reused from the
core RuleBasedAgent so the deterministic loop and the graph stay aligned.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, TypedDict

from langgraph.graph import END, StateGraph

from .models import AgentResult
from .rules import decide


class GraphState(TypedDict, total=False):
    case: Any
    ctx: Dict[str, Any]
    tools: Any
    trace: Any
    match: Any
    decision: Any
    intent_id: str
    behavior: str
    kept: list
    dropped: list
    tool: Optional[str]
    params: Dict[str, Any]
    fences: list
    output: str
    route: str
    status: str
    actions: list


class LangGraphAgent:
    def __init__(self, core: Any):
        self.core = core
        self.graph = self._build()

    def _build(self):
        graph = StateGraph(GraphState)
        graph.add_node("route", self._route)
        graph.add_node("filter", self._filter)
        graph.add_node("plan", self._plan)
        graph.add_node("act", self._act)
        graph.add_node("verify", self._verify)
        graph.add_node("respond", self._respond)
        graph.add_node("reject", self._reject)
        graph.add_node("ask", self._ask)
        graph.add_node("confirm", self._confirm)

        graph.set_entry_point("route")
        graph.add_conditional_edges(
            "route",
            self._after_route,
            {"filter": "filter", "reject": "reject", "ask": "ask"},
        )
        graph.add_edge("filter", "plan")
        graph.add_conditional_edges(
            "plan", self._after_plan, {"act": "act", "confirm": "confirm"}
        )
        graph.add_conditional_edges(
            "act",
            self._after_act,
            {"verify": "verify", "respond": "respond", "end": END},
        )
        graph.add_edge("verify", "respond")
        graph.add_edge("respond", END)
        graph.add_edge("reject", END)
        graph.add_edge("ask", END)
        graph.add_edge("confirm", END)
        return graph.compile()

    def run(self, case: Any, tools: Any, trace: Any, ctx: Dict[str, Any]) -> AgentResult:
        state: GraphState = {
            "case": case,
            "tools": tools,
            "trace": trace,
            "ctx": ctx or {},
        }
        final = self.graph.invoke(state)
        return AgentResult(
            output=final.get("output", ""),
            route=final.get("route", "ERROR"),
            state=final.get("status", "FAILED"),
            actions=final.get("actions", []),
        )

    def _route(self, state: GraphState) -> Dict[str, Any]:
        case = state["case"]
        trace = state["trace"]
        match = self.core.classifier.match(case.trigger_query)
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
        return {
            "match": match,
            "decision": decision,
            "intent_id": intent_id,
            "behavior": behavior,
            "route": decision.action,
        }

    def _after_route(self, state: GraphState) -> str:
        action = state["decision"].action
        if action == "REJECT":
            return "reject"
        if action == "ASK":
            return "ask"
        return "filter"

    def _filter(self, state: GraphState) -> Dict[str, Any]:
        case = state["case"]
        if self.core.context_filter is not None:
            try:
                kept, dropped = self.core.context_filter.filter(
                    case.trigger_query, case.raw_chat_history
                )
            except Exception:  # noqa: BLE001
                kept, dropped = self.core._filter(case)
            strategy = "semantic"
        else:
            kept, dropped = self.core._filter(case)
            strategy = "topic_keyword"

        state["trace"].record(
            "filter",
            kept=[m.message_id for m in kept],
            dropped=dropped,
            strategy=strategy,
        )
        return {"kept": kept, "dropped": dropped}

    def _plan(self, state: GraphState) -> Dict[str, Any]:
        tool, params = self.core._plan(
            state["case"],
            state.get("match"),
            state["behavior"],
            state["ctx"],
        )
        state["trace"].record("plan", tool=tool, params=params)
        return {"tool": tool, "params": params}

    def _after_plan(self, state: GraphState) -> str:
        return "act" if state.get("tool") else "confirm"

    def _act(self, state: GraphState) -> Dict[str, Any]:
        tool = state["tool"]
        params = state["params"]
        ctx = state["ctx"]
        trace = state["trace"]
        decision = state["decision"]

        fences = state["tools"].check(tool, params, ctx)
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
            return {
                "fences": fence_dicts,
                "output": self.core._fence_message(fences),
                "route": "REJECT",
                "status": "REJECTED",
                "actions": [
                    {"tool": tool, "executed": False, "fence_checks": fence_dicts}
                ],
            }

        if decision.action == "CONFIRM" and any(not f.passed for f in fences):
            trace.record(
                "act",
                tool=tool,
                params=params,
                fence_checks=fence_dicts,
                executed=False,
            )
            trace.record(
                "confirm", status="WAITING", reason="confirmation token missing"
            )
            return {
                "fences": fence_dicts,
                "output": "该操作需要人工确认。",
                "route": "CONFIRM",
                "status": "WAITING_CONFIRM",
                "actions": [
                    {"tool": tool, "executed": False, "fence_checks": fence_dicts}
                ],
            }

        tool_result = state["tools"].execute(tool, params, ctx)
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
            return {
                "fences": fence_dicts,
                "output": f"工具执行失败：{tool_result.error}",
                "route": decision.action,
                "status": "FAILED",
                "actions": [{"tool": tool, "executed": True, "ok": False}],
            }

        return {
            "fences": fence_dicts,
            "output": "",
            "route": decision.action,
        }

    def _after_act(self, state: GraphState) -> str:
        status = state.get("status")
        if status == "REJECTED":
            return "respond"
        if status == "FAILED":
            return "respond"
        if status == "WAITING_CONFIRM":
            return "end"
        return "verify"

    def _verify(self, state: GraphState) -> Dict[str, Any]:
        case = state["case"]
        kept = state["kept"]
        behavior = state["behavior"]
        trace = state["trace"]

        if behavior == "B4":
            output = (
                f"已执行（Mock）：{state['tool']}。"
                f"参数：{json.dumps(state['params'], ensure_ascii=False)}"
            )
            source_cited = True
        else:
            output = None
            if behavior == "B2" and self.core.summarizer is not None:
                try:
                    llm_output = self.core.summarizer.summarize(
                        case.trigger_query, kept
                    )
                except Exception:  # noqa: BLE001
                    llm_output = None
                if llm_output and any(m.message_id in llm_output for m in kept):
                    output = llm_output
            if output is None:
                output = self.core._summarize(case, kept, behavior)
            source_cited = all(m.message_id in output for m in kept)

        trace.record("verify", passed=True, source_cited=source_cited)
        return {
            "output": output,
            "route": state["decision"].action,
            "status": "DONE",
        }

    def _respond(self, state: GraphState) -> Dict[str, Any]:
        output = state.get("output", "")
        state["trace"].record("respond", output=output)
        return {"output": output}

    def _reject(self, state: GraphState) -> Dict[str, Any]:
        state["trace"].record("reject", reason="out of scope")
        return {
            "output": "该操作超出能力边界，已拒绝并建议转交人工。",
            "route": "REJECT",
            "status": "REJECTED",
        }

    def _ask(self, state: GraphState) -> Dict[str, Any]:
        state["trace"].record("ask", reason="insufficient information")
        return {
            "output": "请补充任务对象、时间范围或判断依据。",
            "route": "ASK",
            "status": "DONE",
        }

    def _confirm(self, state: GraphState) -> Dict[str, Any]:
        decision = state["decision"]
        ctx = state["ctx"]
        trace = state["trace"]

        if decision.action == "CONFIRM" and ctx.get("confirmation_token"):
            trace.record("confirm", status="APPROVED")
            output = "结论已确认（Mock）。"
            trace.record("respond", output=output)
            return {"output": output, "route": "CONFIRM", "status": "DONE"}

        trace.record("confirm", status="REQUIRED", reason=decision.reason)
        return {
            "output": "该任务需要人工确认结论。",
            "route": "CONFIRM",
            "status": "WAITING_CONFIRM",
        }
