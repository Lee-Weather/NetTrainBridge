import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

import database
import job_data

router = APIRouter(prefix="/jobs", tags=["test"])

_SAFE_NAME = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def _safe_filename(name: str) -> str:
    base = os.path.basename(name.strip())
    if not base or not all(c in _SAFE_NAME for c in base):
        raise HTTPException(400, f"invalid filename: {name}")
    return base


@router.post("/{job_id}/test/{filename}")
async def upload_test_file(job_id: str, filename: str, file: UploadFile):
    """Agent 上传 sim2sim 测试产物到 data/{id}/test/。"""
    filename = _safe_filename(filename)
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Job {job_id} not found")
    finally:
        conn.close()

    dest_dir = job_data.test_dir(job_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)
    return {"status": "ok", "filename": filename, "size": len(content)}


@router.get("/{job_id}/test/{filename}")
async def download_test_file(job_id: str, filename: str):
    """下载测试产物。"""
    filename = _safe_filename(filename)
    path = job_data.test_dir(job_id) / filename
    if not path.is_file():
        raise HTTPException(404, f"File {filename} not found for job {job_id}")

    from fastapi.responses import FileResponse

    return FileResponse(
        path=str(path),
        filename=filename,
        media_type="application/octet-stream",
    )
