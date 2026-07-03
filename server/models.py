from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── 枚举 ──

class JobStatus(str, Enum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobType(str, Enum):
    TRAIN = "train"
    SYNC = "sync"
    TEST = "test"


class TrainSource(str, Enum):
    NTB = "ntb"
    GM = "gm"


class JobPhase(str, Enum):
    SYNC = "sync"
    FETCH = "fetch"
    PULL = "pull"
    TEST = "test"
    DONE = "done"


# ── 任务相关 ──

class JobCreate(BaseModel):
    """创建任务请求"""
    repo_url: str
    commit_sha: str
    id: Optional[str] = None  # 可选，不传则自动生成
    job_type: JobType = JobType.TRAIN
    train_source: Optional[TrainSource] = None
    gm_task_id: Optional[str] = None
    gm_checkpoint: Optional[str] = None
    load_run: Optional[str] = None
    task: Optional[str] = None
    checkpoint: Optional[int] = None
    parent_train_job_id: Optional[str] = None
    phase: Optional[JobPhase] = None
    checkpoint_staged: Optional[bool] = None
    fetch_mode: Optional[str] = None  # server | gm


class JobClaim(BaseModel):
    """Agent 抢占任务请求"""
    agent_id: str


class JobStatusUpdate(BaseModel):
    """更新任务状态请求"""
    status: JobStatus
    error_msg: Optional[str] = None


class JobPhaseUpdate(BaseModel):
    """更新任务阶段请求（test job 状态机）"""
    phase: JobPhase


class JobResponse(BaseModel):
    """任务响应"""
    id: str
    status: str
    repo_url: str
    commit_sha: str
    agent_id: Optional[str] = None
    create_time: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    error_msg: Optional[str] = None
    job_type: str = "train"
    train_source: str = "ntb"
    gm_task_id: Optional[str] = None
    parent_train_job_id: Optional[str] = None
    phase: Optional[str] = None


# ── 指标相关 ──

class MetricCreate(BaseModel):
    """单条指标上报"""
    step: int
    loss: Optional[float] = None
    reward: Optional[float] = None
    lr: Optional[float] = None
    kind: str = "train"


class MetricBatchCreate(BaseModel):
    """批量指标上报"""
    metrics: list[MetricCreate]


class MetricResponse(BaseModel):
    """指标响应"""
    step: int
    loss: Optional[float] = None
    reward: Optional[float] = None
    lr: Optional[float] = None
    kind: str = "train"
    timestamp: Optional[str] = None


# ── 日志相关 ──

class LogMessage(BaseModel):
    """日志上报"""
    content: str


class LogResponse(BaseModel):
    """日志响应"""
    logs: list[str]


# ── 心跳相关 ──

class HeartbeatRequest(BaseModel):
    """Agent 心跳上报"""
    agent_id: str
    gpu_util: Optional[float] = None
    gpu_mem_used: Optional[float] = None
    gpu_mem_total: Optional[float] = None


class HeartbeatResponse(BaseModel):
    """心跳响应"""
    agent_id: str
    gpu_util: Optional[float] = None
    gpu_mem_used: Optional[float] = None
    gpu_mem_total: Optional[float] = None
    timestamp: Optional[str] = None


# ── Checkpoint 相关 ──

class CheckpointUploadRequest(BaseModel):
    """分片上传元数据"""
    filename: str
    chunk_index: int
    total_chunks: int


class CheckpointUploadComplete(BaseModel):
    """分片上传完成通知"""
    filename: str
    total_chunks: int
