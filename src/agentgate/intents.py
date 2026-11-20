"""Business intent registry.

The platform owns the behaviour taxonomy (B1-B6); each Agent owns its intents
and declares which behaviour each intent maps to.

Matching is deliberately simple and deterministic: exact phrase containment
over examples + curated keywords.  We do not use longest-common-substring:
it over-fits common Chinese words such as "一下" and "上线".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .models import IntentSpec

# Tie-break order when two phrases have the same length.
BEHAVIOR_PRIORITY = {"B5": 6, "B4": 5, "B3": 4, "B2": 3, "B1": 2, "B6": 1}


@dataclass
class IntentMatch:
    intent_id: str
    behavior: str
    confidence: float
    matched_phrase: str


def _normalize(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


class IntentRegistry:
    def __init__(self, intents: List[IntentSpec]):
        self.intents = list(intents)

    def match(self, query: str) -> Optional[IntentMatch]:
        q = _normalize(query)
        if not q:
            return None

        best = None  # (score, priority, intent, phrase)
        for intent in self.intents:
            phrases = list(intent.examples) + list(intent.keywords)
            for phrase in phrases:
                p = _normalize(phrase)
                if not p or p not in q:
                    continue
                score = len(p)
                priority = BEHAVIOR_PRIORITY.get(intent.behavior, 0)
                candidate = (score, priority, intent, phrase)
                if best is None or candidate[:2] > best[:2]:
                    best = candidate

        if best is None:
            return None

        score, _, intent, phrase = best
        confidence = min(0.99, 0.6 + 0.04 * score)
        return IntentMatch(
            intent_id=intent.id,
            behavior=intent.behavior,
            confidence=confidence,
            matched_phrase=phrase,
        )
