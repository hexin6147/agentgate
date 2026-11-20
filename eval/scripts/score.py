#!/usr/bin/env python
"""Run the offline evaluation over a dataset and write a report.

Usage:
    .venv/bin/python eval/scripts/score.py \
        --dataset eval/dataset \
        --out eval/results/report.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.evaluation import evaluate
from agentgate.factory import build_agent
from agentgate.judge import LLMJudge
from agentgate.llm import LLMClient
from agentgate.rubric import RubricValidationError, load_rubric
from agentgate.tools import ToolRegistry
from samples.ticket.tools import TicketToolRegistry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="eval/dataset")
    parser.add_argument("--out", default="eval/results/report.json")
    parser.add_argument("--project-id", default="pay")
    parser.add_argument(
        "--agent", choices=["rule", "llm", "ticket"], default="rule"
    )
    parser.add_argument("--context", choices=["rule", "bge"], default="rule")
    parser.add_argument("--judge", choices=["none", "llm"], default="none")
    parser.add_argument("--rubric", default=None, help="path to a Rubric YAML")
    parser.add_argument(
        "--no-fence",
        action="store_true",
        help="ablation only: disable all fences so every tool call is permitted",
    )
    args = parser.parse_args(argv)

    dataset = args.dataset if os.path.isabs(args.dataset) else os.path.join(ROOT, args.dataset)
    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)

    judge = None
    if args.judge == "llm":
        judge_client = LLMClient(
            base_url=os.getenv("JUDGE_BASE_URL"),
            model=os.getenv("JUDGE_MODEL"),
            api_key=os.getenv("JUDGE_API_KEY"),
        )
        judge = LLMJudge(judge_client.chat)

    rubric_path = args.rubric
    if rubric_path is None:
        rubric_path = (
            "eval/rubrics/restricted_v1.yaml"
            if args.agent == "ticket"
            else "eval/rubrics/collab_v1.yaml"
        )
    if not os.path.isabs(rubric_path):
        rubric_path = os.path.join(ROOT, rubric_path)
    try:
        rubric = load_rubric(rubric_path)
    except RubricValidationError as exc:
        print(f"invalid rubric: {exc}", file=sys.stderr)
        return 1

    tools = (
        TicketToolRegistry(fence_enabled=not args.no_fence)
        if args.agent == "ticket"
        else ToolRegistry(fence_enabled=not args.no_fence)
    )
    report = evaluate(
        build_agent(args.agent, args.context),
        tools,
        dataset,
        {"project_id": args.project_id},
        judge=judge,
        rubric=rubric,
    )

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    if report["failed_cases"]:
        print("failed_cases:", ", ".join(report["failed_cases"]))
    if "rubric" in report:
        rubric_result = report["rubric"]
        print(
            "rubric: "
            f"{rubric_result['rubric_id']} "
            f"score={rubric_result['weighted_score']:.3f} "
            f"threshold={rubric_result['pass_threshold']} "
            f"gate={rubric_result['gate_passed']} "
            f"passed={rubric_result['passed']}"
        )
        if rubric_result["missing_metrics"]:
            print(
                "missing_metrics:",
                ", ".join(rubric_result["missing_metrics"]),
            )
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
