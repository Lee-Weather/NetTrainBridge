#!/usr/bin/env python3
"""JobRunner 单元测试（无网络）。"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

_AGENT_DIR = Path(__file__).resolve().parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from config import AgentConfig
from job_runner import JobRunner


def test_wrap_conda_no_e_flag() -> None:
    """conda run 不得使用已废弃/不存在的 -e 参数。"""
    runner = JobRunner(AgentConfig(conda_env="F1"))
    cmd = runner._wrap_conda(["python", "-c", "print(1)"])
    assert cmd == [
        "conda", "run", "-n", "F1", "--no-capture-output",
        "python", "-c", "print(1)",
    ]
    assert "-e" not in cmd


def test_wrap_conda_empty_env_passthrough() -> None:
    runner = JobRunner(AgentConfig(conda_env=""))
    assert runner._wrap_conda(["pip", "install", "-e", "."]) == [
        "pip", "install", "-e", ".",
    ]


def test_find_test_csv_latest() -> None:
    runner = JobRunner(AgentConfig())
    with tempfile.TemporaryDirectory() as tmp:
        job_dir = Path(tmp)
        test_dir = job_dir / "test"
        test_dir.mkdir()
        older = test_dir / "isaac_diag_old.csv"
        newer = test_dir / "isaac_diag_new.csv"
        older.write_text("old", encoding="utf-8")
        newer.write_text("new", encoding="utf-8")
        time.sleep(0.01)
        newer.touch()
        assert runner.find_test_csv(job_dir) == newer


def test_find_test_csv_missing() -> None:
    runner = JobRunner(AgentConfig())
    with tempfile.TemporaryDirectory() as tmp:
        assert runner.find_test_csv(Path(tmp)) is None


if __name__ == "__main__":
    test_wrap_conda_no_e_flag()
    test_wrap_conda_empty_env_passthrough()
    test_find_test_csv_latest()
    test_find_test_csv_missing()
    print("test_job_runner passed")
