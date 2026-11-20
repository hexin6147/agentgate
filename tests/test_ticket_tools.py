import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from samples.ticket.tools import TicketToolRegistry


def submit_params(amount=100):
    return {
        "order_id": "ORD-1001",
        "ticket_type": "refund",
        "description": "申请退款",
        "refund_amount": amount,
    }


class TestTicketFences(unittest.TestCase):
    def setUp(self):
        self.tools = TicketToolRegistry()

    def test_t1_blocks_unverified_order_query(self):
        results = self.tools.check(
            "query_order", {"order_id": "ORD-1001"}, {"identity_verified": False}
        )
        failed = [r.fence_id for r in results if not r.passed]
        self.assertIn("T1", failed)

    def test_t1_passes_when_verified(self):
        results = self.tools.check(
            "query_order",
            {"order_id": "ORD-1001"},
            {"identity_verified": True},
        )
        self.assertTrue(all(r.passed for r in results))

    def test_t2_blocks_over_limit_refund(self):
        results = self.tools.check(
            "submit_ticket",
            submit_params(300),
            {
                "identity_verified": True,
                "refund_limit": 200,
                "confirmation_token": "tok-1",
            },
        )
        failed = [r.fence_id for r in results if not r.passed]
        self.assertIn("T2", failed)

    def test_t2_passes_within_limit(self):
        results = self.tools.check(
            "submit_ticket",
            submit_params(100),
            {
                "identity_verified": True,
                "refund_limit": 200,
                "confirmation_token": "tok-1",
            },
        )
        self.assertTrue(all(r.passed for r in results))

    def test_t5_blocks_cross_user_query(self):
        results = self.tools.check(
            "query_order",
            {"order_id": "ORD-1001", "user_id": "U2"},
            {"identity_verified": True, "user_id": "U1"},
        )
        failed = [r.fence_id for r in results if not r.passed]
        self.assertIn("T5", failed)

    def test_f5_requires_order_id(self):
        results = self.tools.check(
            "query_order", {}, {"identity_verified": True}
        )
        failed = [r.fence_id for r in results if not r.passed]
        self.assertIn("F5", failed)


class TestTicketExecution(unittest.TestCase):
    def test_execute_is_deterministic(self):
        tools = TicketToolRegistry()
        first = tools.execute("query_order", {"order_id": "ORD-1001"}, {})
        second = tools.execute("query_order", {"order_id": "ORD-1001"}, {})
        self.assertEqual(first, second)
        self.assertTrue(first.ok)


if __name__ == "__main__":
    unittest.main()
