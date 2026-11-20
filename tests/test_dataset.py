import glob
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys

sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.schema import validate_case


class TestDataset(unittest.TestCase):
    def test_all_cases_validate(self):
        paths = [
            p
            for p in glob.glob(
                os.path.join(ROOT, "eval/dataset/**/*.json"), recursive=True
            )
            if os.path.basename(p) != "schema.json"
        ]
        self.assertGreaterEqual(len(paths), 80)

        for path in paths:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            case = validate_case(raw)
            self.assertEqual(case.agent_id, "rd_collab")


if __name__ == "__main__":
    unittest.main()
