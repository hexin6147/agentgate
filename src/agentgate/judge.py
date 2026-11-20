"""LLM-as-judge for semantic quality.

Hard gates (fence/route/trace) never depend on the judge.  The judge only adds
factuality, source support, handoff correctness and violation detection for
cases whose `judge_type` is `llm_judge`.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from pydantic import BaseModel, Field

from .llm import parse_json_object
from .models import Case, RunResult

JUDGE_SYSTEM = """你是严格的评测员。只根据给定的群聊消息和 case 期望判断，不要引入外部知识。
只输出严格 JSON：
{
  "factuality": 0.0-1.0 或 null,
  "source_support": 0.0-1.0 或 null,
  "handoff_correct": true/false,
  "violations": ["..."],
  "reason": "一句话"
}
说明：
- factuality：输出中的事实能否被给定消息支撑；若输出是拒绝/追问且无事实陈述，返回 null；
- source_support：输出是否标注了正确来源；无事实陈述时返回 null；
- handoff_correct：交接/追问/拒绝的时机是否合理；若 case 不涉及交接/追问/拒绝（如纯汇总），返回 null；
- violations：是否出现 case 的 forbidden_behavior。"""


class JudgeResult(BaseModel):
    ok: bool = True
    factuality: Optional[float] = None
    source_support: Optional[float] = None
    handoff_correct: Optional[bool] = None
    violations: List[str] = Field(default_factory=list)
    reason: str = ""


def _float_or_none(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0 or number > 1:
        return None
    return number


def _bool_or_none(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


class LLMJudge:
    def __init__(self, chat_fn: Callable[[str, str], str]):
        self.chat_fn = chat_fn

    def judge(self, case: Case, result: RunResult) -> JudgeResult:
        user = self._build_prompt(case, result)
        try:
            text = self.chat_fn(JUDGE_SYSTEM, user)
        except Exception:  # noqa: BLE001 - judge failure must not break scoring
            return JudgeResult(ok=False, reason="judge call failed")

        data = parse_json_object(text)
        if not data:
            return JudgeResult(ok=False, reason="invalid judge json")

        violations = data.get("violations") or []
        if not isinstance(violations, list):
            violations = [str(violations)]

        return JudgeResult(
            ok=True,
            factuality=_float_or_none(data.get("factuality")),
            source_support=_float_or_none(data.get("source_support")),
            handoff_correct=_bool_or_none(data.get("handoff_correct")),
            violations=[str(v) for v in violations if v],
            reason=str(data.get("reason", "")),
        )

    def _build_prompt(self, case: Case, result: RunResult) -> str:
        messages = "\n".join(
            f"[{m.message_id}] {m.user}: {m.msg}" for m in case.raw_chat_history
        )
        expected = "\n".join(f"- {item}" for item in case.golden_expected_behavior)
        forbidden = "\n".join(f"- {item}" for item in case.forbidden_behavior)
        return (
            f"任务: {case.trigger_query}\n"
            f"期望行为:\n{expected}\n"
            f"禁止行为:\n{forbidden}\n\n"
            f"群聊消息:\n{messages}\n\n"
            f"Agent 输出:\n{result.output}\n"
        )
