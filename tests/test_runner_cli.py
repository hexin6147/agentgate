import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.cli import main
from agentgate.harness import Harness
from agentgate.runner import Runner
from agentgate.tools import ToolRegistry
from samples.rd_collab.adapter import RuleBasedAgent


class TestRunner(unittest.TestCase):
    def test_run_case_file(self):
        runner = Runner(Harness(ToolRegistry()))
        result = runner.run_case_file(
            "eval/dataset/golden/sample_rd_001.json",
            RuleBasedAgent(),
            {"project_id": "pay"},
        )
        self.assertEqual(result.status, "DONE")
        self.assertEqual(result.case_id, "rd_normal_001")


class TestCLI(unittest.TestCase):
    def test_cli_run_prints_json(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(
                [
                    "run",
                    "--case",
                    "eval/dataset/golden/sample_rd_001.json",
                    "--project-id",
                    "pay",
                ]
            )
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "DONE")
        self.assertEqual(data["case_id"], "rd_normal_001")


if __name__ == "__main__":
    unittest.main()
