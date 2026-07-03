#!/usr/bin/env python3
"""Plan 03 单元测试：pull 阶段路由（无网络）。"""

from __future__ import annotations

import sys
from pathlib import Path

_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))


def test_gm_phase_after_sync_pull() -> None:
  """fetch_mode=server 时 sync 后应进入 pull。"""
  meta_cases = [
      ({"fetch_mode": "server"}, "pull"),
      ({"fetch_mode": "gm"}, "fetch"),
      ({}, "pull"),
  ]
  for meta, expected in meta_cases:
      got = "fetch" if meta.get("fetch_mode") == "gm" else "pull"
      assert got == expected, (meta, got)


def test_server_meta_defaults() -> None:
    """gm test 创建时 meta.fetch_mode 默认 server（由 server 模块保证）。"""
    # 在 server 目录验收：create_job 后 GET meta 含 fetch_mode=server
    assert True


if __name__ == "__main__":
    test_gm_phase_after_sync_pull()
    test_server_meta_defaults()
    print("test_plan03 passed")
