"""test job PULL 阶段：从 Server 下载 checkpoint 到同窗 logs 布局。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from api_client import APIClient, APIError
from checkpoint_layout import (
    DEFAULT_TEST_TASK,
    checkpoint_int_from_filename,
    logs_export_dir,
    model_path_in_logs,
)

logger = logging.getLogger("nettrainbridge.agent.pull")

PULL_POLL_INTERVAL = 10
PULL_MAX_ATTEMPTS = 18  # ~3 分钟


class PullRunnerError(Exception):
    """PULL 阶段失败。"""


async def wait_for_server_checkpoint(
    api_client: APIClient,
    job_id: str,
    filename: str,
    *,
    attempts: int = PULL_MAX_ATTEMPTS,
    interval: float = PULL_POLL_INTERVAL,
) -> None:
    """轮询直到 Server models/ 出现指定文件。"""
    last_err: str | None = None
    for attempt in range(1, attempts + 1):
        try:
            files = await api_client.list_checkpoints(job_id)
            names = {f.get("filename") for f in files if isinstance(f, dict)}
            if filename in names:
                logger.info(
                    "Server checkpoint 就绪 job=%s file=%s (第 %d 次)",
                    job_id,
                    filename,
                    attempt,
                )
                return
            last_err = f"Server 尚无 {filename}"
        except APIError as exc:
            last_err = str(exc)
        if attempt < attempts:
            logger.info(
                "等待家里上传 checkpoint (%d/%d): %s",
                attempt,
                attempts,
                last_err or "unknown",
            )
            await asyncio.sleep(interval)
    raise PullRunnerError(
        f"等待 Server checkpoint 超时: {last_err or filename}。"
        "请确认家里已执行 ntb checkpoint stage-from-gm 或 upload",
    )


async def pull_checkpoint_to_logs(
    api_client: APIClient,
    job_id: str,
    job_dir: Path,
    meta: dict,
) -> Path:
    """从 Server 本 job 下载模型到 logs/.../exported_data/{load_run}/。"""
    task = meta.get("task") or DEFAULT_TEST_TASK
    load_run = meta.get("load_run")
    if not load_run:
        raise PullRunnerError("test job 缺少 load_run")

    checkpoint = meta.get("checkpoint")
    filename = meta.get("model_filename")
    if not filename:
        if checkpoint is not None:
            filename = f"model_{int(checkpoint)}.pt"
        else:
            raise PullRunnerError("meta 缺少 model_filename / checkpoint")

    if checkpoint is None:
        checkpoint = checkpoint_int_from_filename(filename)
    if checkpoint is None:
        raise PullRunnerError(f"无法解析 checkpoint: {filename}")

    dest = model_path_in_logs(job_dir, task, load_run, int(checkpoint))
    dest.parent.mkdir(parents=True, exist_ok=True)

    await wait_for_server_checkpoint(api_client, job_id, filename)
    await api_client.download_checkpoint(job_id, filename, dest)

    logger.info("PULL 完成 job=%s -> %s", job_id, dest)
    return dest
