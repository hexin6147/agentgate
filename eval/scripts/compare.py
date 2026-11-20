#!/usr/bin/env python
"""Compare two evaluation reports (base vs target).

Usage:
    .venv/bin/python eval/scripts/compare.py \
        --base eval/results/report_v1.json \
        --target eval/results/report_v2.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.evaluation import compare_reports


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    with open(args.base, encoding="utf-8") as f:
        base = json.load(f)
    with open(args.target, encoding="utf-8") as f:
        target = json.load(f)

    diff = compare_reports(base, target)
    text = json.dumps(diff, ensure_ascii=False, indent=2)
    print(text)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
