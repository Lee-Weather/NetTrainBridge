"""环境变量读取：优先 NETTRAINBRIDGE_*，兼容已弃用的 GRADMOTION_*。"""

from __future__ import annotations

import logging
import os

_logger = logging.getLogger("nettrainbridge.agent")


def get_env(new_key: str, old_key: str) -> str | None:
    """读取环境变量，新名优先；仅使用旧名时打 deprecation 日志。"""
    value = os.environ.get(new_key)
    if value is not None:
        return value
    value = os.environ.get(old_key)
    if value is not None:
        _logger.warning("环境变量 %s 已弃用，请改用 %s", old_key, new_key)
    return value
