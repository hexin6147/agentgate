import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.intents import IntentRegistry
from agentgate.models import IntentSpec
from agentgate.rules import decide

INTENTS = [
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
        keywords=["直接上线", "直接放行", "批准", "赔付", "批一下", "帮我发布"],
    ),
]


class TestIntentRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = IntentRegistry(INTENTS)

    def test_matches_summary_intent(self):
        match = self.registry.match("汇总本次版本上线的风险")
        self.assertIsNotNone(match)
        self.assertEqual(match.intent_id, "rd_risk_digest")
        self.assertEqual(match.behavior, "B2")

    def test_matches_ci_intent(self):
        match = self.registry.match("查一下 CI")
        self.assertIsNotNone(match)
        self.assertEqual(match.intent_id, "rd_ci_query")
        self.assertEqual(match.behavior, "B1")

    def test_matches_review_intent(self):
        match = self.registry.match("直接发起变更评审")
        self.assertIsNotNone(match)
        self.assertEqual(match.intent_id, "rd_request_review")
        self.assertEqual(match.behavior, "B4")

    def test_matches_decision_intent(self):
        match = self.registry.match("这次能不能上线")
        self.assertIsNotNone(match)
        self.assertEqual(match.intent_id, "rd_go_live_decision")
        self.assertEqual(match.behavior, "B3")

    def test_unknown_returns_none(self):
        self.assertIsNone(self.registry.match("今天天气怎么样"))


class TestRules(unittest.TestCase):
    def test_b1_auto(self):
        d = decide("B1")
        self.assertEqual((d.rule_id, d.action), ("R1", "AUTO"))

    def test_b2_auto(self):
        d = decide("B2")
        self.assertEqual((d.rule_id, d.action), ("R1", "AUTO"))

    def test_b3_confirm(self):
        d = decide("B3")
        self.assertEqual((d.rule_id, d.action), ("R2", "CONFIRM"))

    def test_b4_confirm(self):
        d = decide("B4")
        self.assertEqual((d.rule_id, d.action), ("R5", "CONFIRM"))

    def test_b5_reject(self):
        d = decide("B5")
        self.assertEqual((d.rule_id, d.action), ("R4", "REJECT"))

    def test_b6_ask(self):
        d = decide("B6")
        self.assertEqual((d.rule_id, d.action), ("R3", "ASK"))


class TestClassifierRegressions(unittest.TestCase):
    """Queries that failed in report_v1."""

    def setUp(self):
        self.registry = IntentRegistry(INTENTS)

    def assert_behavior(self, query, behavior):
        match = self.registry.match(query)
        self.assertIsNotNone(match, f"no match for {query}")
        self.assertEqual(match.behavior, behavior, query)

    def test_summary_paraphrases(self):
        for query in (
            "这次改动的隐患有哪些",
            "发布前需要盯哪些点",
            "这周发布前还有哪些坑",
            "帮我把需要提前处理的事项列出来",
        ):
            self.assert_behavior(query, "B2")

    def test_vague_asks_fall_back_to_none(self):
        for query in ("把那个问题处理一下", "看一下这个", "跟进一下"):
            self.assertIsNone(self.registry.match(query), query)

    def test_decision_phrase_beats_out_of_scope(self):
        self.assert_behavior("给个上线结论", "B3")

    def test_review_paraphrases(self):
        for query in ("这个改动需要走个流程", "帮我把这个改动推上去"):
            self.assert_behavior(query, "B4")

    def test_out_of_scope_paraphrase(self):
        self.assert_behavior("你来批一下", "B5")

    def test_ci_paraphrases(self):
        for query in ("流水线跑完了吗", "打包结果出了吗"):
            self.assert_behavior(query, "B1")


if __name__ == "__main__":
    unittest.main()
