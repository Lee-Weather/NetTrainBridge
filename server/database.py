import sqlite3
from pathlib import Path

from config import ServerConfig

_config = ServerConfig.load()

_CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id                  TEXT PRIMARY KEY,
    status              TEXT DEFAULT 'PENDING',
    repo_url            TEXT NOT NULL,
    commit_sha          TEXT NOT NULL,
    agent_id            TEXT,
    create_time         DATETIME DEFAULT CURRENT_TIMESTAMP,
    start_time          DATETIME,
    end_time            DATETIME,
    error_msg           TEXT,
    job_type            TEXT NOT NULL DEFAULT 'train',
    train_source        TEXT NOT NULL DEFAULT 'ntb',
    gm_task_id          TEXT,
    parent_train_job_id TEXT,
    phase               TEXT
);
"""

_JOB_COLUMN_MIGRATIONS: list[tuple[str, str]] = [
    ("job_type", "TEXT NOT NULL DEFAULT 'train'"),
    ("train_source", "TEXT NOT NULL DEFAULT 'ntb'"),
    ("gm_task_id", "TEXT"),
    ("parent_train_job_id", "TEXT"),
    ("phase", "TEXT"),
]

_CREATE_METRICS_TABLE = """
CREATE TABLE IF NOT EXISTS metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT NOT NULL,
    step        INTEGER NOT NULL,
    loss        REAL,
    reward      REAL,
    lr          REAL,
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
    kind        TEXT NOT NULL DEFAULT 'train',
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
"""

_METRICS_COLUMN_MIGRATIONS: list[tuple[str, str]] = [
    ("kind", "TEXT NOT NULL DEFAULT 'train'"),
]

_CREATE_HEARTBEATS_TABLE = """
CREATE TABLE IF NOT EXISTS heartbeats (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        TEXT NOT NULL,
    agent_id      TEXT NOT NULL,
    gpu_util      REAL,
    gpu_mem_used  REAL,
    gpu_mem_total REAL,
    timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
"""


def _migrate_jobs_table(conn: sqlite3.Connection) -> None:
    """为已有数据库追加 v0.2 jobs 字段（幂等）。"""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    for name, col_def in _JOB_COLUMN_MIGRATIONS:
        if name not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {col_def}")


def _migrate_metrics_table(conn: sqlite3.Connection) -> None:
    """为已有数据库追加 metrics.kind 字段（幂等）。"""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(metrics)").fetchall()}
    for name, col_def in _METRICS_COLUMN_MIGRATIONS:
        if name not in existing:
            conn.execute(f"ALTER TABLE metrics ADD COLUMN {name} {col_def}")


def get_connection() -> sqlite3.Connection:
    """获取数据库连接。"""
    conn = sqlite3.connect(_config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """初始化数据库：确保目录存在，创建表。"""
    db_path = Path(_config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    try:
        conn.execute(_CREATE_JOBS_TABLE)
        conn.execute(_CREATE_METRICS_TABLE)
        conn.execute(_CREATE_HEARTBEATS_TABLE)
        _migrate_jobs_table(conn)
        _migrate_metrics_table(conn)
        conn.commit()
    finally:
        conn.close()
