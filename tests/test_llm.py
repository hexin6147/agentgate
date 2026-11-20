import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.intents import IntentRegistry
from agentgate.llm import (
    HybridClassifier,
    LLMIntentClassifier,
    LLMSummarizer,
    parse_json_object,
)
from agentgate.models import IntentSpec, Message

INTENTS = [
    IntentSpec(
        id="rd_risk_digest",
        name="汇总上线风险",
        behavior="B2",
        examples=["汇总本次版本上线的风险"],
        keywords=["汇总", "风险"],
    ),
    IntentSpec(
        id="rd_ci_query",
        name="查询 CI 状态",
        behavior="B1",
        examples=["查一下 CI"],
        keywords=["CI", "构建"],
    ),
    IntentSpec(
        id="rd_request_review",
        name="发起变更评审",
        behavior="B4",
        examples=["发起评审"],
        keywords=["评审", "变更"],
    ),
    IntentSpec(
        id="rd_go_live_decision",
        name="判断能否上线",
        behavior="B3",
        examples=["这次能不能上线"],
        keywords=["能不能上线", "上线结论"],
    ),
    IntentSpec(
        id="rd_out_of_scope",
        name="审批/发布/资金",
        behavior="B5",
        examples=["直接上线"],
        keywords=["直接上线", "批准", "批一下"],
    ),
]


def fake_chat(payload):
    return lambda system, user: payload


class TestParse(unittest.TestCase):
    def test_parses_plain_json(self):
        self.assertEqual(
            parse_json_object('{"intent_id":"x","confidence":0.9}'),
            {"intent_id": "x", "confidence": 0.9},
        )

    def test_parses_code_fence(self):
        text = '```json\n{"intent_id":"x"}\n```'
        self.assertEqual(parse_json_object(text), {"intent_id": "x"})

    def test_invalid_returns_none(self):
        self.assertIsNone(parse_json_object("not json"))


class TestLLMIntentClassifier(unittest.TestCase):
    def test_valid_intent(self):
        classifier = LLMIntentClassifier(
            fake_chat('{"intent_id":"rd_go_live_decision","confidence":0.9,"evidence":"x"}'),
            INTENTS,
        )
        match = classifier.match("这版能不能发")
        self.assertIsNotNone(match)
        self.assertEqual(match.intent_id, "rd_go_live_decision")
        self.assertEqual(match.behavior, "B3")

    def test_invalid_intent_returns_none(self):
        classifier = LLMIntentClassifier(
            fake_chat('{"intent_id":"nope","confidence":0.9}'), INTENTS
        )
        self.assertIsNone(classifier.match("x"))

    def test_low_confidence_returns_none(self):
        classifier = LLMIntentClassifier(
            fake_chat('{"intent_id":"rd_go_live_decision","confidence":0.2}'),
            INTENTS,
        )
        self.assertIsNone(classifier.match("x"))

    def test_exception_returns_none(self):
        def boom(system, user):
            raise RuntimeError("network down")

        classifier = LLMIntentClassifier(boom, INTENTS)
        self.assertIsNone(classifier.match("x"))

    def test_vague_query_guard(self):
        classifier = LLMIntentClassifier(
            fake_chat('{"intent_id":"rd_risk_digest","confidence":0.9}'), INTENTS
        )
        self.assertIsNone(classifier.match("把那个问题处理一下"))
        self.assertIsNone(classifier.match("这个怎么处理"))

    def test_write_action_guard_overrides_decision(self):
        classifier = LLMIntentClassifier(
            fake_chat('{"intent_id":"rd_go_live_decision","confidence":0.9}'),
            INTENTS,
        )
        match = classifier.match("把这个改动提上去")
        self.assertEqual(match.intent_id, "rd_request_review")
        self.assertEqual(match.behavior, "B4")

    def test_summary_guard_overrides_decision(self):
        classifier = LLMIntentClassifier(
            fake_chat('{"intent_id":"rd_go_live_decision","confidence":0.9}'),
            INTENTS,
        )
        match = classifier.match("这次改动的隐患有哪些")
        self.assertEqual(match.intent_id, "rd_risk_digest")
        self.assertEqual(match.behavior, "B2")

    def test_decision_phrase_not_overridden(self):
        classifier = LLMIntentClassifier(
            fake_chat('{"intent_id":"rd_go_live_decision","confidence":0.9}'),
            INTENTS,
        )
        match = classifier.match("给个上线结论")
        self.assertEqual(match.intent_id, "rd_go_live_decision")
        self.assertEqual(match.behavior, "B3")


class TestHybridClassifier(unittest.TestCase):
    def test_falls_back_to_rules(self):
        llm = LLMIntentClassifier(
            fake_chat('{"intent_id":"nope","confidence":0.9}'), INTENTS
        )
        hybrid = HybridClassifier(llm, IntentRegistry(INTENTS))
        match = hybrid.match("汇总本次版本上线的风险")
        self.assertIsNotNone(match)
        self.assertEqual(match.intent_id, "rd_risk_digest")

    def test_llm_wins_when_valid(self):
        llm = LLMIntentClassifier(
            fake_chat('{"intent_id":"rd_ci_query","confidence":0.9}'), INTENTS
        )
        hybrid = HybridClassifier(llm, IntentRegistry(INTENTS))
        match = hybrid.match("看一下编译结果")
        self.assertEqual(match.intent_id, "rd_ci_query")


class TestLLMSummarizer(unittest.TestCase):
    def test_returns_text(self):
        summarizer = LLMSummarizer(lambda system, user: "风险：[m2] 数据库迁移")
        out = summarizer.summarize(
            "汇总风险",
            [Message(message_id="m2", user="用户B", ts="t", msg="数据库迁移有风险")],
        )
        self.assertIn("[m2]", out)

    def test_failure_returns_none(self):
        def boom(system, user):
            raise RuntimeError("network down")

        summarizer = LLMSummarizer(boom)
        self.assertIsNone(
            summarizer.summarize(
                "汇总风险",
                [Message(message_id="m2", user="用户B", ts="t", msg="风险")],
            )
        )


if __name__ == "__main__":
    unittest.main()
