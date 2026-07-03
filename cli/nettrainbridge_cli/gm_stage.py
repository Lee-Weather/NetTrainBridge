"""CLI：从 gm 拉取 checkpoint 并上传到 Server（Plan 03）。"""

from __future__ import annotations

import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from nettrainbridge_common.config_loader import get_setting

from nettrainbridge_cli.checkpoint_io import put_job_meta, upload_checkpoint

_CHECKPOINT_NUM = re.compile(r"(\d+)")


class GmStageError(Exception):
    """gm staging 失败。"""


@dataclass
class GmCliConfig:
    gm_api_key: str
    gm_base_url: str
    proxy: str = ""
    request_timeout: int = 60


def load_gm_cli_config() -> GmCliConfig:
    from nettrainbridge_cli.main import CLIError

    api_key = get_setting(
        "gm_api_key",
        env_new="GM_API_KEY",
        section="cli",
        default="",
    ) or get_setting(
        "gm_api_key",
        env_new="GM_API_KEY",
        section="agent",
        default="",
    )
    base_url = get_setting(
        "gm_base_url",
        env_new="GM_BASE_URL",
        section="cli",
        default="",
    ) or get_setting(
        "gm_base_url",
        env_new="GM_BASE_URL",
        section="agent",
        default="",
    )
    proxy = get_setting(
        "proxy",
        env_new="NETTRAINBRIDGE_PROXY",
        env_old="GRADMOTION_PROXY",
        section="cli",
        default="",
    )
    if not api_key or not base_url:
        raise CLIError(
            "请在 ~/.nettrainbridge/config.json 的 cli 段配置 gm_api_key / gm_base_url",
        )
    return GmCliConfig(
        gm_api_key=str(api_key),
        gm_base_url=str(base_url).rstrip("/"),
        proxy=str(proxy or ""),
    )


