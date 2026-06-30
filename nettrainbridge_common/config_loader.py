"""NetTrainBridge 统一配置文件加载。

优先级（高 → 低）：
  1. 环境变量 NETTRAINBRIDGE_* / GRADMOTION_*
  2. 配置文件
  3. 代码默认值

配置文件查找顺序：
  1. $NETTRAINBRIDGE_CONFIG 指定路径
  2. 当前目录 .nettrainbridge.json
  3. ~/.nettrainbridge/config.json  （Windows: %USERPROFILE%\\.nettrainbridge\\config.json）
"""

from __future__ import annotations

import json
import os
from importlib import resources
from pathlib import Path
from typing import Any

_CACHE: dict | None = None
_CACHE_PATH: Path | None = None


def default_config_path() -> Path:
    return Path.home() / ".nettrainbridge" / "config.json"


def discover_config_paths() -> list[Path]:
    paths: list[Path] = []
    explicit = os.environ.get("NETTRAINBRIDGE_CONFIG")
    if explicit:
        paths.append(Path(explicit).expanduser())
    paths.append(Path.cwd() / ".nettrainbridge.json")
    paths.append(default_config_path())
    return paths


def load_config_file(*, reload: bool = False) -> tuple[dict[str, Any], Path | None]:
    global _CACHE, _CACHE_PATH
    if _CACHE is not None and not reload:
        return _CACHE, _CACHE_PATH

    for path in discover_config_paths():
        if path.is_file():
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError(f"配置文件必须是 JSON 对象: {path}")
            _CACHE = data
            _CACHE_PATH = path
            return _CACHE, _CACHE_PATH

    _CACHE = {}
    _CACHE_PATH = None
    return _CACHE, _CACHE_PATH


def _lookup_in_config(key: str, section: str | None) -> Any:
    data, _ = load_config_file()
    if section:
        block = data.get(section)
        if isinstance(block, dict) and key in block:
            return block[key]
    if key in data:
        return data[key]
    return None


def get_setting(
    key: str,
    *,
    env_new: str,
    env_old: str | None = None,
    section: str | None = None,
    default: Any = None,
) -> Any:
    """读取单项配置。"""
    value = os.environ.get(env_new)
    if value is None and env_old:
        value = os.environ.get(env_old)
    if value is not None:
        return value

    cfg_value = _lookup_in_config(key, section)
    if cfg_value is not None:
        return cfg_value

    return default


def _read_example_template() -> str | None:
    try:
        ref = resources.files("nettrainbridge_common").joinpath("config.example.json")
        if ref.is_file():
            return ref.read_text(encoding="utf-8")
    except (ModuleNotFoundError, TypeError, OSError):
        pass

    local = Path(__file__).resolve().parent / "config.example.json"
    if local.is_file():
        return local.read_text(encoding="utf-8")
    return None


def write_default_config(
    path: Path | None = None,
    *,
    server_url: str = "http://47.103.63.175:8000",
    overwrite: bool = False,
) -> Path:
    """写入示例配置文件。"""
    target = path or default_config_path()
    if target.exists() and not overwrite:
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    content = _read_example_template()
    if content:
        content = content.replace("http://47.103.63.175:8000", server_url)
    else:
        content = json.dumps(
            {
                "server_url": server_url,
                "cli": {"server_url": server_url},
                "agent": {
                    "server_url": server_url,
                    "proxy": "",
                    "workspace": "~/czy/nettrainbridge",
                    "conda_env": "F1",
                },
                "server": {
                    "allowed_repos": [
                        "https://github.com/Lee-Weather/agi_origin.git",
                    ],
                },
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n"

    target.write_text(content, encoding="utf-8")
    load_config_file(reload=True)
    return target


def config_status_message() -> str:
    """返回当前配置来源说明（用于启动日志）。"""
    _, path = load_config_file()
    if path:
        return f"配置文件: {path}"
    return "配置文件: 未找到（使用环境变量或内置默认值）"
