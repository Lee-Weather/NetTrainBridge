"""test job 同窗参数解析（load_run + checkpoint）。"""

from __future__ import annotations

import shutil
from pathlib import Path

from api_client import APIClient
from checkpoint_layout import (
    DEFAULT_TEST_TASK,
    checkpoint_int_from_filename,
    checkpoint_int_from_spec,
    find_legacy_fetched_model,
    logs_export_dir,
    model_path_in_logs,
)
from fetch_runner import FetchRunnerError


async def resolve_test_context(
    api_client: APIClient,
    job: dict,
    job_dir: Path,
) -> dict:
    """解析 test 阶段所需的 task / load_run / checkpoint / checkpoint_path。"""
    job_id = job["id"]
    train_source = job.get("train_source") or "ntb"
    meta = await api_client.get_job_meta(job_id) or {}

    task = meta.get("task") or DEFAULT_TEST_TASK
    load_run = meta.get("load_run")
    checkpoint = meta.get("checkpoint")

    if train_source == "gm":
        model_path = _resolve_gm_model(job_dir, task, load_run, checkpoint, meta)
    else:
        model_path = await _resolve_ntb_parent_model(api_client, job, job_dir, task, load_run, checkpoint, meta)

    if checkpoint is None:
        checkpoint = checkpoint_int_from_filename(model_path.name)
    if checkpoint is None:
        raise FetchRunnerError(f"无法解析 checkpoint 整数: {model_path.name}")

    if not load_run:
        load_run = model_path.parent.name

    return {
        "task": task,
        "load_run": load_run,
        "checkpoint": int(checkpoint),
        "checkpoint_path": model_path,
    }


def _resolve_gm_model(
    job_dir: Path,
    task: str,
    load_run: str | None,
    checkpoint: int | None,
    meta: dict,
) -> Path:
    if load_run and checkpoint is not None:
        path = model_path_in_logs(job_dir, task, load_run, int(checkpoint))
        if path.is_file():
            return path

    if load_run:
        export_dir = logs_export_dir(job_dir, task, load_run)
        if export_dir.is_dir():
            pts = list(export_dir.glob("model_*.pt"))
            if pts:
                return max(pts, key=lambda p: p.stat().st_mtime)

    legacy = find_legacy_fetched_model(job_dir)
    if legacy is not None:
        return _migrate_legacy_to_logs(job_dir, task, load_run, checkpoint, meta, legacy)

    raise FetchRunnerError("gm 路径未找到本地 checkpoint（logs/.../exported_data/<load_run>/）")


async def _resolve_ntb_parent_model(
    api_client: APIClient,
    job: dict,
    job_dir: Path,
    task: str,
    load_run: str | None,
    checkpoint: int | None,
    meta: dict,
) -> Path:
    if not load_run:
        raise FetchRunnerError("ntb test 缺少 meta.load_run（请 ntb test run --load-run）")
    if checkpoint is None:
        raise FetchRunnerError("ntb test 缺少 meta.checkpoint")

    dest = model_path_in_logs(job_dir, task, load_run, int(checkpoint))
    if dest.is_file():
        return dest

    parent_id = job.get("parent_train_job_id")
    if not parent_id:
        raise FetchRunnerError("ntb test 缺少 parent_train_job_id")

    parent_meta = await api_client.get_job_meta(parent_id) or {}
    filename = parent_meta.get("model_filename") or f"model_{checkpoint}.pt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    downloaded = await api_client.download_checkpoint(parent_id, filename, dest)
    return downloaded


def _migrate_legacy_to_logs(
    job_dir: Path,
    task: str,
    load_run: str | None,
    checkpoint: int | None,
    meta: dict,
    legacy: Path,
) -> Path:
    """将 fetched_models 迁移到 logs 布局（v0.2 兼容）。"""
    if not load_run:
        load_run = meta.get("load_run") or "legacy_import"
    if checkpoint is None:
        checkpoint = checkpoint_int_from_filename(legacy.name)
        if checkpoint is None:
            gm_spec = meta.get("gm_checkpoint", "latest")
            checkpoint = checkpoint_int_from_spec(gm_spec, legacy.name)

    dest_dir = logs_export_dir(job_dir, task, load_run)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"model_{int(checkpoint)}.pt"
    if not dest.is_file():
        shutil.copy2(legacy, dest)
    return dest
