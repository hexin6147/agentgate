import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.evaluation import aggregate, compare_reports, evaluate, score_case
from agentgate.harness import Harness
from agentgate.schema import validate_case
from agentgate.tools import ToolRegistry
from samples.rd_collab.adapter import RuleBasedAgent


def load_case(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return validate_case(json.load(f))


def run(rel, ctx):
    case = load_case(rel)
    result = Harness(ToolRegistry()).run_case(RuleBasedAgent(), case, ctx)
    return case, result


class TestScoreCase(unittest.TestCase):
    def test_normal_case_scores(self):
        case, result = run(
            "eval/dataset/golden/sample_rd_001.json", {"project_id": "pay"}
        )
        score = score_case(case, result)

        self.assertTrue(score["behavior_correct"])
        self.assertTrue(score["route_correct"])
        self.assertAlmostEqual(score["context_recall"], 1.0)
        self.assertAlmostEqual(score["source_citation"], 1.0)
        self.assertTrue(score["trace_complete"])
        self.assertTrue(score["passed"])

    def test_adversarial_case_scores(self):
        case, result = run(
            "eval/dataset/adversarial/sample_adv_001.json",
            {"project_id": "pay", "incident_leveled": False},
        )
        score = score_case(case, result)

        self.assertTrue(score["behavior_correct"])
        self.assertTrue(score["route_correct"])
        self.assertFalse(score["fence_violation"])
        self.assertIsNone(score["source_citation"])
        self.assertTrue(score["passed"])

    def test_ci_source_citation_not_applicable(self):
        case, result = run(
            "eval/dataset/golden/gen_normal_ci_000.json", {"project_id": "pay"}
        )
        score = score_case(case, result)
        self.assertIsNone(score["source_citation"])


class TestAggregateAndCompare(unittest.TestCase):
    def test_evaluate_dataset(self):
        report = evaluate(
            RuleBasedAgent(),
            ToolRegistry(),
            os.path.join(ROOT, "eval/dataset"),
            {"project_id": "pay"},
        )
        metrics = report["metrics"]
        self.assertGreaterEqual(metrics["cases"], 80)
        self.assertGreaterEqual(metrics["passed"], 1)
        self.assertAlmostEqual(metrics["trace_completeness"], 1.0)
        self.assertIn("hard_gate_passed", metrics)
        self.assertIsInstance(metrics["hard_gate_passed"], bool)
        self.assertIn("failed_cases", report)

    def test_compare_reports_detects_new_failure(self):
        base = {
            "metrics": {"pass_rate": 1.0},
            "case_results": [{"case_id": "c1", "passed": True}],
        }
        target = {
            "metrics": {"pass_rate": 0.5},
            "case_results": [{"case_id": "c1", "passed": False}],
        }
        diff = compare_reports(base, target)
        self.assertEqual(diff["new_failures"], ["c1"])
        self.assertAlmostEqual(diff["metric_diff"]["pass_rate"], -0.5)


if __name__ == "__main__":
    unittest.main()
