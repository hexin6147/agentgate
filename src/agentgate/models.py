"""Core data models for AgentGate (pydantic v2)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

BEHAVIORS = ("B1", "B2", "B3", "B4", "B5", "B6")
ROUTES = ("AUTO", "CONFIRM", "ASK", "REJECT", "TRANSFER")
LABELS = ("normal", "boundary", "adversarial")
JUDGE_TYPES = ("hard_rule", "human_review", "llm_judge")
DIFFICULTIES = ("easy", "medium", "hard")


class Message(BaseModel):
    message_id: str
    user: str
    ts: str
    msg: str


class Topic(BaseModel):
    topic_id: str
    message_ids: List[str]
    label: str


class IntentSpec(BaseModel):
    id: str
    name: str
    behavior: str
    examples: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    tool: Optional[str] = None


class AgentMetadata(BaseModel):
    name: str
    version: str
    paradigm: str
    description: str = ""
    capabilities: List[str] = Field(default_factory=list)
    intents: List[IntentSpec] = Field(default_factory=list)


class Case(BaseModel):
    case_id: str
    agent_id: str
    label: str
    scene: str
    raw_chat_history: List[Message]
    trigger_query: str
    available_tools: List[str]
    expected_intent: str
    expected_behavior: str
    expected_route: str
    golden_expected_behavior: List[str]
    forbidden_behavior: List[str]
    judge_type: str
    source: Dict[str, Any]
    topics: List[Topic] = Field(default_factory=list)
    relevant_message_ids: List[str] = Field(default_factory=list)
    difficulty: str = "medium"
    notes: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)


class RuleDecision(BaseModel):
    rule_id: str
    action: str          # AUTO / CONFIRM / ASK / REJECT
    risk: str            # low / medium / high
    reason: str


class FenceResult(BaseModel):
    fence_id: str
    passed: bool
    reason: str


class ToolResult(BaseModel):
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class AgentResult(BaseModel):
    output: str
    route: str
    state: str = "DONE"
    actions: List[Dict[str, Any]] = Field(default_factory=list)


class RunResult(BaseModel):
    run_id: str
    case_id: str
    status: str
    route: str
    output: str
    trace: Dict[str, Any]
    error: Optional[str] = None
