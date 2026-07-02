import asyncio
from collections import deque
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from config import ServerConfig
from models import LogMessage, LogResponse

router = APIRouter(prefix="/jobs", tags=["logs"])

# 内存日志缓存: job_id -> deque(maxlen=5000)
_log_cache: dict[str, deque] = {}
_config = ServerConfig.load()


def _get_log_buffer(job_id: str) -> deque:
    """获取或创建任务的日志缓冲区。"""
    if job_id not in _log_cache:
        _log_cache[job_id] = deque(maxlen=_config.LOG_MAX_LINES)
    return _log_cache[job_id]


@router.post("/{job_id}/logs")
async def append_logs(job_id: str, req: LogMessage):
    """Agent 上报训练日志。"""
    buffer = _get_log_buffer(job_id)
    buffer.append(req.content)
    return {"status": "ok", "lines": len(buffer)}


@router.get("/{job_id}/logs/stream")
async def stream_logs(job_id: str):
    """SSE 实时推送任务日志（每 1s 检查缓存增量）。"""

    async def event_generator():
        last_count = 0
        while True:
            buffer = _get_log_buffer(job_id)
            if len(buffer) > last_count:
                for line in list(buffer)[last_count:]:
                    yield f"data: {line}\n\n"
                last_count = len(buffer)
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}/logs", response_model=LogResponse)
async def get_logs(job_id: str, tail: Optional[int] = None):
    """查询任务日志。

    Args:
        tail: 返回最后 N 行，默认返回全部。
    """
    buffer = _get_log_buffer(job_id)
    logs = list(buffer)

    if tail:
        logs = logs[-tail:]

    return LogResponse(logs=logs)


@router.delete("/{job_id}/logs")
async def clear_logs(job_id: str):
    """清空任务日志缓存。"""
    if job_id in _log_cache:
        _log_cache[job_id].clear()
    return {"status": "ok"}


def drop_job_logs(job_id: str) -> None:
    """移除内存中的任务日志缓存。"""
    _log_cache.pop(job_id, None)


def drop_all_logs() -> None:
    """清空全部内存日志缓存。"""
    _log_cache.clear()
