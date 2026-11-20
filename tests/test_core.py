import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.schema import validate_case, CaseValidationError
from agentgate.trace import TraceRecorder


class TestCaseSchema(unittest.TestCase):
    def load(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return json.load(f)

    def test_valid_case_loads(self):
        raw = self.load("eval/dataset/golden/sample_rd_001.json")
        case = validate_case(raw)
        self.assertEqual(case.case_id, "rd_normal_001")
        self.assertEqual(case.expected_behavior, "B2")
        self.assertEqual(case.expected_route, "AUTO")

    def test_missing_required_field_raises(self):
        raw = self.load("eval/dataset/golden/sample_rd_001.json")
        del raw["expected_route"]
        with self.assertRaises(CaseValidationError) as ctx:
            validate_case(raw)
        self.assertIn("expected_route", str(ctx.exception))

    def test_invalid_behavior_raises(self):
        raw = self.load("eval/dataset/golden/sample_rd_001.json")
        raw["expected_behavior"] = "B9"
        with self.assertRaises(CaseValidationError):
            validate_case(raw)

    def test_invalid_route_raises(self):
        raw = self.load("eval/dataset/golden/sample_rd_001.json")
        raw["expected_route"] = "DONE"
        with self.assertRaises(CaseValidationError):
            validate_case(raw)

    def test_context_defaults_to_empty(self):
        raw = self.load("eval/dataset/golden/sample_rd_001.json")
        case = validate_case(raw)
        self.assertEqual(case.context, {})

    def test_context_is_loaded(self):
        raw = self.load("eval/dataset/golden/sample_rd_001.json")
        raw["context"] = {"identity_verified": True, "refund_limit": 200}
        case = validate_case(raw)
        self.assertEqual(case.context["identity_verified"], True)
        self.assertEqual(case.context["refund_limit"], 200)


class TestTrace(unittest.TestCase):
    def test_records_steps_with_sequence(self):
        t = TraceRecorder(run_id="r1", case_id="c1")
        t.record("route", behavior="B2", rule_hit=["R1"])
        t.record("act", tool="search_chat_history", executed=True)
        self.assertEqual([s["seq"] for s in t.steps], [1, 2])
        self.assertEqual(t.steps[0]["behavior"], "B2")

    def test_to_dict(self):
        t = TraceRecorder(run_id="r1", case_id="c1")
        t.record("route", behavior="B1")
        d = t.to_dict()
        self.assertEqual(d["run_id"], "r1")
        self.assertEqual(d["case_id"], "c1")
        self.assertEqual(len(d["steps"]), 1)


if __name__ == "__main__":
    unittest.main()
