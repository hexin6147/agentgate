import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.harness import Harness
from agentgate.schema import validate_case
from agentgate.tools import ToolRegistry
from samples.rd_collab.adapter import RuleBasedAgent


def load_case(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return validate_case(json.load(f))


class TestHarness(unittest.TestCase):
    def setUp(self):
        self.tools = ToolRegistry()
        self.agent = RuleBasedAgent()
        self.harness = Harness(self.tools)

    def test_normal_case_end_to_end(self):
        case = load_case("eval/dataset/golden/sample_rd_001.json")
        result = self.harness.run_case(self.agent, case, {"project_id": "pay"})

        self.assertEqual(result.status, "DONE")
        self.assertEqual(result.route, "AUTO")
        self.assertIn("数据库迁移", result.output)

        nodes = [s["node"] for s in result.trace["steps"]]
        for node in ("route", "filter", "plan", "act", "verify", "respond"):
            self.assertIn(node, nodes)

        act = [s for s in result.trace["steps"] if s["node"] == "act"][0]
        self.assertTrue(act["executed"])

    def test_adversarial_case_blocks_tool(self):
        case = load_case("eval/dataset/adversarial/sample_adv_001.json")
        result = self.harness.run_case(
            self.agent,
            case,
            {"project_id": "pay", "incident_leveled": False},
        )

        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.route, "REJECT")
        self.assertNotIn("request_review", result.output)

        act = [s for s in result.trace["steps"] if s["node"] == "act"][0]
        self.assertFalse(act["executed"])
        fence_ids = [f["fence_id"] for f in act["fence_checks"]]
        self.assertIn("F1", fence_ids)

    def test_review_executes_with_confirmation(self):
        case = load_case("eval/dataset/adversarial/sample_adv_001.json")
        result = self.harness.run_case(
            self.agent,
            case,
            {
                "project_id": "pay",
                "incident_leveled": True,
                "confirmation_token": "tok-1",
            },
        )

        self.assertEqual(result.status, "DONE")
        self.assertIn("已执行", result.output)
        act = [s for s in result.trace["steps"] if s["node"] == "act"][0]
        self.assertTrue(act["executed"])


if __name__ == "__main__":
    unittest.main()
