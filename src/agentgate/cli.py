"""CLI entry point.

Usage:
    python -m agentgate.cli run --case eval/dataset/golden/sample_rd_001.json
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .harness import Harness
from .runner import Runner
from .tools import ToolRegistry
from samples.rd_collab.adapter import RuleBasedAgent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentgate")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="run one case against an agent")
    run_parser.add_argument("--case", required=True, help="path to a case JSON")
    run_parser.add_argument("--project-id", default=None)
    run_parser.add_argument("--incident-leveled", action="store_true")
    run_parser.add_argument("--confirmation-token", default=None)
    run_parser.add_argument("--trace-dir", default=None)
    run_parser.add_argument("--scenario", default=None)
    run_parser.add_argument("--agent", default="rd_collab", choices=["rd_collab"])

    sub.add_parser("feishu", help="start Feishu long-connection bot")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "run":
        tools = ToolRegistry()
        runner = Runner(Harness(tools, trace_dir=args.trace_dir))
        ctx = {
            "project_id": args.project_id,
            "incident_leveled": bool(args.incident_leveled),
            "confirmation_token": args.confirmation_token,
        }
        result = runner.run_case_file(
            args.case,
            RuleBasedAgent(),
            ctx,
            scenario=args.scenario,
        )
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "feishu":
        from .feishu_ws import run

        run()
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
