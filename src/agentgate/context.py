"""Semantic context filtering with embeddings (BGE via OpenAI-compatible API)."""
from __future__ import annotations

import math
import os
from typing import Callable, List, Optional, Sequence, Tuple

from .models import Message


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


class SemanticContextFilter:
    def __init__(
        self,
        embed_fn: Callable[[List[str]], List[List[float]]],
        top_k: int = 5,
        threshold: float = 0.35,
        fallback: Optional[Callable[[str, List[Message]], Tuple[List[Message], List[str]]]] = None,
    ):
        self.embed_fn = embed_fn
        self.top_k = top_k
        self.threshold = threshold
        self.fallback = fallback

    def filter(
        self, query: str, messages: List[Message]
    ) -> Tuple[List[Message], List[str]]:
        if not messages:
            return [], []

        try:
            vectors = self.embed_fn([query] + [m.msg for m in messages])
        except Exception:  # noqa: BLE001 - fallback is intentional
            return self._fallback(query, messages)

        if not vectors or len(vectors) != len(messages) + 1:
            return self._fallback(query, messages)

        query_vec = vectors[0]
        scored = [
            (cosine(query_vec, vector), message)
            for vector, message in zip(vectors[1:], messages)
        ]
        selected = [(score, message) for score, message in scored if score >= self.threshold]
        if not selected:
            # Conservative: never drop everything.
            return list(messages), []

        selected.sort(key=lambda item: item[0], reverse=True)
        selected = selected[: self.top_k]
        keep_ids = {message.message_id for _, message in selected}
        kept = [m for m in messages if m.message_id in keep_ids]
        dropped = [m.message_id for m in messages if m.message_id not in keep_ids]
        return kept, dropped

    def _fallback(
        self, query: str, messages: List[Message]
    ) -> Tuple[List[Message], List[str]]:
        if self.fallback is not None:
            return self.fallback(query, messages)
        return list(messages), []


class EmbeddingClient:
    """OpenAI-compatible embeddings client (Ollama BGE by default)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        from openai import OpenAI

        self.model = model or os.getenv(
            "EMBEDDING_MODEL", "quentinz/bge-base-zh-v1.5:latest"
        )
        self.client = OpenAI(
            base_url=base_url
            or os.getenv("EMBEDDING_BASE_URL", "http://127.0.0.1:11434/v1"),
            api_key=api_key or os.getenv("LLM_API_KEY", "ollama"),
            timeout=timeout or float(os.getenv("EMBEDDING_TIMEOUT", "60")),
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        response = self.client.embeddings.create(model=self.model, input=list(texts))
        return [item.embedding for item in response.data]
