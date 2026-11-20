"""Batch/single-case runner."""
from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List, Optional

from .harness import Harness
from .models import Case, RunResult
from .schema import validate_case


class Runner:
    def __init__(self, harness: Harness):
        self.harness = harness

    def load_case(self, path: str) -> Case:
        with open(path, encoding="utf-8") as f:
            return validate_case(json.load(f))

    def run_case_file(
        self,
        path: str,
        agent: Any,
        ctx: Optional[Dict[str, Any]] = None,
        scenario: Optional[str] = None,
    ) -> RunResult:
        case = self.load_case(path)
        merged = {**(ctx or {}), **case.context}
        return self.harness.run_case(agent, case, merged, scenario=scenario)

    def run_dir(
        self,
        directory: str,
        agent: Any,
        ctx: Optional[Dict[str, Any]] = None,
        pattern: str = "*.json",
        scenario: Optional[str] = None,
    ) -> List[RunResult]:
        results: List[RunResult] = []
        for path in sorted(glob.glob(os.path.join(directory, pattern))):
            results.append(self.run_case_file(path, agent, ctx, scenario=scenario))
        return results
