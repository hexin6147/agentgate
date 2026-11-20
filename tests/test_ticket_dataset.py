import glob
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.evaluation import evaluate
from agentgate.factory import build_agent
from agentgate.schema import validate_case
from samples.ticket.tools import TicketToolRegistry


class TestTicketDataset(unittest.TestCase):
    def test_all_cases_validate(self):
        paths = sorted(
            glob.glob(
                os.path.join(ROOT, "eval/dataset_ticket/**/*.json"), recursive=True
            )
        )
        self.assertEqual(len(paths), 24)
        for path in paths:
            with open(path, encoding="utf-8") as f:
                case = validate_case(json.load(f))
            self.assertEqual(case.agent_id, "ticket_agent")
            self.assertTrue(case.context)

    def test_evaluate_sample_b(self):
        report = evaluate(
            build_agent("ticket"),
            TicketToolRegistry(),
            os.path.join(ROOT, "eval/dataset_ticket"),
            {},
        )
        metrics = report["metrics"]
        self.assertEqual(metrics["cases"], 24)
        self.assertEqual(metrics["passed"], 24)
        self.assertAlmostEqual(metrics["fence_interception"], 1.0)
        self.assertAlmostEqual(metrics["false_block_rate"], 0.0)
        self.assertAlmostEqual(metrics["trace_completeness"], 1.0)
        self.assertTrue(metrics["hard_gate_passed"])


if __name__ == "__main__":
    unittest.main()
