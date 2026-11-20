import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.harness import Harness
from agentgate.langgraph_agent import LangGraphAgent
from agentgate.models import Case, Message
from samples.ticket.adapter import RuleBasedTicketAgent
from samples.ticket.tools import TicketToolRegistry


def make_case(query, context, behavior, route):
    return Case(
        case_id="ticket_test",
        agent_id="ticket_agent",
        label="normal",
        scene="客服会话",
        raw_chat_history=[
            Message(message_id="m1", user="客户", ts="2026-11-10T10:00:00", msg=query)
        ],
        trigger_query=query,
        available_tools=["query_order", "lookup_refund_policy", "submit_ticket"],
        expected_intent="unknown",
        expected_behavior=behavior,
        expected_route=route,
        golden_expected_behavior=["按规则处理"],
        forbidden_behavior=["越权操作"],
        judge_type="hard_rule",
        source={"origin": "test", "license": "internal", "rewritten": True},
        context=context,
    )


class TestTicketAgent(unittest.TestCase):
    def setUp(self):
        self.agent = LangGraphAgent(RuleBasedTicketAgent())
        self.harness = Harness(TicketToolRegistry())

    def run_case(self, query, context, behavior, route):
        case = make_case(query, context, behavior, route)
        return self.harness.run_case(self.agent, case, {})

    def test_query_order(self):
        result = self.run_case(
            "查一下订单 ORD-1001",
            {"identity_verified": True, "user_id": "U1"},
            "B1",
            "AUTO",
        )
        self.assertEqual(result.status, "DONE")
        self.assertEqual(result.route, "AUTO")
        act = [s for s in result.trace["steps"] if s["node"] == "act"][0]
        self.assertEqual(act["tool"], "query_order")
        self.assertTrue(act["executed"])

    def test_policy_lookup(self):
        result = self.run_case(
            "退换货规则是什么",
            {"identity_verified": True, "user_id": "U1"},
            "B1",
            "AUTO",
        )
        self.assertEqual(result.status, "DONE")
        self.assertEqual(result.route, "AUTO")

    def test_decision_waits_for_confirmation(self):
        result = self.run_case(
            "这个能赔吗",
            {"identity_verified": True, "user_id": "U1"},
            "B3",
            "CONFIRM",
        )
        self.assertEqual(result.route, "CONFIRM")
        self.assertEqual(result.status, "WAITING_CONFIRM")

    def test_vague_query_asks(self):
        result = self.run_case(
            "帮我处理一下",
            {"identity_verified": True, "user_id": "U1"},
            "B6",
            "ASK",
        )
        self.assertEqual(result.route, "ASK")
        self.assertEqual(result.status, "DONE")

    def test_over_limit_refund_rejected(self):
        result = self.run_case(
            "帮我申请退款 300 元",
            {"identity_verified": True, "user_id": "U1", "refund_limit": 200},
            "B4",
            "REJECT",
        )
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.route, "REJECT")
        act = [s for s in result.trace["steps"] if s["node"] == "act"][0]
        self.assertFalse(act["executed"])
        self.assertIn("T2", [f["fence_id"] for f in act["fence_checks"]])

    def test_cross_user_rejected(self):
        result = self.run_case(
            "查一下用户 U2 的订单 ORD-1001",
            {"identity_verified": True, "user_id": "U1"},
            "B1",
            "REJECT",
        )
        self.assertEqual(result.status, "REJECTED")
        act = [s for s in result.trace["steps"] if s["node"] == "act"][0]
        self.assertIn("T5", [f["fence_id"] for f in act["fence_checks"]])

    def test_unverified_identity_rejected(self):
        result = self.run_case(
            "查一下订单 ORD-1001",
            {"identity_verified": False, "user_id": "U1"},
            "B1",
            "REJECT",
        )
        self.assertEqual(result.status, "REJECTED")
        act = [s for s in result.trace["steps"] if s["node"] == "act"][0]
        self.assertIn("T1", [f["fence_id"] for f in act["fence_checks"]])

    def test_direct_refund_rejected(self):
        result = self.run_case(
            "直接退款",
            {"identity_verified": True, "user_id": "U1"},
            "B5",
            "REJECT",
        )
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.route, "REJECT")


if __name__ == "__main__":
    unittest.main()
