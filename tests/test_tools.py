import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.tools import ToolRegistry


def review_params():
    return {
        "project_id": "pay",
        "change_type": "hotfix",
        "summary": "add index",
        "incident_id": "INC-1",
    }


class TestFences(unittest.TestCase):
    def setUp(self):
        self.tools = ToolRegistry()

    def test_f1_blocks_review_when_incident_not_leveled(self):
        results = self.tools.check(
            "request_review", review_params(), {"project_id": "pay", "incident_leveled": False}
        )
        f1 = [r for r in results if r.fence_id == "F1"][0]
        self.assertFalse(f1.passed)

    def test_f2_blocks_high_risk_without_confirmation(self):
        results = self.tools.check(
            "request_review",
            review_params(),
            {"project_id": "pay", "incident_leveled": True},
        )
        f2 = [r for r in results if r.fence_id == "F2"][0]
        self.assertFalse(f2.passed)

    def test_review_passes_with_leveled_and_token(self):
        results = self.tools.check(
            "request_review",
            review_params(),
            {
                "project_id": "pay",
                "incident_leveled": True,
                "confirmation_token": "tok-1",
            },
        )
        self.assertTrue(all(r.passed for r in results))

    def test_f3_blocks_cross_project_search(self):
        results = self.tools.check(
            "search_chat_history",
            {"query": "风险", "project_id": "other"},
            {"project_id": "pay"},
        )
        f3 = [r for r in results if r.fence_id == "F3"][0]
        self.assertFalse(f3.passed)

    def test_f4_blocks_ci_mutation(self):
        results = self.tools.check(
            "query_ci",
            {"pipeline": "build", "action": "deploy"},
            {"project_id": "pay"},
        )
        f4 = [r for r in results if r.fence_id == "F4"][0]
        self.assertFalse(f4.passed)

    def test_f5_blocks_missing_required_fields(self):
        results = self.tools.check(
            "create_issue",
            {"project_id": "pay"},
            {"project_id": "pay", "confirmation_token": "tok-1"},
        )
        f5 = [r for r in results if r.fence_id == "F5"][0]
        self.assertFalse(f5.passed)


class TestExecution(unittest.TestCase):
    def setUp(self):
        self.tools = ToolRegistry()

    def test_execute_is_deterministic(self):
        first = self.tools.execute("query_ci", {"pipeline": "build"}, {})
        second = self.tools.execute("query_ci", {"pipeline": "build"}, {})
        self.assertEqual(first, second)
        self.assertTrue(first.ok)

    def test_fault_injection(self):
        tools = ToolRegistry(faults={"query_ci": "error_500"})
        result = tools.execute("query_ci", {"pipeline": "build"}, {})
        self.assertFalse(result.ok)
        self.assertIn("500", result.error)


if __name__ == "__main__":
    unittest.main()
