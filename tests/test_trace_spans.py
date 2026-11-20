import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate import store
from agentgate.harness import Harness
from agentgate.runner import Runner
from agentgate.schema import validate_case
from agentgate.tools import ToolRegistry
from agentgate.trace import TraceRecorder, set_current_recorder
from samples.rd_collab.adapter import RuleBasedAgent


def load_case(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return validate_case(json.load(f))


def span_depth(spans, span_id):
    by_id = {span["span_id"]: span for span in spans}
    depth = 1
    current = by_id[span_id]
    while current.get("parent_id"):
        current = by_id[current["parent_id"]]
        depth += 1
    return depth


class TestSpanRecorder(unittest.TestCase):
    def test_explicit_parent_child_chain(self):
        trace = TraceRecorder(run_id="r1", case_id="c1")
        root = trace.start_span("run", kind="root")
        step = trace.start_span("step", parent_id=root, kind="step")
        tool = trace.start_span("tool:query_ci", kind="tool")
        trace.end_span(tool, status="ok", ok=True)
        trace.end_span(step, status="ok")
        trace.end_span(root, status="ok")

        spans = trace.spans
        self.assertEqual(len(spans), 3)
        self.assertEqual(spans[0]["parent_id"], None)
        self.assertEqual(spans[1]["parent_id"], root)
        self.assertEqual(spans[2]["parent_id"], step)
        self.assertEqual(span_depth(spans, tool), 3)
        self.assertIsNotNone(spans[2]["end_ts"])
        self.assertEqual(spans[2]["attrs"]["ok"], True)

    def test_record_creates_step_span_and_keeps_old_shape(self):
        trace = TraceRecorder(run_id="r2", case_id="c2")
        root = trace.start_span("run", kind="root")
        trace.set_root_span(root)
        step = trace.record("route", behavior="B2")

        self.assertEqual(step["seq"], 1)
        self.assertEqual(step["node"], "route")
        self.assertIn("ts", step)
        self.assertIn("span_id", step)
        self.assertEqual(trace.spans[-1]["attrs"]["kind"], "step")
        self.assertEqual(trace.spans[-1]["attrs"]["behavior"], "B2")

    def test_tool_span_nests_under_current_step(self):
        tools = ToolRegistry(
            specs={
                "fake_tool": {
                    "risk": "low",
                    "required": [],
                    "requires_confirmation": False,
                }
            },
            fixtures={"fake_tool": {"answer": 42}},
        )
        trace = TraceRecorder(run_id="r3", case_id="c3")
        root = trace.start_span("run", kind="root")
        trace.set_root_span(root)
        set_current_recorder(trace)
        try:
            trace.record("plan", tool="fake_tool")
            result = tools.execute("fake_tool", {}, {})
            trace.finish()
        finally:
            set_current_recorder(None)
        trace.end_span(root, status="ok")

        spans = trace.spans
        tool_spans = [s for s in spans if s["name"] == "tool:fake_tool"]
        self.assertTrue(result.ok)
        self.assertEqual(len(tool_spans), 1)
        self.assertEqual(tool_spans[0]["status"], "ok")
        self.assertEqual(span_depth(spans, tool_spans[0]["span_id"]), 3)


class TestHarnessObservability(unittest.TestCase):
    def setUp(self):
        self.tools = ToolRegistry()
        self.case = load_case("eval/dataset/golden/sample_rd_001.json")

    def test_run_writes_store_spans_and_logs(self):
        result = Harness(self.tools).run_case(
            RuleBasedAgent(), self.case, {"project_id": "pay"}, scenario="S1"
        )

        self.assertEqual(result.status, "DONE")
        self.assertEqual(result.trace["trace_id"], result.run_id)
        self.assertGreaterEqual(
            max(span_depth(result.trace["spans"], s["span_id"]) for s in result.trace["spans"]),
            3,
        )

        run = store.get_run(result.run_id)
        self.assertIsNotNone(run)
        self.assertEqual(run["scenario"], "S1")
        self.assertEqual(run["status"], "DONE")

        spans = store.get_spans(result.run_id)
        self.assertGreaterEqual(len(spans), 3)
        step_names = [
            s["name"] for s in spans if s["attrs"].get("kind") == "step"
        ]
        self.assertEqual(
            step_names, [step["node"] for step in result.trace["steps"]]
        )

        self.assertEqual(
            [r["run_id"] for r in store.query_runs(trace_id=result.run_id)],
            [result.run_id],
        )
        self.assertEqual(
            [r["run_id"] for r in store.query_runs(scenario="S1")],
            [result.run_id],
        )

        log_path = os.environ["AGENTGATE_LOG"]
        with open(log_path, encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        self.assertTrue(records)
        self.assertTrue(all(record.get("trace_id") for record in records))
        events = [record["event"] for record in records]
        self.assertIn("run_start", events)
        self.assertIn("run_end", events)

    def test_case_exception_is_isolated_and_recorded(self):
        class BoomAgent:
            def run(self, case, tools, trace, ctx):
                raise TimeoutError("model timed out")

        result = Harness(self.tools).run_case(BoomAgent(), self.case, {})

        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.route, "ERROR")
        self.assertIn("timed out", result.error)
        self.assertEqual(result.trace["steps"][-1]["node"], "error")

        run = store.get_run(result.run_id)
        self.assertEqual(run["status"], "FAILED")
        error_spans = [
            s for s in result.trace["spans"] if s["attrs"].get("kind") == "step"
        ]
        self.assertEqual(error_spans[-1]["status"], "error")

        with open(os.environ["AGENTGATE_LOG"], encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        error_records = [r for r in records if r["event"] == "run_error"]
        self.assertEqual(error_records[0]["error_type"], "timeout")
        self.assertTrue(all(r.get("trace_id") for r in records))

    def test_one_failed_case_does_not_stop_batch(self):
        class FlakyAgent:
            def __init__(self):
                self.calls = 0

            def run(self, case, tools, trace, ctx):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("first case explodes")
                return RuleBasedAgent().run(case, tools, trace, ctx)

        with tempfile.TemporaryDirectory() as tmp:
            for rel in (
                "eval/dataset/golden/sample_rd_001.json",
                "eval/dataset/golden/gen_normal_ci_000.json",
            ):
                shutil.copy(os.path.join(ROOT, rel), tmp)
            results = Runner(Harness(self.tools)).run_dir(tmp, FlakyAgent())

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].status, "FAILED")
        self.assertEqual(results[1].status, "DONE")


if __name__ == "__main__":
    unittest.main()
