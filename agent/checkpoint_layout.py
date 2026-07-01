"""训练代码原生 logs 路径布局（R1-2）。"""

from __future__ import annotations

import re
from pathlib import Path

DEFAULT_TEST_TASK = "x1_dh_stand"
_CHECKPOINT_NUM = re.compile(r"model_(\d+)\.pt$", re.IGNORECASE)


def logs_export_dir(job_dir: Path, task: str, load_run: str) -> Path:
    """{job_dir}/logs/<task>/exported_data/<load_run>/"""
    return job_dir / "logs" / task / "exported_data" / load_run


def model_path_in_logs(job_dir: Path, task: str, load_run: str, checkpoint: int) -> Path:
    return logs_export_dir(job_dir, task, load_run) / f"model_{checkpoint}.pt"


def checkpoint_int_from_filename(filename: str) -> int | None:
    match = _CHECKPOINT_NUM.search(filename)
    if match:
        return int(match.group(1))
    return None


def checkpoint_int_from_spec(spec: str, filename: str) -> int:
    """从 gm_checkpoint 说明与落盘文件名解析整数 checkpoint。"""
    from_filename = checkpoint_int_from_filename(filename)
    if from_filename is not None:
        return from_filename

    spec = (spec or "latest").strip()
    if spec == "latest":
        raise ValueError(f"无法从文件名解析 checkpoint: {filename}")

    if spec.endswith(".pt"):
        parsed = checkpoint_int_from_filename(spec)
        if parsed is not None:
            return parsed

    try:
        return int(spec)
    except ValueError as exc:
        raise ValueError(f"无法解析 checkpoint: {spec!r} / {filename}") from exc


def find_legacy_fetched_model(job_dir: Path) -> Path | None:
    """v0.2 兼容：fetched_models/*.pt"""
    legacy = job_dir / "fetched_models"
    if not legacy.is_dir():
        return None
    pts = list(legacy.glob("*.pt"))
    if not pts:
        return None
    return max(pts, key=lambda p: p.stat().st_mtime)
