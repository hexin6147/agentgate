"""Isolate runtime side effects (SQLite + JSONL logs) for every test."""
import pytest


@pytest.fixture(autouse=True)
def isolate_agentgate_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTGATE_DB", str(tmp_path / "agentgate.db"))
    monkeypatch.setenv("AGENTGATE_LOG", str(tmp_path / "agentgate.jsonl"))
