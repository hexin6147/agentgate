#!/usr/bin/env python
"""Convenience launcher for local development.

Usage:
    .venv/bin/python run.py run --case eval/dataset/golden/sample_rd_001.json
    .venv/bin/python run.py feishu
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from agentgate.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
