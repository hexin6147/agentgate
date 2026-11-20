"""Agent factory: rule baseline or LLM-backed LangGraph agent."""
from __future__ import annotations

from .context import EmbeddingClient, SemanticContextFilter
from .langgraph_agent import LangGraphAgent
from .llm import HybridClassifier, LLMClient, LLMIntentClassifier, LLMSummarizer
from samples.rd_collab.adapter import RuleBasedAgent
from samples.ticket.adapter import RuleBasedTicketAgent


def _build_context_filter(context: str):
    if context == "rule":
        return None
    if context == "bge":
        embedder = EmbeddingClient()
        return SemanticContextFilter(embedder.embed, top_k=5, threshold=0.35)
    raise ValueError(f"unknown context mode: {context}")


def build_agent(kind: str = "rule", context: str = "rule"):
    if kind not in ("rule", "llm", "ticket"):
        raise ValueError(f"unknown agent kind: {kind}")

    if kind == "ticket":
        return LangGraphAgent(RuleBasedTicketAgent())

    context_filter = _build_context_filter(context)
    core = RuleBasedAgent(context_filter=context_filter)

    if kind == "rule":
        return core

    client = LLMClient()
    llm_classifier = LLMIntentClassifier(client.chat, core.intents)
    hybrid = HybridClassifier(llm_classifier, core.registry)
    core = RuleBasedAgent(
        classifier=hybrid,
        summarizer=LLMSummarizer(client.chat),
        context_filter=context_filter,
    )
    return LangGraphAgent(core)
