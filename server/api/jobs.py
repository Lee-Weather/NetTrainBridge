import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

import database
import job_data
from models import (
    JobClaim,
    JobCreate,
    JobPhase,
    JobPhaseUpdate,
    JobResponse,
    JobStatus,
    JobStatusUpdate,
    JobType,
    TrainSource,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


def normalize_repo_url(repo_url: str) -> str:
    """规范化仓库 URL，便于白名单与去重比较。"""
    url = repo_url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url.lower()


def _row_get(row, key: str, default=None):
    """读取 Row 字段；缺失列时返回 default（兼容极旧库）。"""
    if key not in row.keys():
        return default
    return row[key]


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
        job_type=_row_get(row, "job_type") or "train",
        train_source=_row_get(row, "train_source") or "ntb",
        gm_task_id=_row_get(row, "gm_task_id"),
        parent_train_job_id=_row_get(row, "parent_train_job_id"),
        phase=_row_get(row, "phase"),
    )


def _resolve_train_source(req: JobCreate) -> TrainSource:
    if req.train_source is not None:
        return req.train_source
    if req.job_type == JobType.TEST and req.gm_task_id:
        return TrainSource.GM
    return TrainSource.NTB


def _job_exists(job_id: str) -> bool:
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def _build_initial_meta(
    req: JobCreate,
    *,
    job_id: str,
    train_source: TrainSource,
    phase: Optional[str],
) -> dict:
    meta: dict = {
        "job_id": job_id,
        "job_type": req.job_type.value,
        "train_source": train_source.value,
        "repo_url": req.repo_url,
        "commit_sha": req.commit_sha,
    }
    if req.gm_task_id:
        meta["gm_task_id"] = req.gm_task_id
        meta["gm_checkpoint"] = req.gm_checkpoint or "latest"
    if req.parent_train_job_id:
        meta["parent_train_job_id"] = req.parent_train_job_id
    if phase:
        meta["phase"] = phase
    return meta


def _validate_job_create(req: JobCreate) -> None:
    if req.job_type == JobType.TEST:
        if not req.gm_task_id and not req.parent_train_job_id:
            raise HTTPException(
                status_code=400,
                detail="test job requires gm_task_id or parent_train_job_id",
            )
        if req.gm_task_id and req.parent_train_job_id:
            raise HTTPException(
                status_code=400,
                detail="test job accepts gm_task_id or parent_train_job_id, not both",
            )
        if req.parent_train_job_id and not _job_exists(req.parent_train_job_id):
            raise HTTPException(
                status_code=400,
                detail=f"parent_train_job_id not found: {req.parent_train_job_id}",
            )
        if req.gm_checkpoint and not req.gm_task_id:
            raise HTTPException(
                status_code=400,
                detail="gm_checkpoint requires gm_task_id",
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
async def list_jobs(
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    limit: int = 100,
):
    """返回任务列表，支持 status / job_type 过滤和 limit 限制。"""
    conn = database.get_connection()
    try:
        query = "SELECT * FROM jobs WHERE 1=1"
        params: list = []
        if status:
            query += " AND status=?"
            params.append(status)
        if job_type:
            query += " AND job_type=?"
            params.append(job_type)
        query += " ORDER BY create_time DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [_row_to_response(r) for r in rows]
    finally:
        conn.close()


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(req: JobCreate):
    """创建新任务（手动 curl 或 Webhook 调用）。"""
    return create_job_sync(req)


def create_job_sync(req: JobCreate) -> JobResponse:
    """同步创建任务（Webhook 后台任务等场景复用）。"""
    _validate_job_create(req)
    train_source = _resolve_train_source(req)
    job_id = req.id or uuid.uuid4().hex[:12]
    if req.phase:
        phase = req.phase.value
    elif req.job_type == JobType.TEST:
        phase = JobPhase.SYNC.value
    else:
        phase = None
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO jobs ("
            "id, repo_url, commit_sha, create_time, "
            "job_type, train_source, gm_task_id, parent_train_job_id, phase"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                req.repo_url,
                req.commit_sha,
                datetime.utcnow().isoformat(),
                req.job_type.value,
                train_source.value,
                req.gm_task_id,
                req.parent_train_job_id,
                phase,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    finally:
        conn.close()

    meta = _build_initial_meta(
        req,
        job_id=job_id,
        train_source=train_source,
        phase=phase,
    )
    job_data.init_job_layout(job_id, meta)
    return _row_to_response(row)


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


@router.put("/{job_id}/phase", response_model=JobResponse)
async def update_job_phase(job_id: str, req: JobPhaseUpdate):
    """Agent 更新 test job 阶段（sync → fetch → test）。"""
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Job {job_id} not found")

        phase = req.phase.value
        conn.execute(
            "UPDATE jobs SET phase=? WHERE id=?",
            (phase, job_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    finally:
        conn.close()

    job_data.merge_meta(job_id, {"phase": phase})
    return _row_to_response(row)
