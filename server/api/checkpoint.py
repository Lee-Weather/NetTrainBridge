import os
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from config import ServerConfig

router = APIRouter(prefix="/jobs", tags=["checkpoint"])

_config = ServerConfig.load()

# 分片上传状态: job_id -> {filename, total_chunks, received_chunks}
_upload_sessions: dict[str, dict] = {}


def _job_dir(job_id: str) -> Path:
    """获取任务的数据目录。"""
    return Path(_config.DATA_DIR) / job_id


def _temp_dir(job_id: str) -> Path:
    """获取分片上传临时目录。"""
    return _job_dir(job_id) / ".tmp"


@router.post("/{job_id}/checkpoint")
async def upload_chunk(
    job_id: str,
    file: UploadFile,
    chunk_index: int = 0,
    total_chunks: int = 1,
):
    """分片上传模型文件。

    - chunk_index: 当前分片序号（从 0 开始）
    - total_chunks: 总分片数
    - file: 分片文件内容
    """
    filename = file.filename or "best_model.pt"

    # 初始化上传会话
    if job_id not in _upload_sessions:
        _upload_sessions[job_id] = {
            "filename": filename,
            "total_chunks": total_chunks,
            "received": set(),
        }

    session = _upload_sessions[job_id]

    # 保存分片到临时目录
    tmp = _temp_dir(job_id)
    tmp.mkdir(parents=True, exist_ok=True)
    chunk_path = tmp / f"{filename}.part.{chunk_index}"

    content = await file.read()
    with open(chunk_path, "wb") as f:
        f.write(content)

    session["received"].add(chunk_index)

    # 所有分片到齐，合并文件
    if len(session["received"]) >= session["total_chunks"]:
        final_path = _job_dir(job_id) / filename
        with open(final_path, "wb") as out:
            for i in range(session["total_chunks"]):
                part = tmp / f"{filename}.part.{i}"
                if not part.exists():
                    raise HTTPException(400, f"Missing chunk {i}")
                with open(part, "rb") as inp:
                    shutil.copyfileobj(inp, out)

        # 清理临时文件
        shutil.rmtree(tmp, ignore_errors=True)
        del _upload_sessions[job_id]

        return {"status": "completed", "filename": filename, "size": final_path.stat().st_size}

    return {
        "status": "partial",
        "filename": filename,
        "received": len(session["received"]),
        "total": session["total_chunks"],
    }


@router.get("/{job_id}/checkpoint/{filename}")
async def download_checkpoint(job_id: str, filename: str):
    """下载模型文件。"""
    file_path = _job_dir(job_id) / filename
    if not file_path.exists():
        raise HTTPException(404, f"File {filename} not found for job {job_id}")

    from fastapi.responses import FileResponse
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )
