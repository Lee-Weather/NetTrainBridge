from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import httpx

from config import AgentConfig

logger = logging.getLogger("nettrainbridge.agent")


class APIError(Exception):
    """与云服务器通信失败时抛出。"""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class APIClient:
    """云服务器 API 客户端，封装所有 HTTP 请求。"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 httpx 异步客户端。"""
        if self._client is None or self._client.is_closed:
            kwargs: dict = {
                "base_url": self.config.server_url,
                "timeout": self.config.request_timeout,
            }
            if self.config.proxy:
                kwargs["proxy"] = self.config.proxy  # httpx >= 0.28 使用 proxy (单数)
            self._client = httpx.AsyncClient(**kwargs)
        return self._client

    async def close(self):
        """关闭客户端连接。"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        retry_on_failure: bool = True,
        **kwargs,
    ) -> httpx.Response:
        """发送 HTTP 请求，支持重试。"""
        client = await self._get_client()
        last_error: Exception | None = None

        attempts = self.config.max_retries if retry_on_failure else 1
        for attempt in range(attempts):
            try:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                # 4xx 错误不重试 (除了 429 限流)
                if e.response.status_code < 500 and e.response.status_code != 429:
                    raise APIError(
                        f"请求失败: {method} {path} -> {e.response.status_code}: {e.response.text}",
                        status_code=e.response.status_code,
                    )
                last_error = e
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e

            if attempt < attempts - 1:
                wait = 2 ** attempt  # 指数退避: 1s, 2s, 4s
                logger.warning(
                    "请求失败 %s %s (尝试 %d/%d), %s 后重试: %s",
                    method, path, attempt + 1, attempts, wait, last_error,
                )
                import asyncio
                await asyncio.sleep(wait)

        raise APIError(
            f"请求失败 (已重试 {attempts} 次): {method} {path} -> {last_error}",
        )

    # ── 任务接口 ──

    async def get_pending_jobs(self) -> list[dict]:
        """获取待处理任务列表。"""
        response = await self._request("GET", "/jobs/pending")
        return response.json()

    async def get_job(self, job_id: str) -> dict:
        """查询单个任务详情。"""
        response = await self._request("GET", f"/jobs/{job_id}")
        return response.json()

    async def claim_job(self, job_id: str) -> dict:
        """抢占任务。"""
        response = await self._request(
            "PUT",
            f"/jobs/{job_id}/claim",
            json={"agent_id": self.config.agent_id},
        )
        return response.json()

    async def update_status(
        self,
        job_id: str,
        status: str,
        error_msg: Optional[str] = None,
    ) -> dict:
        """更新任务状态。"""
        payload: dict = {"status": status}
        if error_msg is not None:
            payload["error_msg"] = error_msg
        response = await self._request(
            "PUT", f"/jobs/{job_id}/status", json=payload,
        )
        return response.json()

    # ── 日志接口 ──

    async def append_logs(self, job_id: str, content: str) -> dict:
        """上报训练日志。"""
        response = await self._request(
            "POST",
            f"/jobs/{job_id}/logs",
            json={"content": content},
        )
        return response.json()

    # ── 指标接口 ──

    async def append_metrics(self, job_id: str, metrics: list[dict]) -> dict:
        """批量上报训练指标。

        metrics 格式: [{"step": 100, "loss": 0.5, "reward": 1.2}, ...]
        """
        response = await self._request(
            "POST",
            f"/jobs/{job_id}/metrics",
            json={"metrics": metrics},
        )
        return response.json()

    # ── 心跳接口 ──

    async def send_heartbeat(
        self,
        job_id: str,
        gpu_util: Optional[float] = None,
        gpu_mem_used: Optional[float] = None,
        gpu_mem_total: Optional[float] = None,
    ) -> dict:
        """发送心跳。"""
        payload: dict = {"agent_id": self.config.agent_id}
        if gpu_util is not None:
            payload["gpu_util"] = gpu_util
        if gpu_mem_used is not None:
            payload["gpu_mem_used"] = gpu_mem_used
        if gpu_mem_total is not None:
            payload["gpu_mem_total"] = gpu_mem_total

        response = await self._request(
            "POST",
            f"/jobs/{job_id}/heartbeat",
            json=payload,
        )
        return response.json()

    # ── 任务元数据 ──

    async def put_job_meta(self, job_id: str, meta: dict) -> dict:
        """合并写入任务 meta.json。"""
        response = await self._request(
            "PUT",
            f"/jobs/{job_id}/meta",
            json=meta,
        )
        return response.json()

    async def get_job_meta(self, job_id: str) -> dict | None:
        """读取任务 meta.json；不存在时返回 None。"""
        client = await self._get_client()
        try:
            response = await client.get(f"/jobs/{job_id}/meta")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise APIError(
                f"请求失败: GET /jobs/{job_id}/meta -> {e.response.status_code}",
                status_code=e.response.status_code,
            ) from e

    async def update_phase(self, job_id: str, phase: str) -> dict:
        """更新任务阶段（test job 状态机）。"""
        response = await self._request(
            "PUT",
            f"/jobs/{job_id}/phase",
            json={"phase": phase},
        )
        return response.json()

    # ── 模型上传接口 ──

    async def list_checkpoints(self, job_id: str) -> list[dict]:
        """列出 Server 上该任务的 checkpoint 文件。"""
        response = await self._request("GET", f"/jobs/{job_id}/checkpoint")
        data = response.json()
        if isinstance(data, dict):
            files = data.get("files")
            if isinstance(files, list):
                return files
        return []

    async def upload_checkpoint(
        self,
        job_id: str,
        file_path: Path,
        chunk_size: int = 4 * 1024 * 1024,
    ) -> dict:
        """分片上传模型文件。

        Args:
            job_id: 任务 ID
            file_path: 模型文件路径
            chunk_size: 分片大小 (默认 4MB)
        """
        file_size = file_path.stat().st_size
        total_chunks = (file_size + chunk_size - 1) // chunk_size
        filename = file_path.name

        logger.info(
            "开始上传模型: %s (%.1f MB, %d 分片)",
            filename, file_size / 1024 / 1024, total_chunks,
        )

        with open(file_path, "rb") as f:
            for chunk_index in range(total_chunks):
                chunk_data = f.read(chunk_size)

                # httpx 使用 files 参数上传
                response = await self._request(
                    "POST",
                    f"/jobs/{job_id}/checkpoint",
                    params={
                        "chunk_index": chunk_index,
                        "total_chunks": total_chunks,
                    },
                    files={"file": (filename, chunk_data, "application/octet-stream")},
                )
                result = response.json()
                logger.info(
                    "上传分片 %d/%d: %s",
                    chunk_index + 1, total_chunks, result.get("status"),
                )

        return result

    async def download_checkpoint(
        self,
        job_id: str,
        filename: str,
        dest: Path,
    ) -> Path:
        """从 Server 下载模型到本地。"""
        dest.parent.mkdir(parents=True, exist_ok=True)
        client = await self._get_client()
        response = await client.get(f"/jobs/{job_id}/checkpoint/{filename}")
        if response.status_code == 404:
            raise APIError(
                f"checkpoint 不存在: {job_id}/{filename}",
                status_code=404,
            )
        response.raise_for_status()
        with open(dest, "wb") as f:
            f.write(response.content)
        logger.info("已下载 checkpoint: %s -> %s", filename, dest)
        return dest

    async def upload_test_file(
        self,
        job_id: str,
        file_path: Path,
        *,
        dest_name: str | None = None,
    ) -> dict:
        """上传测试产物到 Server data/{id}/test/。"""
        filename = dest_name or file_path.name
        with open(file_path, "rb") as f:
            response = await self._request(
                "POST",
                f"/jobs/{job_id}/test/{filename}",
                files={"file": (filename, f, "application/octet-stream")},
            )
        return response.json()