def _api_error_message(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    code = payload.get("code")
    success = payload.get("success")
    if success is False or (isinstance(code, int) and code not in (0, 200)):
        msg = payload.get("msg") or payload.get("message") or payload.get("msgEn")
        return str(msg or f"gm API 错误 code={code}")
    return None


def _unwrap_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    err = _api_error_message(payload)
    if err:
        raise GmStageError(err)
    for key in ("data", "result"):
        inner = payload.get(key)
        if inner is None or inner == "":
            continue
        if isinstance(inner, dict):
            nested_err = _api_error_message(inner)
            if nested_err:
                raise GmStageError(nested_err)
            return inner
        if isinstance(inner, list):
            return inner
    return payload


def _extract_model_list(payload: Any) -> list[dict]:
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


def _api_url(cfg: GmCliConfig, endpoint: str) -> str:
    path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
    if path.startswith("/api/"):
        return f"{cfg.gm_base_url}{path}"
    return f"{cfg.gm_base_url}/api{path}"


def _list_models(cfg: GmCliConfig, task_id: str, *, checkpoint: Optional[str] = None) -> list[dict]:
    body: dict[str, Any] = {
        "task_id": task_id,
        "taskId": task_id,
        "page": 1,
        "pageNum": 1,
        "limit": 50,
        "pageSize": 50,
    }
    if checkpoint and checkpoint != "latest":
        body["checkpoint"] = checkpoint
        body["checkPoint"] = checkpoint
    headers = {
        "X-Api-Key": cfg.gm_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    kwargs: dict[str, Any] = {"timeout": cfg.request_timeout, "headers": headers}
    if cfg.proxy:
        kwargs["proxy"] = cfg.proxy
    with httpx.Client(**kwargs) as client:
        response = client.post(_api_url(cfg, "/task/model/info"), json=body)
        if response.status_code >= 400:
            raise GmStageError(f"gm model list HTTP {response.status_code}")
        payload = _unwrap_payload(response.json())
    return _extract_model_list(payload)


def _checkpoint_sort_key(model: dict) -> int:
    for key in ("checkpoint", "checkPoint", "check_point"):
        raw = model.get(key)
        if raw is not None:
            match = _CHECKPOINT_NUM.search(str(raw))
            if match:
                return int(match.group(1))
    name = str(model.get("fileName") or model.get("filename") or "")
    match = _CHECKPOINT_NUM.search(name)
    return int(match.group(1)) if match else 0


def _select_model(models: list[dict], specifier: str) -> dict:
    if not models:
        raise GmStageError("gm 未返回任何 checkpoint")
    if specifier == "latest":
        return max(models, key=_checkpoint_sort_key)
    spec = specifier.strip()
    for model in models:
        for key in ("checkpoint", "checkPoint", "check_point"):
            if str(model.get(key, "")) == spec:
                return model
        name = str(model.get("fileName") or model.get("filename") or "")
        if spec in name:
            return model
    raise GmStageError(f"未找到匹配的 checkpoint: {specifier}")


def _model_download_url(model: dict) -> str:
    for key in ("policUrlDown", "convertUrlDown"):
        url = model.get(key)
        if url and str(url).startswith(("http://", "https://")):
            return str(url)
    raise GmStageError("checkpoint 缺少可下载的 policUrlDown 直链")


def _model_filename(model: dict, *, fallback: str = "model.pt") -> str:
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


def _download_url(cfg: GmCliConfig, url: str, dest: Path) -> None:
    host = urlparse(url).netloc
    attempts: list[str | None] = [None]
    if cfg.proxy:
        attempts.append(cfg.proxy)
    errors: list[str] = []
    for proxy in attempts:
        label = "direct" if not proxy else "proxy"
        try:
            with httpx.Client(
                timeout=cfg.request_timeout,
                follow_redirects=True,
                proxy=proxy,
            ) as client:
                response = client.get(url)
                if response.status_code >= 400:
                    raise GmStageError(f"下载 HTTP {response.status_code} ({label}, {host})")
                dest.write_bytes(response.content)
            if dest.stat().st_size == 0:
                raise GmStageError(f"下载文件为空: {dest}")
            return
        except GmStageError as exc:
            errors.append(f"{label}: {exc}")
    raise GmStageError("; ".join(errors))


def stage_checkpoint_from_gm(
    job_id: str,
    gm_task_id: str,
    gm_checkpoint: str,
    *,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """从 gm 下载 checkpoint 并上传到 Server test job。"""
    cfg = load_gm_cli_config()
    ck_filter = None if gm_checkpoint == "latest" else gm_checkpoint
    models = _list_models(cfg, gm_task_id, checkpoint=ck_filter)
    model = _select_model(models, gm_checkpoint)
    url = _model_download_url(model)
    filename = _model_filename(model)

    base_dir = work_dir or Path(tempfile.gettempdir())
    local_path = base_dir / filename
    try:
        _download_url(cfg, url, local_path)
        upload_checkpoint(job_id, local_path)
        checkpoint_int = _checkpoint_sort_key(model)
        meta = put_job_meta(
            job_id,
            {
                "model_filename": filename,
                "checkpoint": checkpoint_int,
                "checkpoint_staged": True,
                "checkpoint_staged_at": datetime.now(timezone.utc).isoformat(),
                "fetch_mode": "server",
            },
        )
    finally:
        if work_dir is None and local_path.is_file():
            local_path.unlink(missing_ok=True)

    return {
        "job_id": job_id,
        "gm_task_id": gm_task_id,
        "filename": filename,
        "checkpoint": checkpoint_int,
        "meta": meta,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="从 gm 拉取 checkpoint 并上传到 Server")
    parser.add_argument("--task-id", required=True, help="gm task_id")
    parser.add_argument("--job-id", required=True, help="test job id")
    parser.add_argument("--checkpoint", default="latest", help="checkpoint 说明")
    args = parser.parse_args(argv)
    try:
        result = stage_checkpoint_from_gm(args.job_id, args.task_id, args.checkpoint)
    except (GmStageError, Exception) as exc:
        from nettrainbridge_cli.main import CLIError
        if isinstance(exc, CLIError):
            print(f"❌ {exc}", file=sys.stderr)
            return 1
        if isinstance(exc, GmStageError):
            print(f"❌ {exc}", file=sys.stderr)
            return 1
        raise
    print(
        f"✓ staged {result['filename']} "
        f"(checkpoint={result['checkpoint']}) → job {result['job_id']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
