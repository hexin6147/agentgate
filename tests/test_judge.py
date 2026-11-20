import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.evaluation import aggregate, score_case
from agentgate.harness import Harness
from agentgate.judge import JudgeResult, LLMJudge
from agentgate.schema import validate_case
from agentgate.tools import ToolRegistry
from samples.rd_collab.adapter import RuleBasedAgent


def load_case(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return validate_case(json.load(f))


def run_case(rel, ctx=None):
    case = load_case(rel)
    result = Harness(ToolRegistry()).run_case(
        RuleBasedAgent(), case, ctx or {"project_id": "pay"}
    )
    return case, result


def judge_json(**overrides):
    data = {
        "factuality": 0.9,
        "source_support": 0.8,
        "handoff_correct": True,
        "violations": [],
        "reason": "ok",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


class FakeJudge:
    def __init__(self, factuality=0.9, handoff_correct=True):
        self.factuality = factuality
        self.handoff_correct = handoff_correct

    def judge(self, case, result):
        return JudgeResult(
            ok=True,
            factuality=self.factuality,
            source_support=0.8,
            handoff_correct=self.handoff_correct,
            reason="fake",
        )


class TestLLMJudge(unittest.TestCase):
    def test_valid_json(self):
        judge = LLMJudge(lambda system, user: judge_json())
        case, result = run_case("eval/dataset/golden/sample_rd_001.json")
        outcome = judge.judge(case, result)
        self.assertTrue(outcome.ok)
        self.assertAlmostEqual(outcome.factuality, 0.9)
        self.assertAlmostEqual(outcome.source_support, 0.8)
        self.assertTrue(outcome.handoff_correct)

    def test_code_fence(self):
        judge = LLMJudge(
            lambda system, user: "```json\n" + judge_json() + "\n```"
        )
        case, result = run_case("eval/dataset/golden/sample_rd_001.json")
        self.assertTrue(judge.judge(case, result).ok)

    def test_invalid_json_returns_not_ok(self):
        judge = LLMJudge(lambda system, user: "not json")
        case, result = run_case("eval/dataset/golden/sample_rd_001.json")
        outcome = judge.judge(case, result)
        self.assertFalse(outcome.ok)
        self.assertIsNone(outcome.factuality)

    def test_exception_returns_not_ok(self):
        def boom(system, user):
            raise RuntimeError("judge down")

        judge = LLMJudge(boom)
        case, result = run_case("eval/dataset/golden/sample_rd_001.json")
        outcome = judge.judge(case, result)
        self.assertFalse(outcome.ok)

    def test_null_for_no_claims(self):
        judge = LLMJudge(
            lambda system, user: judge_json(factuality=None, source_support=None)
        )
        case, result = run_case("eval/dataset/golden/sample_rd_001.json")
        outcome = judge.judge(case, result)
        self.assertIsNone(outcome.factuality)
        self.assertIsNone(outcome.source_support)

    def test_prompt_contains_sources_and_output(self):
        captured = {}

        def capture(system, user):
            captured["system"] = system
            captured["user"] = user
            return judge_json()

        judge = LLMJudge(capture)
        case, result = run_case("eval/dataset/golden/sample_rd_001.json")
        judge.judge(case, result)
        self.assertIn("[m1]", captured["user"])
        self.assertIn("Agent 输出", captured["user"])


class TestScoreCaseWithJudge(unittest.TestCase):
    def test_judge_runs_for_llm_judge_case(self):
        case, result = run_case("eval/dataset/golden/sample_rd_001.json")
        score = score_case(case, result, judge=FakeJudge())
        self.assertAlmostEqual(score["factuality"], 0.9)
        # B2 is a pure summary: handoff is not applicable.
        self.assertIsNone(score["handoff_correct"])
        self.assertTrue(score["judge_ok"])

    def test_judge_skipped_for_hard_rule_case(self):
        case, result = run_case(
            "eval/dataset/adversarial/sample_adv_001.json",
            {"project_id": "pay", "incident_leveled": False},
        )
        score = score_case(case, result, judge=FakeJudge())
        self.assertIsNone(score["factuality"])
        self.assertIsNone(score["handoff_correct"])

    def test_judge_runs_for_human_review_case(self):
        case, result = run_case(
            "eval/dataset/boundary/gen_boundary_decision_000.json"
        )
        score = score_case(case, result, judge=FakeJudge())
        self.assertAlmostEqual(score["factuality"], 0.9)
        self.assertTrue(score["handoff_correct"])
        self.assertTrue(score["judge_ok"])

    def test_aggregate_judge_metrics(self):
        normal_case, normal_result = run_case(
            "eval/dataset/golden/sample_rd_001.json"
        )
        decision_case, decision_result = run_case(
            "eval/dataset/boundary/gen_boundary_decision_000.json"
        )
        scores = [
            score_case(normal_case, normal_result, judge=FakeJudge()),
            score_case(decision_case, decision_result, judge=FakeJudge()),
        ]
        metrics = aggregate(scores)["metrics"]
        self.assertAlmostEqual(metrics["factuality"], 0.9)
        self.assertAlmostEqual(metrics["handoff_accuracy"], 1.0)
        self.assertAlmostEqual(metrics["judge_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
