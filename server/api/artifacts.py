"""测试产物列表与打包下载。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

import database
import job_data

router = APIRouter(prefix="/jobs", tags=["artifacts"])

_SKIP_DIRS = frozenset({".tmp", "__pycache__"})


def _ensure_job_exists(job_id: str) -> None:
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Job {job_id} not found")
    finally:
        conn.close()


def _list_test_files(job_id: str) -> list[dict]:
    """递归列出 data/{id}/test/ 下文件（相对 test/ 的路径）。"""
    base = job_data.test_dir(job_id)
    if not base.is_dir():
        return []

    files: list[dict] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base).as_posix()
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        files.append(
            {
                "path": rel,
                "filename": path.name,
                "size": path.stat().st_size,
            },
        )
    return files


def _zip_test_dir(job_id: str) -> io.BytesIO:
    base = job_data.test_dir(job_id)
    if not base.is_dir():
        raise HTTPException(404, f"No test artifacts for job {job_id}")

    files = _list_test_files(job_id)
    if not files:
        raise HTTPException(404, f"No test artifacts for job {job_id}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in files:
            disk = base / entry["path"]
            zf.write(disk, arcname=entry["path"])
    buf.seek(0)
    return buf


@router.get("/{job_id}/artifacts")
async def list_artifacts(job_id: str):
    """列出 test job 测试产物（data/{id}/test/）。"""
    _ensure_job_exists(job_id)
    return {
        "job_id": job_id,
        "files": _list_test_files(job_id),
    }


@router.get("/{job_id}/artifacts/download")
async def download_artifacts_zip(job_id: str):
    """打包下载 test/ 目录为 zip。"""
    _ensure_job_exists(job_id)
    buf = _zip_test_dir(job_id)
    filename = f"{job_id}-artifacts.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
