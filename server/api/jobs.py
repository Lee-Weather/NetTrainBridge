import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

import database
from models import (
    JobClaim,
    JobCreate,
    JobResponse,
    JobStatus,
    JobStatusUpdate,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


def normalize_repo_url(repo_url: str) -> str:
    """规范化仓库 URL，便于白名单与去重比较。"""
    url = repo_url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url.lower()


def _row_to_response(row) -> JobResponse:
    """将 SQLite Row 转为 Pydantic 响应模型。"""
    return JobResponse(
        id=row["id"],
        status=row["status"],
        repo_url=row["repo_url"],
        commit_sha=row["commit_sha"],
        agent_id=row["agent_id"],
        create_time=row["create_time"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        error_msg=row["error_msg"],
    )


@router.get("/pending", response_model=list[JobResponse])
async def list_pending():
    """返回所有 PENDING 状态的任务（Agent 轮询用）。"""
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status='PENDING' ORDER BY create_time ASC"
        ).fetchall()
        return [_row_to_response(r) for r in rows]
    finally:
        conn.close()


@router.get("", response_model=list[JobResponse])
async def list_jobs(status: Optional[str] = None, limit: int = 100):
    """返回任务列表，支持 status 过滤和 limit 限制，默认按 create_time DESC。"""
    conn = database.get_connection()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY create_time DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY create_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_response(r) for r in rows]
    finally:
        conn.close()


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(req: JobCreate):
    """创建新任务（手动 curl 或 Webhook 调用）。"""
    return create_job_sync(req)


def create_job_sync(req: JobCreate) -> JobResponse:
    """同步创建任务（Webhook 后台任务等场景复用）。"""
    job_id = req.id or uuid.uuid4().hex[:12]
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO jobs (id, repo_url, commit_sha, create_time) VALUES (?, ?, ?, ?)",
            (job_id, req.repo_url, req.commit_sha, datetime.utcnow().isoformat()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _row_to_response(row)
    finally:
        conn.close()


def find_job_by_repo_commit(repo_url: str, commit_sha: str) -> Optional[JobResponse]:
    """按仓库 + commit 查找已有任务（用于 Webhook 去重）。"""
    target_repo = normalize_repo_url(repo_url)
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE commit_sha=? ORDER BY create_time DESC",
            (commit_sha,),
        ).fetchall()
        for row in rows:
            if normalize_repo_url(row["repo_url"]) == target_repo:
                return _row_to_response(row)
        return None
    finally:
        conn.close()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """查询单个任务详情。"""
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Job {job_id} not found")
        return _row_to_response(row)
    finally:
        conn.close()


@router.put("/{job_id}/claim", response_model=JobResponse)
async def claim_job(job_id: str, req: JobClaim):
    """Agent 抢占任务（乐观锁：仅当状态仍为 PENDING 时原子更新）。"""
    conn = database.get_connection()
    try:
        cursor = conn.execute(
            "UPDATE jobs SET status=?, agent_id=?, start_time=? "
            "WHERE id=? AND status='PENDING'",
            (JobStatus.ASSIGNED.value, req.agent_id,
             datetime.utcnow().isoformat(), job_id),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(409, "Job already assigned or not found")
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _row_to_response(row)
    finally:
        conn.close()


@router.put("/{job_id}/status", response_model=JobResponse)
async def update_job_status(job_id: str, req: JobStatusUpdate):
    """Agent 更新任务状态（RUNNING/COMPLETED/FAILED）。"""
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Job {job_id} not found")

        now = datetime.utcnow().isoformat()
        if req.status == JobStatus.COMPLETED or req.status == JobStatus.FAILED:
            conn.execute(
                "UPDATE jobs SET status=?, end_time=?, error_msg=? WHERE id=?",
                (req.status.value, now, req.error_msg, job_id),
            )
        else:
            conn.execute(
                "UPDATE jobs SET status=?, error_msg=? WHERE id=?",
                (req.status.value, req.error_msg, job_id),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _row_to_response(row)
    finally:
        conn.close()
