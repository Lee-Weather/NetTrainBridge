#!/usr/bin/env python3
"""workspace 与 Server 对齐逻辑单元测试。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_AGENT_DIR = Path(__file__).resolve().parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from agent import _JOB_ID_RE


def test_job_id_pattern() -> None:
    assert _JOB_ID_RE.fullmatch("d45dd67e27cd")
    assert _JOB_ID_RE.fullmatch("89fdd67d2a4b")
    assert not _JOB_ID_RE.fullmatch("backup")
    assert not _JOB_ID_RE.fullmatch("d45dd67e27cd-extra")


if __name__ == "__main__":
    test_job_id_pattern()
    print("test_workspace_align passed")
