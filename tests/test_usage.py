import json
import os
import sqlite3
import sys
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate import logging as ag_log
from agentgate.harness import Harness
from agentgate.llm import LLMClient
from agentgate.models import AgentResult
from agentgate.schema import validate_case
from agentgate.tools import ToolRegistry
from agentgate.trace import TraceRecorder, set_current_recorder
from agentgate.usage import collect_usage, record_usage


def load_case(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return validate_case(json.load(f))


def make_response(content="hello", prompt_tokens=3, completion_tokens=2, usage=True):
    usage_obj = (
        SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        if usage
        else None
    )
    return SimpleNamespace(
        usage=usage_obj,
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


def make_client(response=None, exc=None):
    class Completions:
        def create(self, **kwargs):
            if exc is not None:
                raise exc
            return response

    client = object.__new__(LLMClient)
    client.model = "fake-model"
    client.client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions())
    )
    return client


class TestUsageCollection(unittest.TestCase):
    def tearDown(self):
        ag_log.set_trace("-", None)

    def test_collect_usage_captures_context(self):
        ag_log.set_trace("trace-u", "run-u")
        ag_log.set_span("span-u")
        with collect_usage() as rows:
            record_usage("fake-model", 11, 7, 4.5)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["run_id"], "run-u")
        self.assertEqual(rows[0]["span_id"], "span-u")
        self.assertEqual(rows[0]["prompt_tokens"], 11)
        self.assertEqual(rows[0]["completion_tokens"], 7)
        self.assertAlmostEqual(rows[0]["latency_ms"], 4.5)

    def test_llm_chat_records_usage(self):
        client = make_client(make_response(prompt_tokens=30, completion_tokens=8))
        ag_log.set_trace("trace-llm", "run-llm")
        with collect_usage() as rows:
            out = client.chat("system", "user")

        self.assertEqual(out, "hello")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["model"], "fake-model")
        self.assertEqual(rows[0]["prompt_tokens"], 30)
        self.assertEqual(rows[0]["completion_tokens"], 8)
        self.assertGreaterEqual(rows[0]["latency_ms"], 0.0)

    def test_missing_usage_still_records_latency(self):
        client = make_client(make_response(usage=False))
        ag_log.set_trace("trace-zero", "run-zero")
        with collect_usage() as rows:
            client.chat("system", "user")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["prompt_tokens"], 0)
        self.assertEqual(rows[0]["completion_tokens"], 0)
        self.assertIn("latency_ms", rows[0])

    def test_llm_error_marks_span_and_skips_usage(self):
        client = make_client(exc=TimeoutError("timed out"))
        trace = TraceRecorder(run_id="r-err", case_id="c-err")
        root = trace.start_span("run", kind="root")
        trace.set_root_span(root)
        set_current_recorder(trace)
        ag_log.set_trace("r-err", "r-err")
        try:
            trace.record("route", behavior="B2")
            with collect_usage() as rows:
                with self.assertRaises(TimeoutError):
                    client.chat("system", "user")
            trace.finish()
        finally:
            set_current_recorder(None)
            ag_log.set_trace("-", None)

        self.assertEqual(rows, [])
        llm_spans = [s for s in trace.spans if s["name"] == "llm:fake-model"]
        self.assertEqual(len(llm_spans), 1)
        self.assertEqual(llm_spans[0]["status"], "error")
        self.assertEqual(llm_spans[0]["attrs"]["error_type"], "timeout")

    def test_llm_span_nests_under_step(self):
        client = make_client(make_response())
        trace = TraceRecorder(run_id="r-depth", case_id="c-depth")
        root = trace.start_span("run", kind="root")
        trace.set_root_span(root)
        set_current_recorder(trace)
        ag_log.set_trace("r-depth", "r-depth")
        try:
            trace.record("route", behavior="B2")
            client.chat("system", "user")
            trace.finish()
        finally:
            set_current_recorder(None)
            ag_log.set_trace("-", None)

        by_id = {s["span_id"]: s for s in trace.spans}
        llm_span = next(s for s in trace.spans if s["name"] == "llm:fake-model")
        step_span = by_id[llm_span["parent_id"]]
        self.assertEqual(step_span["name"], "route")
        self.assertEqual(step_span["parent_id"], root)


class TestHarnessPersistsUsage(unittest.TestCase):
    def test_fake_llm_agent_usage_row(self):
        client = make_client(make_response(prompt_tokens=12, completion_tokens=4))

        class FakeLLMAgent:
            def run(self, case, tools, trace, ctx):
                trace.record("route", behavior="B2")
                output = client.chat("system", case.trigger_query)
                trace.record("respond", output=output)
                return AgentResult(output=output, route="AUTO", state="DONE")

        case = load_case("eval/dataset/golden/sample_rd_001.json")
        result = Harness(ToolRegistry()).run_case(
            FakeLLMAgent(), case, {"project_id": "pay"}, scenario="S1"
        )

        self.assertEqual(result.status, "DONE")
        with sqlite3.connect(os.environ["AGENTGATE_DB"]) as conn:
            rows = conn.execute(
                "SELECT run_id, model, prompt_tokens, completion_tokens, "
                "latency_ms FROM usage WHERE run_id = ?",
                (result.run_id,),
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "fake-model")
        self.assertEqual(rows[0][2], 12)
        self.assertEqual(rows[0][3], 4)
        self.assertGreaterEqual(rows[0][4], 0.0)


if __name__ == "__main__":
    unittest.main()
