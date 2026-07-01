import os
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from config import ServerConfig
import database
import job_data

router = APIRouter(prefix="/jobs", tags=["checkpoint"])

_config = ServerConfig.load()

# 分片上传状态: job_id -> {filename, total_chunks, received_chunks}
_upload_sessions: dict[str, dict] = {}


def _job_dir(job_id: str) -> Path:
    """获取任务的数据目录。"""
    return job_data.job_dir(job_id)


def _temp_dir(job_id: str) -> Path:
    """获取分片上传临时目录。"""
    return _job_dir(job_id) / ".tmp"


def _ensure_job_exists(job_id: str) -> None:
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Job {job_id} not found")
    finally:
        conn.close()


def _resolve_checkpoint_path(job_id: str, filename: str) -> Path:
    """models/ 优先，兼容 v0.1 根目录。"""
    models_path = job_data.models_dir(job_id) / filename
    if models_path.is_file():
        return models_path
    legacy = _job_dir(job_id) / filename
    if legacy.is_file():
        return legacy
    raise HTTPException(404, f"File {filename} not found for job {job_id}")


def _list_checkpoint_files(job_id: str) -> list[dict]:
    """扫描 models/ 与旧版根目录中的 checkpoint 文件。"""
    seen: set[str] = set()
    files: list[dict] = []
    meta = job_data.read_meta(job_id) or {}
    primary = meta.get("model_filename")

    def _add(path: Path, location: str) -> None:
        if not path.is_file() or path.name in seen:
            return
        seen.add(path.name)
        files.append(
            {
                "filename": path.name,
                "size": path.stat().st_size,
                "location": location,
                "primary": path.name == primary if primary else False,
            },
        )

    models = job_data.models_dir(job_id)
    if models.is_dir():
        for path in sorted(models.iterdir()):
            if path.is_file() and not path.name.startswith("."):
                _add(path, "models")
    job_root = _job_dir(job_id)
    if job_root.is_dir():
        for path in sorted(job_root.iterdir()):
            if path.is_file() and path.suffix == ".pt":
                _add(path, "legacy")

    if primary and not any(f["filename"] == primary for f in files):
        files.insert(
            0,
            {
                "filename": primary,
                "size": None,
                "location": "meta",
                "primary": True,
            },
        )
    return files


@router.get("/{job_id}/checkpoint")
async def list_checkpoints(job_id: str):
    """列出任务 checkpoint 文件（含 meta.json 中的主模型名）。"""
    _ensure_job_exists(job_id)
    meta = job_data.read_meta(job_id)
    return {
        "job_id": job_id,
        "files": _list_checkpoint_files(job_id),
        "meta": meta,
    }


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
        models = job_data.models_dir(job_id)
        models.mkdir(parents=True, exist_ok=True)
        final_path = models / filename
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
    file_path = _resolve_checkpoint_path(job_id, filename)

    from fastapi.responses import FileResponse
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )
