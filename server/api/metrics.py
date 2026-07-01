from typing import Optional

from fastapi import APIRouter, HTTPException

import database
from models import MetricBatchCreate, MetricCreate, MetricResponse

router = APIRouter(prefix="/jobs", tags=["metrics"])


@router.post("/{job_id}/metrics")
async def append_metrics(job_id: str, req: MetricBatchCreate):
    """Agent 上报训练指标（支持批量）。"""
    conn = database.get_connection()
    try:
        # 检查任务是否存在
        row = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Job {job_id} not found")

        for m in req.metrics:
            conn.execute(
                "INSERT INTO metrics (job_id, step, loss, reward, lr, kind) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, m.step, m.loss, m.reward, m.lr, m.kind or "train"),
            )
        conn.commit()
        return {"status": "ok", "count": len(req.metrics)}
    finally:
        conn.close()


@router.get("/{job_id}/metrics", response_model=list[MetricResponse])
async def get_metrics(
    job_id: str,
    limit: Optional[int] = None,
    since_step: Optional[int] = None,
    kind: Optional[str] = None,
):
    """查询任务指标。

    Args:
        limit: 返回最近 N 条记录。
        since_step: 返回 step > 此值的记录。
    """
    conn = database.get_connection()
    try:
        query = "SELECT step, loss, reward, lr, kind, timestamp FROM metrics WHERE job_id=?"
        params: list = [job_id]

        if since_step is not None:
            query += " AND step > ?"
            params.append(since_step)
        if kind is not None:
            query += " AND kind=?"
            params.append(kind)

        query += " ORDER BY step ASC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [
            MetricResponse(
                step=r["step"],
                loss=r["loss"],
                reward=r["reward"],
                lr=r["lr"],
                kind=r["kind"] if "kind" in r.keys() else "train",
                timestamp=r["timestamp"],
            )
            for r in rows
        ]
    finally:
        conn.close()
