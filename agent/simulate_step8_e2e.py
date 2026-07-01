#!/usr/bin/env python3
"""步骤 8 E2E 模拟：不启 Agent/git，验证 test 全流程 API + Mock 脚本。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TEST_SCRIPT = (
    _REPO_ROOT / "contrib/agi_origin/humanoid/scripts/test_with_metrics.py"
)
DEFAULT_BASE = os.environ.get("NETTRAINBRIDGE_SERVER_URL", "http://127.0.0.1:8000")


def _post(base: str, path: str, **kwargs) -> dict:
    r = httpx.post(f"{base.rstrip('/')}{path}", timeout=30, **kwargs)
    r.raise_for_status()
    return r.json() if r.content else {}


def _put(base: str, path: str, **kwargs) -> dict:
    r = httpx.put(f"{base.rstrip('/')}{path}", timeout=30, **kwargs)
    r.raise_for_status()
    return r.json()


def _get(base: str, path: str) -> httpx.Response:
    return httpx.get(f"{base.rstrip('/')}{path}", timeout=30)


def _upload_checkpoint(base: str, job_id: str, file_path: Path) -> None:
    with open(file_path, "rb") as f:
        r = httpx.post(
            f"{base.rstrip('/')}/jobs/{job_id}/checkpoint",
            params={"chunk_index": 0, "total_chunks": 1},
            files={"file": (file_path.name, f, "application/octet-stream")},
            timeout=60,
        )
    r.raise_for_status()


def _upload_test_file(base: str, job_id: str, file_path: Path) -> None:
    with open(file_path, "rb") as f:
        r = httpx.post(
            f"{base.rstrip('/')}/jobs/{job_id}/test/{file_path.name}",
            files={"file": (file_path.name, f, "application/octet-stream")},
            timeout=60,
        )
    r.raise_for_status()


def _run_mock_test(work_dir: Path, job_id: str, checkpoint: Path) -> Path:
    """本地跑 test_with_metrics --mock，返回 summary.json 路径。"""
    metrics = work_dir / "metrics.jsonl"
    env = os.environ.copy()
    env["NETTRAINBRIDGE_JOB_ID"] = job_id
    env["NETTRAINBRIDGE_METRICS_FILE"] = str(metrics)
    subprocess.run(
        [
            sys.executable,
            str(_TEST_SCRIPT),
            "--mock",
            "--checkpoint",
            str(checkpoint),
            "--mock-steps",
            "2",
        ],
        cwd=work_dir,
        env=env,
        check=True,
    )
    summary = work_dir / "test" / "summary.json"
    if not summary.is_file():
        raise RuntimeError(f"summary 未生成: {summary}")
    return summary


def _post_metrics_from_jsonl(base: str, job_id: str, metrics_file: Path) -> int:
    metrics = []
    for line in metrics_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        metrics.append(
            {
                "step": rec["step"],
                "loss": rec.get("loss"),
                "reward": rec.get("reward"),
                "lr": rec.get("lr"),
                "kind": rec.get("kind", "test"),
            },
        )
    _post(base, f"/jobs/{job_id}/metrics", json={"metrics": metrics})
    return len(metrics)


def simulate_ntb_path(base: str) -> str:
    """路径 B：ntb train → test（无 gm fetch）。"""
    train = _post(
        base,
        "/jobs",
        json={
            "repo_url": "https://github.com/test/step8-train.git",
            "commit_sha": "step8_train",
            "job_type": "train",
        },
    )
    train_id = train["id"]
    ckpt = Path(tempfile.gettempdir()) / f"step8_train_{train_id}.pt"
    ckpt.write_bytes(b"mock train model")
    _upload_checkpoint(base, train_id, ckpt)
    _put(
        base,
        f"/jobs/{train_id}/meta",
        json={"model_filename": ckpt.name, "train_source": "ntb"},
    )

    test = _post(
        base,
        "/jobs",
        json={
            "repo_url": "https://github.com/test/step8-test-ntb.git",
            "commit_sha": "step8_ntb",
            "job_type": "test",
            "parent_train_job_id": train_id,
        },
    )
    test_id = test["id"]
    _put(base, f"/jobs/{test_id}/claim", json={"agent_id": "step8-mock"})
    _put(base, f"/jobs/{test_id}/status", json={"status": "RUNNING"})
    _put(base, f"/jobs/{test_id}/phase", json={"phase": "test"})

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        parent_ckpt = work / ckpt.name
        r = _get(base, f"/jobs/{train_id}/checkpoint/{ckpt.name}")
        r.raise_for_status()
        parent_ckpt.write_bytes(r.content)

        summary = _run_mock_test(work, test_id, parent_ckpt)
        metrics_file = work / "metrics.jsonl"
        count = _post_metrics_from_jsonl(base, test_id, metrics_file)
        _upload_test_file(base, test_id, summary)
        _upload_test_file(base, test_id, metrics_file)

    _put(base, f"/jobs/{test_id}/phase", json={"phase": "done"})
    _put(base, f"/jobs/{test_id}/status", json={"status": "COMPLETED"})

    job = _get(base, f"/jobs/{test_id}").json()
    assert job["status"] == "COMPLETED", job
    assert _get(base, f"/jobs/{test_id}/test/summary.json").status_code == 200
    mets = _get(base, f"/jobs/{test_id}/metrics?kind=test").json()
    assert len(mets) >= 2, mets
    print(f"  ntb path OK job={test_id} metrics={count}")
    return test_id


def simulate_gm_path(base: str) -> str:
    """路径 A：gm test（跳过真实 FETCH，直接上传 models/）。"""
    test = _post(
        base,
        "/jobs",
        json={
            "repo_url": "https://github.com/test/step8-test-gm.git",
            "commit_sha": "step8_gm",
            "job_type": "test",
            "gm_task_id": "task_step8_mock",
            "gm_checkpoint": "latest",
        },
    )
    test_id = test["id"]
    ckpt = Path(tempfile.gettempdir()) / f"step8_gm_{test_id}.pt"
    ckpt.write_bytes(b"mock gm model")
    _upload_checkpoint(base, test_id, ckpt)
    _put(
        base,
        f"/jobs/{test_id}/meta",
        json={
            "model_filename": ckpt.name,
            "gm_task_id": "task_step8_mock",
            "gm_checkpoint": "latest",
        },
    )
    _put(base, f"/jobs/{test_id}/phase", json={"phase": "test"})

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        local_ckpt = work / ckpt.name
        r = _get(base, f"/jobs/{test_id}/checkpoint/{ckpt.name}")
        r.raise_for_status()
        local_ckpt.write_bytes(r.content)

        summary = _run_mock_test(work, test_id, local_ckpt)
        _post_metrics_from_jsonl(base, test_id, work / "metrics.jsonl")
        _upload_test_file(base, test_id, summary)

    _put(base, f"/jobs/{test_id}/phase", json={"phase": "done"})
    _put(base, f"/jobs/{test_id}/status", json={"status": "COMPLETED"})

    assert _get(base, f"/jobs/{test_id}/test/summary.json").status_code == 200
    meta = _get(base, f"/jobs/{test_id}/meta").json()
    assert meta.get("gm_task_id") == "task_step8_mock"
    print(f"  gm path OK job={test_id}")
    return test_id


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE
    if not _TEST_SCRIPT.is_file():
        print(f"缺少测试脚本: {_TEST_SCRIPT}", file=sys.stderr)
        return 1
    health = httpx.get(f"{base.rstrip('/')}/health", timeout=10)
    health.raise_for_status()

    print("simulate_step8_e2e:")
    simulate_ntb_path(base)
    simulate_gm_path(base)
    print("simulate_step8_e2e passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
