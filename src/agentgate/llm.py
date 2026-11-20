"""LLM helpers: intent classification and risk summarization.

LLM is the primary classifier; the rule registry is the fallback.  Safety
decisions (allow / confirm / reject) still live in `rules.py` and `tools.py`.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

from .intents import IntentMatch
from .logging import classify_error, current_span_id, log_event, set_span
from .models import IntentSpec, Message
from .trace import current_recorder
from .usage import record_usage

VAGUE_PATTERNS = (
    "那个问题",
    "处理一下",
    "看一下这个",
    "跟进一下",
    "你看着办",
    "帮忙处理下",
    "这个你来跟进",
    "后续怎么安排",
    "怎么处理",
)

WRITE_ACTION_PATTERNS = (
    "提交",
    "推上去",
    "提上去",
    "走流程",
    "走个流程",
    "发起评审",
    "发起变更",
)

SUMMARY_GUARD_PATTERNS = (
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
)

DECISION_PATTERNS = (
    "能不能上线",
    "上线结论",
    "是否可以上线",
    "定级",
    "结论",
)

INTENT_SYSTEM = (
    "你是意图分类器。只能从给定 intents 中选一个，或返回 unknown。"
    '只输出严格 JSON：{"intent_id":"...","confidence":0.0,"evidence":"..."}'
)

SUMMARY_SYSTEM = (
    "你是研发协作 Agent。只使用给定群聊消息中的事实，逐条列出风险或结论，"
    "并用 [message_id] 标注来源。不要编造消息中不存在的信息。"
    "如果信息不足，请明确说明。"
)


def parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _intents_prompt(intents: List[IntentSpec]) -> str:
    lines = []
    for intent in intents:
        examples = " / ".join(intent.examples)
        lines.append(
            f"- {intent.id} | {intent.name} | behavior {intent.behavior} | 例: {examples}"
        )
    return "\n".join(lines)


class LLMIntentClassifier:
    def __init__(
        self,
        chat_fn: Callable[[str, str], str],
        intents: List[IntentSpec],
        min_confidence: float = 0.6,
    ):
        self.chat_fn = chat_fn
        self.intents = list(intents)
        self.by_id = {intent.id: intent for intent in self.intents}
        self.min_confidence = min_confidence

    def _intent_for(self, behavior: str) -> Optional[IntentSpec]:
        return next(
            (intent for intent in self.intents if intent.behavior == behavior),
            None,
        )

    def match(self, query: str) -> Optional[IntentMatch]:
        if not query or any(pattern in query for pattern in VAGUE_PATTERNS):
            return None

        user = _intents_prompt(self.intents) + "\n\nquery: " + query
        recorder = current_recorder()
        phase_span = (
            recorder.start_span("classify", kind="phase")
            if recorder is not None
            else None
        )
        try:
            text = self.chat_fn(INTENT_SYSTEM, user)
        except Exception as exc:  # noqa: BLE001 - fallback is the point
            if recorder is not None and phase_span is not None:
                recorder.end_span(
                    phase_span,
                    status="error",
                    error_type=classify_error(exc),
                )
            return None
        if recorder is not None and phase_span is not None:
            recorder.end_span(phase_span, status="ok")

        data = parse_json_object(text)
        if not data:
            return None

        intent = self.by_id.get(str(data.get("intent_id", "")))
        if intent is None:
            return None

        try:
            confidence = float(data.get("confidence", 0))
        except (TypeError, ValueError):
            return None
        if confidence < self.min_confidence:
            return None

        # Deterministic safety/consistency guards.  The LLM is primary; these
        # only correct well-known, high-risk semantic slips.
        if any(p in query for p in WRITE_ACTION_PATTERNS) and intent.behavior not in (
            "B4",
            "B5",
        ):
            override = self._intent_for("B4")
            if override is not None:
                intent = override
        elif (
            intent.behavior == "B3"
            and any(p in query for p in SUMMARY_GUARD_PATTERNS)
            and not any(p in query for p in DECISION_PATTERNS)
        ):
            override = self._intent_for("B2")
            if override is not None:
                intent = override

        return IntentMatch(
            intent_id=intent.id,
            behavior=intent.behavior,
            confidence=confidence,
            matched_phrase=str(data.get("evidence", "llm")),
        )


class HybridClassifier:
    """LLM first, rule registry as fallback."""

    def __init__(self, llm: LLMIntentClassifier, rules: Any):
        self.llm = llm
        self.rules = rules

    def match(self, query: str) -> Optional[IntentMatch]:
        match = self.llm.match(query)
        if match is not None:
            return match
        return self.rules.match(query)


class LLMSummarizer:
    def __init__(self, chat_fn: Callable[[str, str], str]):
        self.chat_fn = chat_fn

    def summarize(self, query: str, messages: List[Message]) -> Optional[str]:
        lines = [f"[{m.message_id}] {m.user}: {m.msg}" for m in messages]
        user = f"任务: {query}\n\n群聊消息:\n" + "\n".join(lines)
        recorder = current_recorder()
        phase_span = (
            recorder.start_span("summarize", kind="phase")
            if recorder is not None
            else None
        )
        try:
            text = self.chat_fn(SUMMARY_SYSTEM, user)
        except Exception as exc:  # noqa: BLE001
            if recorder is not None and phase_span is not None:
                recorder.end_span(
                    phase_span,
                    status="error",
                    error_type=classify_error(exc),
                )
            return None
        if recorder is not None and phase_span is not None:
            recorder.end_span(phase_span, status="ok")
        text = (text or "").strip()
        return text or None


class LLMClient:
    """OpenAI-compatible client (Ollama / DeepSeek / others)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        from openai import OpenAI

        self.model = model or os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")
        self.client = OpenAI(
            base_url=base_url or os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1"),
            api_key=api_key or os.getenv("LLM_API_KEY", "ollama"),
            timeout=timeout or float(os.getenv("LLM_TIMEOUT", "120")),
        )

    def chat(
        self,
        system: str,
        user: str,
        max_tokens: int = 400,
        temperature: float = 0.0,
    ) -> str:
        recorder = current_recorder()
        previous_span = current_span_id()
        span_id = (
            recorder.start_span(
                f"llm:{self.model}", kind="llm", model=self.model
            )
            if recorder is not None
            else None
        )
        if span_id is not None:
            set_span(span_id)
        log_event("llm_start", model=self.model)

        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - re-raised after recording
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            error_type = classify_error(exc)
            if recorder is not None and span_id is not None:
                recorder.end_span(
                    span_id,
                    status="error",
                    error_type=error_type,
                    latency_ms=latency_ms,
                )
            log_event(
                "llm_error",
                level="error",
                error_type=error_type,
                model=self.model,
                latency_ms=latency_ms,
                msg=str(exc),
            )
            set_span(previous_span)
            raise

        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        record_usage(
            self.model, prompt_tokens, completion_tokens, latency_ms
        )

        if recorder is not None and span_id is not None:
            recorder.end_span(
                span_id,
                status="ok",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
            )
        log_event(
            "llm_end",
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )
        set_span(previous_span)
        return content
