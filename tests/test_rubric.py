import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.evaluation import evaluate
from agentgate.factory import build_agent
from agentgate.rubric import (
    Rubric,
    RubricDimension,
    RubricValidationError,
    load_rubric,
    score_rubric,
    validate_rubric,
)
from agentgate.tools import ToolRegistry

COLLAB = os.path.join(ROOT, "eval/rubrics/collab_v1.yaml")
RESTRICTED = os.path.join(ROOT, "eval/rubrics/restricted_v1.yaml")


class TestLoadRubric(unittest.TestCase):
    def test_load_collab(self):
        rubric = load_rubric(COLLAB)
        self.assertEqual(rubric.rubric_id, "collab_v1")
        self.assertAlmostEqual(sum(d.weight for d in rubric.dimensions), 1.0)
        self.assertTrue(any(d.judge_type == "hard_rule" for d in rubric.dimensions))

    def test_load_restricted(self):
        rubric = load_rubric(RESTRICTED)
        self.assertEqual(rubric.rubric_id, "restricted_v1")
        self.assertAlmostEqual(sum(d.weight for d in rubric.dimensions), 1.0)


class TestValidateRubric(unittest.TestCase):
    def make(self, dimensions, threshold=0.8):
        return Rubric(
            rubric_id="test",
            paradigm="collab",
            pass_threshold=threshold,
            dimensions=dimensions,
        )

    def test_weight_sum_must_be_one(self):
        rubric = self.make(
            [
                RubricDimension(
                    name="a", weight=0.5, judge_type="hard_rule",
                    metric="fence_interception",
                ),
                RubricDimension(
                    name="b", weight=0.4, judge_type="hard_rule",
                    metric="behavior_accuracy",
                ),
            ]
        )
        with self.assertRaises(RubricValidationError):
            validate_rubric(rubric)

    def test_requires_hard_rule(self):
        rubric = self.make(
            [
                RubricDimension(
                    name="a", weight=1.0, judge_type="human_review",
                    metric="handoff_accuracy",
                )
            ]
        )
        with self.assertRaises(RubricValidationError):
            validate_rubric(rubric)

    def test_threshold_range(self):
        rubric = self.make(
            [
                RubricDimension(
                    name="a", weight=1.0, judge_type="hard_rule",
                    metric="fence_interception",
                )
            ],
            threshold=1.5,
        )
        with self.assertRaises(RubricValidationError):
            validate_rubric(rubric)


class TestScoreRubric(unittest.TestCase):
    def setUp(self):
        self.rubric = load_rubric(COLLAB)
        self.metrics = {
            "fence_interception": 1.0,
            "false_block_rate": 0.0,
            "behavior_accuracy": 1.0,
            "route_accuracy": 1.0,
            "context_recall": 1.0,
            "context_drift": 0.0,
            "handoff_accuracy": 1.0,
            "factuality": 1.0,
            "source_citation": 1.0,
        }

    def test_perfect_score(self):
        result = score_rubric(self.rubric, self.metrics)
        self.assertAlmostEqual(result.weighted_score, 1.0)
        self.assertTrue(result.gate_passed)
        self.assertTrue(result.passed)

    def test_gate_failure_blocks_even_with_high_score(self):
        metrics = dict(self.metrics)
        metrics["fence_interception"] = 0.5
        result = score_rubric(self.rubric, metrics)
        self.assertFalse(result.gate_passed)
        self.assertFalse(result.passed)

    def test_lower_is_better(self):
        metrics = dict(self.metrics)
        metrics["false_block_rate"] = 0.05  # target 0.10 -> normalised 0.5
        result = score_rubric(self.rubric, metrics)
        dim = next(d for d in result.dimensions if d.metric == "false_block_rate")
        self.assertAlmostEqual(dim.score, 0.5)

    def test_missing_metric_is_skipped_and_renormalised(self):
        metrics = dict(self.metrics)
        metrics.pop("factuality")
        metrics.pop("handoff_accuracy")
        result = score_rubric(self.rubric, metrics)
        self.assertIn("factuality", result.missing_metrics)
        self.assertIn("handoff_accuracy", result.missing_metrics)
        self.assertAlmostEqual(result.weighted_score, 1.0)

    def test_intent_metric_alias(self):
        restricted = load_rubric(RESTRICTED)
        metrics = {
            "fence_interception": 1.0,
            "false_block_rate": 0.0,
            "intent_accuracy": 1.0,
            "behavior_accuracy": 1.0,
            "handoff_accuracy": 1.0,
            "factuality": 1.0,
        }
        result = score_rubric(restricted, metrics)
        self.assertIn("answer_correctness", result.missing_metrics)
        self.assertTrue(result.passed)


class TestEvaluateWithRubric(unittest.TestCase):
    def test_evaluate_attaches_rubric_result(self):
        rubric = load_rubric(COLLAB)
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(
                os.path.join(ROOT, "eval/dataset/golden/sample_rd_001.json"),
                os.path.join(tmp, "case.json"),
            )
            report = evaluate(
                build_agent("rule"),
                ToolRegistry(),
                tmp,
                {"project_id": "pay"},
                rubric=rubric,
            )
        self.assertIn("rubric", report)
        self.assertEqual(report["rubric"]["rubric_id"], "collab_v1")
        self.assertGreaterEqual(report["rubric"]["weighted_score"], 0.99)
        self.assertTrue(report["rubric"]["passed"])


if __name__ == "__main__":
    unittest.main()
