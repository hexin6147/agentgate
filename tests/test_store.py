import json
import os
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.models import RunResult
from agentgate import store


def make_run(run_id="run_1", case_id="case_1", trace_id=None):
    return RunResult(
        run_id=run_id,
        case_id=case_id,
        status="DONE",
        route="AUTO",
        output="ok",
        trace={
            "trace_id": trace_id or run_id,
            "started_at": "2026-11-21T00:00:00+00:00",
            "ended_at": "2026-11-21T00:00:01+00:00",
        },
    )


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "agentgate.db")
        self._old = os.environ.get("AGENTGATE_DB")
        os.environ["AGENTGATE_DB"] = self.db
        store.init_db()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("AGENTGATE_DB", None)
        else:
            os.environ["AGENTGATE_DB"] = self._old
        self.tmp.cleanup()

    def _query(self, sql, params=()):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(sql, params).fetchall()

    def test_init_creates_tables(self):
        names = {
            row[0]
            for row in self._query(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertTrue({"runs", "spans", "usage", "reports"} <= names)

    def test_save_and_get_run(self):
        store.save_run(make_run(), scenario="S1")
        run = store.get_run("run_1")
        self.assertEqual(run["case_id"], "case_1")
        self.assertEqual(run["scenario"], "S1")
        self.assertEqual(run["trace_id"], "run_1")
        self.assertEqual(run["status"], "DONE")
        self.assertEqual(run["started_at"], "2026-11-21T00:00:00+00:00")
        self.assertEqual(run["ended_at"], "2026-11-21T00:00:01+00:00")

    def test_save_run_is_idempotent(self):
        store.save_run(make_run(), scenario="S1")
        run = make_run()
        run.output = "updated"
        store.save_run(run, scenario="S1")
        self.assertEqual(store.get_run("run_1")["output"], "updated")
        self.assertEqual(len(store.query_runs()), 1)

    def test_query_runs_by_scenario_and_trace(self):
        store.save_run(make_run("run_a", trace_id="trace_a"), scenario="S1")
        store.save_run(make_run("run_b", trace_id="trace_b"), scenario="S2")

        self.assertEqual(
            [r["run_id"] for r in store.query_runs(scenario="S1")], ["run_a"]
        )
        self.assertEqual(
            [r["run_id"] for r in store.query_runs(trace_id="trace_b")], ["run_b"]
        )
        self.assertEqual(len(store.query_runs(limit=1)), 1)

    def test_spans_roundtrip(self):
        spans = [
            {
                "span_id": "s1",
                "parent_id": None,
                "name": "run",
                "start_ts": "t0",
                "end_ts": "t2",
                "status": "ok",
                "attrs": {"kind": "root"},
            },
            {
                "span_id": "s2",
                "parent_id": "s1",
                "name": "route",
                "start_ts": "t0",
                "end_ts": "t1",
                "status": "ok",
                "attrs": {"kind": "step", "behavior": "B2"},
            },
        ]
        store.save_spans("run_1", spans)
        loaded = store.get_spans("run_1")
        self.assertEqual([s["span_id"] for s in loaded], ["s1", "s2"])
        self.assertEqual(loaded[1]["parent_id"], "s1")
        self.assertEqual(loaded[1]["attrs"]["behavior"], "B2")

    def test_usage_rows(self):
        store.save_usage(
            [
                {
                    "run_id": "run_1",
                    "span_id": "span_llm",
                    "model": "qwen2.5:7b-instruct",
                    "prompt_tokens": 30,
                    "completion_tokens": 8,
                    "latency_ms": 12.5,
                }
            ]
        )
        rows = self._query(
            "SELECT run_id, model, prompt_tokens, completion_tokens, latency_ms "
            "FROM usage"
        )
        self.assertEqual(rows[0][0], "run_1")
        self.assertEqual(rows[0][2], 30)
        self.assertEqual(rows[0][3], 8)
        self.assertAlmostEqual(rows[0][4], 12.5)

    def test_report_roundtrip(self):
        store.save_report(
            {
                "scenario": "S1",
                "metrics": {"prompt_tokens": 30, "latency_ms": 12.5},
            },
            run_id="run_1",
        )
        rows = self._query(
            "SELECT run_id, scenario, metrics_json FROM reports"
        )
        self.assertEqual(rows[0][0], "run_1")
        self.assertEqual(rows[0][1], "S1")
        self.assertEqual(json.loads(rows[0][2])["prompt_tokens"], 30)


if __name__ == "__main__":
    unittest.main()
