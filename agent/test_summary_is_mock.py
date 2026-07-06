#!/usr/bin/env python3
"""test 产物上传辅助逻辑单元测试。"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_AGENT_DIR = Path(__file__).resolve().parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from agent import _summary_is_mock


def test_summary_is_mock_true() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "summary.json"
        path.write_text(json.dumps({"mode": "mock"}), encoding="utf-8")
        assert _summary_is_mock(path) is True


def test_summary_is_mock_false() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "summary.json"
        path.write_text(json.dumps({"mode": "real"}), encoding="utf-8")
        assert _summary_is_mock(path) is False


if __name__ == "__main__":
    test_summary_is_mock_true()
    test_summary_is_mock_false()
    print("test_summary_is_mock passed")
