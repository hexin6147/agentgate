import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate import logging as ag_log


class TestStructuredLogging(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "logs", "agentgate.jsonl")
        self._old_path = os.environ.get("AGENTGATE_LOG")
        os.environ["AGENTGATE_LOG"] = self.path
        ag_log.set_trace("-", None)

    def tearDown(self):
        if self._old_path is None:
            os.environ.pop("AGENTGATE_LOG", None)
        else:
            os.environ["AGENTGATE_LOG"] = self._old_path
        self.tmp.cleanup()

    def _lines(self):
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_log_event_carries_trace_and_run(self):
        ag_log.set_trace("trace-1", "run-1")
        ag_log.log_event("run_start", case_id="c1")

        [record] = self._lines()
        self.assertEqual(record["trace_id"], "trace-1")
        self.assertEqual(record["run_id"], "run-1")
        self.assertEqual(record["event"], "run_start")
        self.assertEqual(record["level"], "info")
        self.assertEqual(record["case_id"], "c1")
        self.assertIn("ts", record)

    def test_log_event_includes_span_and_fields(self):
        ag_log.set_trace("trace-2", "run-2")
        ag_log.set_span("span-9")
        ag_log.log_event("tool_call", level="warning", tool="query_ci", latency_ms=4.2)

        [record] = self._lines()
        self.assertEqual(record["span_id"], "span-9")
        self.assertEqual(record["level"], "warning")
        self.assertEqual(record["tool"], "query_ci")
        self.assertAlmostEqual(record["latency_ms"], 4.2)

    def test_unknown_error_type_is_normalized(self):
        ag_log.set_trace("trace-3")
        ag_log.log_event("boom", level="error", error_type="made-up")

        [record] = self._lines()
        self.assertEqual(record["error_type"], "internal")

    def test_missing_trace_still_has_required_key(self):
        ag_log.log_event("outside_run")

        [record] = self._lines()
        self.assertEqual(record["trace_id"], "-")
        self.assertEqual(record["run_id"], "-")

    def test_classify_error_enum(self):
        self.assertEqual(ag_log.classify_error(TimeoutError("timed out")), "timeout")
        self.assertEqual(ag_log.classify_error(ValueError("bad")), "validation")
        self.assertEqual(ag_log.classify_error(ConnectionError("down")), "upstream")
        self.assertEqual(ag_log.classify_error(RuntimeError("bug")), "internal")

    def test_appends_json_lines(self):
        ag_log.set_trace("trace-4", "run-4")
        ag_log.log_event("one")
        ag_log.log_event("two")

        records = self._lines()
        self.assertEqual([r["event"] for r in records], ["one", "two"])


if __name__ == "__main__":
    unittest.main()
