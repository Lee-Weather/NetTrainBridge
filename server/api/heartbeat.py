from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

import database
from models import HeartbeatRequest, HeartbeatResponse

router = APIRouter(prefix="/jobs", tags=["heartbeat"])


@router.post("/{job_id}/heartbeat")
async def send_heartbeat(job_id: str, req: HeartbeatRequest):
    """Agent 上报心跳（GPU 状态等）。"""
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Job {job_id} not found")

        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO heartbeats "
            "(job_id, agent_id, gpu_util, gpu_mem_used, gpu_mem_total, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                job_id, req.agent_id, req.gpu_util,
                req.gpu_mem_used, req.gpu_mem_total, now,
            ),
        )
        conn.commit()
        return {"status": "ok", "timestamp": now}
    finally:
        conn.close()


@router.get("/{job_id}/heartbeat", response_model=HeartbeatResponse)
async def get_latest_heartbeat(job_id: str):
    """查询任务最新一条心跳。"""
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT agent_id, gpu_util, gpu_mem_used, gpu_mem_total, timestamp "
            "FROM heartbeats WHERE job_id=? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, f"No heartbeat for job {job_id}")
        return HeartbeatResponse(
            agent_id=row["agent_id"],
            gpu_util=row["gpu_util"],
            gpu_mem_used=row["gpu_mem_used"],
            gpu_mem_total=row["gpu_mem_total"],
            timestamp=row["timestamp"],
        )
    finally:
        conn.close()


@router.get("/{job_id}/heartbeats", response_model=list[HeartbeatResponse])
async def list_heartbeats(job_id: str, limit: Optional[int] = 20):
    """查询任务心跳历史。"""
    conn = database.get_connection()
    try:
        query = (
            "SELECT agent_id, gpu_util, gpu_mem_used, gpu_mem_total, timestamp "
            "FROM heartbeats WHERE job_id=? ORDER BY id DESC"
        )
        params: list = [job_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [
            HeartbeatResponse(
                agent_id=r["agent_id"],
                gpu_util=r["gpu_util"],
                gpu_mem_used=r["gpu_mem_used"],
                gpu_mem_total=r["gpu_mem_total"],
                timestamp=r["timestamp"],
            )
            for r in rows
        ]
    finally:
        conn.close()
