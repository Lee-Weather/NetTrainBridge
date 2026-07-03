"""CLI：checkpoint 上传到 Server。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

CHUNK_SIZE = 4 * 1024 * 1024
REQUEST_TIMEOUT = 120.0


def put_job_meta(job_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    from nettrainbridge_cli.main import request_json

    return request_json("PUT", f"/jobs/{job_id}/meta", json=meta)


def upload_checkpoint(job_id: str, file_path: Path) -> dict[str, Any]:
    """分片上传 checkpoint 到 Server（与 Agent 协议一致）。"""
    from nettrainbridge_cli.main import CLIError, auth_headers, server_url

    if not file_path.is_file():
        raise CLIError(f"文件不存在: {file_path}")

    file_size = file_path.stat().st_size
    total_chunks = max(1, (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE)
    filename = file_path.name
    url = server_url().rstrip("/") + f"/jobs/{job_id}/checkpoint"
    result: dict[str, Any] = {}

    with httpx.Client(timeout=REQUEST_TIMEOUT, headers=auth_headers()) as client:
        with open(file_path, "rb") as handle:
            for chunk_index in range(total_chunks):
                chunk_data = handle.read(CHUNK_SIZE)
                response = client.post(
                    url,
                    params={
                        "chunk_index": chunk_index,
                        "total_chunks": total_chunks,
                    },
                    files={"file": (filename, chunk_data, "application/octet-stream")},
                )
                if response.status_code >= 400:
                    raise CLIError(
                        f"上传失败 HTTP {response.status_code}: {response.text[:300]}",
                    )
                result = response.json()

    return result
