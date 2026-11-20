import glob
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.schema import validate_case


class TestHeldout(unittest.TestCase):
    def test_heldout_cases_validate(self):
        paths = sorted(
            glob.glob(os.path.join(ROOT, "eval/heldout/**/*.json"), recursive=True)
        )
        self.assertEqual(len(paths), 20)
        for path in paths:
            with open(path, encoding="utf-8") as f:
                case = validate_case(json.load(f))
            self.assertEqual(case.agent_id, "rd_collab")
            self.assertEqual(case.notes, "held-out set; not used for keyword design")


if __name__ == "__main__":
    unittest.main()
