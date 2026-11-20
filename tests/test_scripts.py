import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestScoreScript(unittest.TestCase):
    def test_score_script_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "report.json")
            proc = subprocess.run(
                [
                    sys.executable,
                    os.path.join(ROOT, "eval/scripts/score.py"),
                    "--out",
                    out,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, encoding="utf-8") as f:
                report = json.load(f)
            self.assertGreaterEqual(report["metrics"]["cases"], 80)
            self.assertAlmostEqual(report["metrics"]["trace_completeness"], 1.0)


if __name__ == "__main__":
    unittest.main()
