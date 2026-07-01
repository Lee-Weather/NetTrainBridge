from typing import Any

from fastapi import APIRouter, HTTPException

import database
import job_data

router = APIRouter(prefix="/jobs", tags=["meta"])


def _ensure_job_exists(job_id: str) -> None:
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Job {job_id} not found")
    finally:
        conn.close()


@router.get("/{job_id}/meta")
async def get_job_meta(job_id: str) -> dict[str, Any]:
    """读取任务 meta.json。"""
    _ensure_job_exists(job_id)
    meta = job_data.read_meta(job_id)
    if meta is None:
        raise HTTPException(404, f"meta not found for job {job_id}")
    return meta


@router.put("/{job_id}/meta")
async def put_job_meta(job_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """合并写入任务 meta.json。"""
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a JSON object")
    _ensure_job_exists(job_id)
    return job_data.merge_meta(job_id, body)
