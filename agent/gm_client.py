"""Gradmotion (gm) API 客户端 — Agent 经代理直拉 checkpoint (5B)。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx

from config import AgentConfig

logger = logging.getLogger("nettrainbridge.agent.gm")


class GMClientError(Exception):
    """gm API 或下载失败。"""


def _api_error_message(payload: Any) -> str | None:
    """gm 常在 HTTP 200 下用 body.code / success 表示失败。"""
    if not isinstance(payload, dict):
        return None
    code = payload.get("code")
    success = payload.get("success")
    if success is False or (isinstance(code, int) and code not in (0, 200)):
        msg = payload.get("msg") or payload.get("message") or payload.get("msgEn")
        return str(msg or f"gm API 错误 code={code}")
    return None


def _unwrap_payload(payload: Any) -> Any:
    """展开 gm 响应外层（兼容 CLI 与直连 API 多种嵌套）。"""
    if not isinstance(payload, dict):
        return payload

    err = _api_error_message(payload)
    if err:
        raise GMClientError(err)

    for key in ("data", "result"):
        inner = payload.get(key)
        if inner is None or inner == "":
            continue
        if isinstance(inner, dict):
            nested_err = _api_error_message(inner)
            if nested_err:
                raise GMClientError(nested_err)
            return inner
        if isinstance(inner, list):
            return inner
    return payload


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
        # gm OpenAPI 与 gm-cli 一致：X-Api-Key（非 Bearer）
        return {
            "X-Api-Key": self.config.gm_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _api_client(self) -> httpx.Client:
        kwargs: dict[str, Any] = {
            "timeout": self.config.request_timeout,
            "headers": self._headers(),
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        elif self.config.proxy:
            kwargs["proxy"] = self.config.proxy
        return httpx.Client(**kwargs)

    def _download_client(self, *, proxy: str | None) -> httpx.Client:
        """OSS 预签名直链：不带 gm 鉴权头（附加头易导致 403）。"""
        kwargs: dict[str, Any] = {
            "timeout": self.config.request_timeout,
            "follow_redirects": True,
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        elif proxy:
            kwargs["proxy"] = proxy
        return httpx.Client(**kwargs)

    @staticmethod
    def _url_host(url: str) -> str:
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""

    def _is_gm_api_host(self, url: str) -> bool:
        base_host = self._url_host(self.config.gm_base_url or "")
        if not base_host:
            return False
        return self._url_host(url) == base_host

    def _download_proxy_attempts(self, url: str) -> list[str | None]:
        """外网 OSS 默认直连；失败后再试公司代理。"""
        if self._is_gm_api_host(url):
            return [self.config.proxy or None]
        attempts: list[str | None] = [None]
        if self.config.proxy:
            attempts.append(self.config.proxy)
        return attempts

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

        with self._api_client() as client:
            response = client.post(url, json=body)
            if response.status_code >= 400:
                raise GMClientError(
                    f"gm model list 失败 HTTP {response.status_code}: {response.text[:500]}",
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise GMClientError(
                    f"gm model list 响应非 JSON: {response.text[:200]}",
                ) from exc

        data = _unwrap_payload(payload)
        models = _extract_model_list(data)
        if not models and isinstance(data, dict):
            models = _extract_model_list(payload)
        if not models:
            logger.warning(
                "gm list_models 空列表 task_id=%s url=%s keys=%s",
                task_id,
                url,
                list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__,
            )
        return models

    def download(self, url: str, dest: Path) -> Path:
        """从 policUrlDown 等直链下载模型到 dest（OSS 预签名，不走 gm 鉴权头）。"""
        if not url:
            raise GMClientError("下载 URL 为空")
        if not url.startswith(("http://", "https://")):
            raise GMClientError(f"不支持的下载 URL（需 http/https 直链）: {url[:120]}")

        dest.parent.mkdir(parents=True, exist_ok=True)
        host = self._url_host(url)
        logger.info("gm download host=%s -> %s", host or "?", dest)

        errors: list[str] = []
        attempts = self._download_proxy_attempts(url)
        for idx, proxy in enumerate(attempts):
            label = "direct" if not proxy else "proxy"
            try:
                with self._download_client(proxy=proxy) as client:
                    with client.stream("GET", url) as response:
                        if response.status_code >= 400:
                            raise GMClientError(
                                f"gm 模型下载失败 HTTP {response.status_code} "
                                f"({label}, host={host})",
                            )
                        with open(dest, "wb") as f:
                            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                                f.write(chunk)
                if dest.stat().st_size == 0:
                    raise GMClientError(f"下载文件为空: {dest}")
                return dest
            except GMClientError as exc:
                errors.append(f"{label}: {exc}")
                msg = str(exc)
                retryable = any(code in msg for code in ("403", "407", "502", "503", "504"))
                if not retryable or idx == len(attempts) - 1:
                    break
                logger.warning("gm download retry after %s failed: %s", label, exc)

        hint = (
            "（外网 OSS 直链对公司代理可能返回 403，已尝试直连与代理）"
            if self.config.proxy
            else ""
        )
        raise GMClientError(f"gm 模型下载失败{hint}: {'; '.join(errors)}")


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
    """优先 policUrlDown，其次 convertUrlDown（须为 http 直链）。"""
    for key in ("policUrlDown", "convertUrlDown"):
        url = model.get(key)
        if url and str(url).startswith(("http://", "https://")):
            return str(url)
    url = model.get("policUrlDown") or model.get("policUrl")
    if not url:
        raise GMClientError("checkpoint 条目缺少 policUrlDown")
    if url.startswith("/"):
        base = (model.get("_gm_base_url") or "").rstrip("/")
        if base:
            return urljoin(f"{base}/", url.lstrip("/"))
    text = str(url)
    if text.startswith(("http://", "https://")):
        return text
    raise GMClientError(
        "checkpoint 仅有存储相对路径，缺少可下载的 policUrlDown 直链",
    )


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
