#!/usr/bin/env python3
"""训练机 gm 凭证探针：验证 Agent 能否拉取 checkpoint 列表。

用法（在训练机 Agent 目录或项目根）::

    python agent/scripts/gm_probe.py --task-id TASK_20260605_042
    python agent/scripts/gm_probe.py --task-id TASK_xxx --checkpoint 50

退出码 0=成功；非 0=配置或 API 错误。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_AGENT_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _AGENT_DIR.parent
for p in (_AGENT_DIR, _REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from config import AgentConfig  # noqa: E402
from gm_client import GMClient, GMClientError, model_download_url, select_model  # noqa: E402
from nettrainbridge_common.config_loader import config_status_message  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="探针：gm task model list（Agent 同款凭证）")
    parser.add_argument("--task-id", required=True, help="gm task_id")
    parser.add_argument("--checkpoint", default="latest", help="latest 或整数如 50")
    parser.add_argument(
        "--download",
        action="store_true",
        help="选中后试下载到 /tmp/gm_probe_model.pt（验证 OSS 直链）",
    )
    args = parser.parse_args()

    cfg = AgentConfig.load()
    print(config_status_message())
    print(f"gm_base_url: {cfg.gm_base_url or '(未配置)'}")
    print(f"gm_api_key:  {'已配置' if cfg.gm_api_key else '(未配置)'}")
    if cfg.proxy:
        print(f"proxy:       {cfg.proxy}")

    if not cfg.gm_api_key or not cfg.gm_base_url:
        print("\n❌ 请在 ~/.nettrainbridge/config.json 的 agent 段配置 gm_api_key / gm_base_url")
        print("   须与家里 gm CLI 同账号（gm auth status 显示的 API Key）")
        return 1

    client = GMClient(cfg)
    try:
        ck_filter = None if args.checkpoint == "latest" else args.checkpoint
        models = client.list_models(args.task_id, checkpoint=ck_filter)
        print(f"\n✓ list_models 返回 {len(models)} 条")
        if not models:
            print("❌ 列表为空（检查 task_id 或账号权限）")
            return 2
        picked = select_model(models, args.checkpoint)
        print(
            f"✓ 选中 checkpoint={picked.get('checkpoint')} "
            f"file={picked.get('fileName')}",
        )
        if args.download:
            dest = Path("/tmp/gm_probe_model.pt")
            url = model_download_url(picked)
            from urllib.parse import urlparse

            print(f"  下载 host: {urlparse(url).netloc}")
            client.download(url, dest)
            print(f"✓ 下载成功 -> {dest} ({dest.stat().st_size} bytes)")
    except GMClientError as exc:
        print(f"\n❌ {exc}")
        if "token" in str(exc).lower() or "失效" in str(exc):
            print("   → API Key 过期或与家里 gm 账号不一致，请更新 agent.gm_api_key")
        elif "403" in str(exc):
            print("   → OSS 直链 403：外网存储可能被公司代理拦截，已修复为优先直连；仍失败请联系运维放行 aliyuncs.com")
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
