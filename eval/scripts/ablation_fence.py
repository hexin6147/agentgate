#!/usr/bin/env python
"""Fence ablation: what changes when the platform stops enforcing fences?

The platform's core claim is "violations are blocked before execution".  This
script measures that claim directly: run the same cases twice, once with
fences enabled and once with them disabled, on the same deterministic mock
tools, and compare:

  - cases where a high-risk write tool actually executed
  - cases where at least one fence check failed (i.e. the fence engaged)
  - cases whose final route matches the expected route
  - cases that pass the standard per-case judgement

Everything runs in-process against mock tools; nothing is sent anywhere.

Usage:
    .venv/bin/python eval/scripts/ablation_fence.py
    .venv/bin/python eval/scripts/ablation_fence.py --out eval/results/ablation.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.evaluation import score_case  # noqa: E402
from agentgate.factory import build_agent  # noqa: E402
from agentgate.harness import Harness  # noqa: E402
from agentgate.runner import Runner  # noqa: E402
from agentgate.tools import ToolRegistry  # noqa: E402
from samples.ticket.tools import TicketToolRegistry  # noqa: E402

TARGETS: List[Dict[str, Any]] = [
    {
        "key": "a_adversarial",
        "name": "Sample A · 对抗集",
        "agent": "rule",
        "path": "eval/dataset/adversarial",
        "ctx": {"project_id": "pay"},
    },
    {
        "key": "a_normal",
        "name": "Sample A · 正常集",
        "agent": "rule",
        "path": "eval/dataset/golden",
        "ctx": {"project_id": "pay"},
    },
    {
        "key": "b_adversarial",
        "name": "Sample B · 对抗集",
        "agent": "ticket",
        "path": "eval/dataset_ticket/adversarial",
        "ctx": {"project_id": "pay"},
    },
    {
        "key": "b_normal",
        "name": "Sample B · 正常集",
        "agent": "ticket",
        "path": "eval/dataset_ticket/golden",
        "ctx": {"project_id": "pay"},
    },
]


def _registry(agent_kind: str, fences: bool) -> Any:
    if agent_kind == "ticket":
        return TicketToolRegistry(fence_enabled=fences)
    return ToolRegistry(fence_enabled=fences)


def _run_target(target: Dict[str, Any], fences: bool) -> Dict[str, Any]:
    tools = _registry(target["agent"], fences)
    high_risk = {
        name for name, spec in tools.specs.items() if spec.get("risk") == "high"
    }
    runner = Runner(Harness(tools))
    agent = build_agent(target["agent"], "rule")
    directory = os.path.join(ROOT, target["path"])

    rows = []
    for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
        case = runner.load_case(path)
        result = runner.run_case_file(path, agent, target["ctx"])
        score = score_case(case, result)
        steps = result.trace.get("steps", [])
        executed = [
            step.get("tool")
            for step in steps
            if step.get("node") == "act"
            and step.get("executed")
            and step.get("tool") in high_risk
        ]
        blocked = any(
            any(not check.get("passed") for check in (step.get("fence_checks") or []))
            for step in steps
        )
        rows.append(
            {
                "case_id": case.case_id,
                "executed_high_risk": executed,
                "fence_blocked": blocked,
                "route_ok": score["route_correct"],
                "passed": score["passed"],
            }
        )

    return {
        "key": target["key"],
        "name": target["name"],
        "fences": fences,
        "cases": len(rows),
        "cases_with_high_risk_execution": sum(
            1 for row in rows if row["executed_high_risk"]
        ),
        "high_risk_executions": sum(len(row["executed_high_risk"]) for row in rows),
        "fence_blocked_cases": sum(1 for row in rows if row["fence_blocked"]),
        "route_ok": sum(1 for row in rows if row["route_ok"]),
        "passed": sum(1 for row in rows if row["passed"]),
        "details": rows,
    }


def run_ablation(targets: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    targets = targets or TARGETS
    results = []
    for target in targets:
        on = _run_target(target, fences=True)
        off = _run_target(target, fences=False)
        results.append({"target": target["key"], "on": on, "off": off})
    return {"results": results}


def _print_table(report: Dict[str, Any]) -> None:
    header = (
        f"{'数据集':<22}{'围栏':<6}{'用例':>4}"
        f"{'高危写入执行':>10}{'被拦用例':>8}{'路由正确':>8}{'通过':>6}"
    )
    print(header)
    print("-" * len(header))
    for item in report["results"]:
        for mode, label in ((item["on"], "开"), (item["off"], "关")):
            print(
                f"{mode['name']:<22}{label:<6}{mode['cases']:>4}"
                f"{mode['high_risk_executions']:>10}"
                f"{mode['fence_blocked_cases']:>10}"
                f"{mode['route_ok']:>10}"
                f"{mode['passed']:>8}"
            )
        print()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="eval/results/ablation_fence.json")
    args = parser.parse_args(argv)

    report = run_ablation()
    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    _print_table(report)
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
