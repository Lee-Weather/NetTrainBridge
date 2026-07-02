#!/usr/bin/env python3
"""清空全部任务 API 单元测试（使用临时 DB 与 data 目录）。"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SERVER_DIR.parent


def test_clear_all_jobs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "data"
        db_path = Path(tmp) / "server.db"
        data_dir.mkdir()

        os.environ["NETTRAINBRIDGE_DATA_DIR"] = str(data_dir)
        os.environ["NETTRAINBRIDGE_DB_PATH"] = str(db_path)

        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        if str(_SERVER_DIR) not in sys.path:
            sys.path.insert(0, str(_SERVER_DIR))

        import importlib

        import database
        import job_data
        from api.jobs import clear_all_jobs_sync, create_job_sync
        from models import JobCreate

        importlib.reload(database)
        importlib.reload(job_data)
        import api.jobs as jobs_api

        importlib.reload(jobs_api)

        database.init_db()

        j1 = create_job_sync(
            JobCreate(
                repo_url="https://github.com/test/clear-1.git",
                commit_sha="c1",
            ),
        )
        j2 = create_job_sync(
            JobCreate(
                repo_url="https://github.com/test/clear-2.git",
                commit_sha="c2",
            ),
        )
        assert job_data.job_dir(j1.id).is_dir()
        assert job_data.job_dir(j2.id).is_dir()

        orphan = data_dir / "orphan_job"
        orphan.mkdir()
        (orphan / "meta.json").write_text("{}", encoding="utf-8")

        conn = sqlite3.connect(db_path)
        try:
            assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 2
        finally:
            conn.close()

        result = clear_all_jobs_sync()
        assert result["deleted_jobs"] == 2
        assert result["deleted_dirs"] == 3
        assert result["orphan_dirs"] == 1

        conn = sqlite3.connect(db_path)
        try:
            assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
        finally:
            conn.close()

        assert not any(data_dir.iterdir())


if __name__ == "__main__":
    test_clear_all_jobs()
    print("test_clear_all_jobs passed")
