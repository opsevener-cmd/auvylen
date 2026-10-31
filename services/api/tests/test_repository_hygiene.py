"""Datastore snapshots and dumps must never be tracked (they may hold private state)."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN = (".rdb", ".aof", ".dump", ".sql", ".sqlite", ".sqlite3", ".db")


def test_no_datastore_snapshots_are_tracked() -> None:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("Not running from a Git checkout")
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    offending = [
        path
        for path in tracked
        if path.lower().endswith(FORBIDDEN) or Path(path).name.startswith("appendonly")
    ]
    assert offending == []


def test_ignore_rules_cover_redis_snapshots() -> None:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("Not running from a Git checkout")
    for name in ("dump.rdb", "nested/dump.rdb", "appendonly.aof"):
        result = subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT, check=False)
        assert result.returncode == 0, name
