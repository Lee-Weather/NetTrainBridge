from collections import deque
from typing import Optional

from fastapi import APIRouter, HTTPException

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
