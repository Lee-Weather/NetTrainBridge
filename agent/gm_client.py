"""Gradmotion (gm) API 客户端 — Agent 经代理直拉 checkpoint (5B)。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

from config import AgentConfig

logger = logging.getLogger("nettrainbridge.agent.gm")


class GMClientError(Exception):
    """gm API 或下载失败。"""


def _dig(obj: Any, *keys: str) -> Any:
    """从嵌套 dict 中按多个 key 尝试取值。"""
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return None


def _extract_model_list(payload: Any) -> list[dict]:
    """解析 model list 响应（兼容多种 gm 返回结构）。"""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("list", "records", "rows", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_model_list(value)
            if nested:
                return nested
    return []


class GMClient:
    """httpx 同步客户端，调用 gm OpenAPI。"""

    def __init__(self, config: AgentConfig, transport: httpx.BaseTransport | None = None):
        self.config = config
        self._transport = transport

    def _api_url(self, endpoint: str) -> str:
        base = (self.config.gm_base_url or "").rstrip("/")
        if not base:
            raise GMClientError("GM_BASE_URL 未配置")
        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        if path.startswith("/api/"):
            return f"{base}{path}"
        return f"{base}/api{path}"

    def _headers(self) -> dict[str, str]:
        if not self.config.gm_api_key:
            raise GMClientError("GM_API_KEY 未配置")
        return {
            "Authorization": f"Bearer {self.config.gm_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _client(self) -> httpx.Client:
        kwargs: dict[str, Any] = {
            "timeout": self.config.request_timeout,
            "headers": self._headers(),
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        elif self.config.proxy:
            kwargs["proxy"] = self.config.proxy
        return httpx.Client(**kwargs)

    def list_models(
        self,
        task_id: str,
        *,
        checkpoint: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> list[dict]:
        """查询任务 checkpoint 列表（对应 gm task model list）。"""
        body: dict[str, Any] = {
            "task_id": task_id,
            "taskId": task_id,
            "page": page,
            "pageNum": page,
            "limit": limit,
            "pageSize": limit,
        }
        if checkpoint and checkpoint != "latest":
            body["checkpoint"] = checkpoint
            body["checkPoint"] = checkpoint

        url = self._api_url("/task/model/info")
        logger.info("gm list_models task_id=%s checkpoint=%s", task_id, checkpoint or "latest")

        with self._client() as client:
            response = client.post(url, json=body)
            if response.status_code >= 400:
                raise GMClientError(
                    f"gm model list 失败 HTTP {response.status_code}: {response.text[:500]}",
                )
            payload = response.json()

        data = _dig(payload, "data", "result") or payload
        models = _extract_model_list(data)
        if not models and isinstance(data, dict):
            models = _extract_model_list(payload)
        return models

    def download(self, url: str, dest: Path) -> Path:
        """从 policUrlDown 下载模型到 dest。"""
        if not url:
            raise GMClientError("下载 URL 为空")
        dest.parent.mkdir(parents=True, exist_ok=True)
        logger.info("gm download -> %s", dest)

        with self._client() as client:
            with client.stream("GET", url) as response:
                if response.status_code >= 400:
                    raise GMClientError(
                        f"gm 模型下载失败 HTTP {response.status_code}",
                    )
                with open(dest, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)

        if dest.stat().st_size == 0:
            raise GMClientError(f"下载文件为空: {dest}")
        return dest


_CHECKPOINT_NUM = re.compile(r"(\d+)")


def checkpoint_sort_key(model: dict) -> int:
    """从 checkpoint 字段提取排序用数字。"""
    for key in ("checkpoint", "checkPoint", "check_point", "iteration", "step"):
        raw = model.get(key)
        if raw is None:
            continue
        text = str(raw)
        match = _CHECKPOINT_NUM.search(text)
        if match:
            return int(match.group(1))
    name = str(
        model.get("fileName")
        or model.get("filename")
        or model.get("modelName")
        or "",
    )
    match = _CHECKPOINT_NUM.search(name)
    return int(match.group(1)) if match else 0


def select_model(models: list[dict], specifier: str) -> dict:
    """按 gm_checkpoint 说明选择条目（latest / 3000 / model_3000.pt）。"""
    if not models:
        raise GMClientError("gm 未返回任何 checkpoint")

    if specifier == "latest":
        return max(models, key=checkpoint_sort_key)

    spec = specifier.strip()
    if spec.endswith(".pt"):
        for model in models:
            name = str(
                model.get("fileName")
                or model.get("filename")
                or model.get("modelName")
                or "",
            )
            if name == spec or name.endswith(spec):
                return model

    for model in models:
        for key in ("checkpoint", "checkPoint", "check_point"):
            if str(model.get(key, "")) == spec:
                return model
        name = str(model.get("fileName") or model.get("filename") or "")
        if spec in name:
            return model

    raise GMClientError(f"未找到匹配的 checkpoint: {specifier}")


def model_download_url(model: dict) -> str:
    """优先 policUrlDown，其次 policUrl。"""
    url = model.get("policUrlDown") or model.get("policUrl")
    if not url:
        raise GMClientError("checkpoint 条目缺少 policUrlDown")
    if url.startswith("/"):
        base = (model.get("_gm_base_url") or "").rstrip("/")
        if base:
            return urljoin(f"{base}/", url.lstrip("/"))
    return str(url)


def model_filename(model: dict, *, fallback: str = "model.pt") -> str:
    for key in ("fileName", "filename", "modelName", "name"):
        value = model.get(key)
        if value:
            name = str(value)
            if name.endswith(".pt"):
                return name
            return f"{name}.pt" if "." not in name else name
    ckpt = model.get("checkpoint") or model.get("checkPoint")
    if ckpt is not None:
        return f"model_{ckpt}.pt"
    return fallback
