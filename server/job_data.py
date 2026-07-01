"""任务数据目录与 meta.json 读写。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import ServerConfig

_config = ServerConfig.load()


def job_dir(job_id: str) -> Path:
    return Path(_config.DATA_DIR) / job_id


def models_dir(job_id: str) -> Path:
    return job_dir(job_id) / "models"


def test_dir(job_id: str) -> Path:
    return job_dir(job_id) / "test"


def meta_path(job_id: str) -> Path:
    return job_dir(job_id) / "meta.json"


def read_meta(job_id: str) -> dict[str, Any] | None:
    path = meta_path(job_id)
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"meta.json 必须是对象: {path}")
    return data


def merge_meta(job_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """合并写入 meta.json（patch 覆盖同名字段）。"""
    job_dir(job_id).mkdir(parents=True, exist_ok=True)
    current = read_meta(job_id) or {}
    current.update(patch)
    with open(meta_path(job_id), "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return current


def init_job_layout(job_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    """创建任务时初始化 data/{id}/ 目录结构与 meta.json。"""
    models_dir(job_id).mkdir(parents=True, exist_ok=True)
    test = test_dir(job_id)
    test.mkdir(parents=True, exist_ok=True)
    (test / "videos").mkdir(parents=True, exist_ok=True)
    return merge_meta(job_id, meta)
