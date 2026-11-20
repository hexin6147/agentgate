import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.harness import Harness
from agentgate.intents import IntentMatch
from agentgate.schema import validate_case
from agentgate.tools import ToolRegistry
from samples.rd_collab.adapter import RuleBasedAgent


def load_case(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return validate_case(json.load(f))


class FakeClassifier:
    def __init__(self, intent_id, behavior):
        self.intent_id = intent_id
        self.behavior = behavior

    def match(self, query):
        return IntentMatch(self.intent_id, self.behavior, 0.9, "fake")


class FakeSummarizer:
    def __init__(self, text):
        self.text = text

    def summarize(self, query, messages):
        return self.text


class TestLLMBackedAgent(unittest.TestCase):
    def run_case(self, agent, ctx=None):
        case = load_case("eval/dataset/golden/sample_rd_001.json")
        return Harness(ToolRegistry()).run_case(agent, case, ctx or {"project_id": "pay"})

    def test_uses_injected_classifier_and_summarizer(self):
        agent = RuleBasedAgent(
            classifier=FakeClassifier("rd_risk_digest", "B2"),
            summarizer=FakeSummarizer("LLM 摘要：[m2] 数据库迁移有风险"),
        )
        result = self.run_case(agent)
        self.assertEqual(result.status, "DONE")
        self.assertIn("LLM 摘要", result.output)

    def test_falls_back_when_summarizer_returns_none(self):
        agent = RuleBasedAgent(
            classifier=FakeClassifier("rd_risk_digest", "B2"),
            summarizer=FakeSummarizer(None),
        )
        result = self.run_case(agent)
        self.assertIn("风险与上下文", result.output)

    def test_falls_back_when_summary_has_no_sources(self):
        agent = RuleBasedAgent(
            classifier=FakeClassifier("rd_risk_digest", "B2"),
            summarizer=FakeSummarizer("数据库迁移有风险"),
        )
        result = self.run_case(agent)
        self.assertIn("[m2]", result.output)

    def test_decision_intent_waits_for_confirmation(self):
        agent = RuleBasedAgent(
            classifier=FakeClassifier("rd_go_live_decision", "B3")
        )
        result = self.run_case(agent)
        self.assertEqual(result.route, "CONFIRM")
        self.assertEqual(result.status, "WAITING_CONFIRM")


if __name__ == "__main__":
    unittest.main()
