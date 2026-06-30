#!/usr/bin/env python3
"""NetTrainBridge 命令行客户端 (ntb)。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from nettrainbridge_common.config_loader import (
    default_config_path,
    discover_config_paths,
    get_setting,
    load_config_file,
    write_default_config,
)

DEFAULT_SERVER_URL = "http://localhost:8000"
REQUEST_TIMEOUT = 30.0
WATCH_INTERVAL = 5.0
TERMINAL_STATUSES = frozenset({"COMPLETED", "FAILED"})


def server_url() -> str:
    value = get_setting(
        "server_url",
        env_new="NETTRAINBRIDGE_SERVER_URL",
        env_old="GRADMOTION_SERVER_URL",
        section="cli",
        default=DEFAULT_SERVER_URL,
    )
    return str(value or DEFAULT_SERVER_URL)


def auth_headers() -> dict[str, str]:
    token = get_setting(
        "api_token",
        env_new="NETTRAINBRIDGE_API_TOKEN",
        env_old="GRADMOTION_API_TOKEN",
        section="cli",
        default="",
    )
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


class CLIError(Exception):
    pass


def request_json(method: str, path: str, **kwargs: Any) -> Any:
    url = server_url().rstrip("/") + path
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, headers=auth_headers()) as client:
            resp = client.request(method, url, **kwargs)
    except httpx.RequestError as exc:
        raise CLIError(f"无法连接服务器 {server_url()}: {exc}") from exc

    if resp.status_code == 404:
        raise CLIError(f"资源不存在: {path}")
    if resp.status_code >= 400:
        detail = resp.text.strip()
        raise CLIError(f"请求失败 HTTP {resp.status_code}: {detail}")

    if not resp.content:
        return None
    return resp.json()


def request_json_optional(method: str, path: str, **kwargs: Any) -> Any | None:
    """请求 JSON；404 时返回 None。"""
    try:
        return request_json(method, path, **kwargs)
    except CLIError as exc:
        if "资源不存在" in str(exc):
            return None
        raise


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_health(args: argparse.Namespace) -> None:
    data = request_json("GET", "/health")
    if args.json:
        print_json(data)
        return
    status = data.get("status", "unknown") if isinstance(data, dict) else data
    print(f"NetTrainBridge Server: {status}")
    print(f"URL: {server_url()}")


def _repo_short(repo_url: str) -> str:
    return repo_url.rstrip("/").split("/")[-1].replace(".git", "")


def _format_jobs_table(jobs: list[dict]) -> str:
    if not jobs:
        return "（无任务）"

    headers = ("ID", "STATUS", "REPO", "COMMIT", "AGENT", "CREATED")
    rows: list[tuple[str, ...]] = []
    for job in jobs:
        rows.append(
            (
                job.get("id", "")[:12],
                job.get("status", ""),
                _repo_short(job.get("repo_url", ""))[:20],
                (job.get("commit_sha") or "")[:12],
                (job.get("agent_id") or "-")[:12],
                (job.get("create_time") or "-")[:19],
            )
        )

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = [fmt_row(headers), fmt_row(tuple("-" * w for w in widths))]
    lines.extend(fmt_row(row) for row in rows)
    return "\n".join(lines)


def cmd_jobs(args: argparse.Namespace) -> None:
    params: dict[str, Any] = {"limit": args.limit}
    if args.status:
        params["status"] = args.status

    data = request_json("GET", "/jobs", params=params)
    if args.json:
        print_json(data)
        return

    jobs = data if isinstance(data, list) else []
    print(f"任务列表 ({len(jobs)}) — {server_url()}")
    print(_format_jobs_table(jobs))


def cmd_job(args: argparse.Namespace) -> None:
    data = request_json("GET", f"/jobs/{args.job_id}")
    if args.json:
        print_json(data)
        return

    fields = [
        ("ID", data.get("id")),
        ("状态", data.get("status")),
        ("仓库", data.get("repo_url")),
        ("Commit", data.get("commit_sha")),
        ("Agent", data.get("agent_id") or "-"),
        ("创建时间", data.get("create_time") or "-"),
        ("开始时间", data.get("start_time") or "-"),
        ("结束时间", data.get("end_time") or "-"),
    ]
    if data.get("error_msg"):
        fields.append(("错误", data.get("error_msg")))

    label_width = max(len(name) for name, _ in fields)
    for name, value in fields:
        print(f"{name.ljust(label_width)}  {value}")


def _fmt_float(value: Any, digits: int = 4) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _format_metrics_table(metrics: list[dict]) -> str:
    if not metrics:
        return "（无指标）"

    headers = ("STEP", "LOSS", "REWARD", "LR", "TIME")
    rows: list[tuple[str, ...]] = []
    for m in metrics:
        rows.append(
            (
                str(m.get("step", "")),
                _fmt_float(m.get("loss")),
                _fmt_float(m.get("reward")),
                _fmt_float(m.get("lr")),
                (m.get("timestamp") or "-")[:19],
            )
        )

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.rjust(widths[i]) for i, cell in enumerate(cells))

    lines = [fmt_row(headers), fmt_row(tuple("-" * w for w in widths))]
    lines.extend(fmt_row(row) for row in rows)
    return "\n".join(lines)


def cmd_metrics(args: argparse.Namespace) -> None:
    params: dict[str, Any] = {}
    if args.limit is not None:
        params["limit"] = args.limit
    if args.since_step is not None:
        params["since_step"] = args.since_step

    data = request_json("GET", f"/jobs/{args.job_id}/metrics", params=params)
    if args.json:
        print_json(data)
        return

    metrics = data if isinstance(data, list) else []
    print(f"指标 ({len(metrics)}) — job {args.job_id}")
    print(_format_metrics_table(metrics))


def _format_gpu_mem(used: Any, total: Any) -> str:
    if used is None or total is None:
        return "-"
    try:
        used_gb = float(used) / 1024 / 1024 / 1024
        total_gb = float(total) / 1024 / 1024 / 1024
        return f"{used_gb:.1f} / {total_gb:.1f} GB"
    except (TypeError, ValueError):
        return "-"


def cmd_heartbeat(args: argparse.Namespace) -> None:
    data = request_json("GET", f"/jobs/{args.job_id}/heartbeat")
    if args.json:
        print_json(data)
        return

    fields = [
        ("Agent", data.get("agent_id") or "-"),
        ("GPU 利用率", f"{_fmt_float(data.get('gpu_util'), 1)}%" if data.get("gpu_util") is not None else "-"),
        ("显存", _format_gpu_mem(data.get("gpu_mem_used"), data.get("gpu_mem_total"))),
        ("时间", data.get("timestamp") or "-"),
    ]
    label_width = max(len(name) for name, _ in fields)
    print(f"心跳 — job {args.job_id}")
    for name, value in fields:
        print(f"{name.ljust(label_width)}  {value}")


def cmd_logs(args: argparse.Namespace) -> None:
    if args.follow:
        _follow_logs(args.job_id)
        return

    params: dict[str, Any] = {}
    if args.tail is not None:
        params["tail"] = args.tail

    data = request_json("GET", f"/jobs/{args.job_id}/logs", params=params)
    if args.json:
        print_json(data)
        return

    logs = data.get("logs", []) if isinstance(data, dict) else []
    if not logs:
        print("（无日志）")
        return
    for line in logs:
        print(line)


def _follow_logs(job_id: str) -> None:
    url = server_url().rstrip("/") + f"/jobs/{job_id}/logs/stream"
    try:
        with httpx.Client(
            timeout=None,
            headers=auth_headers(),
        ) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code == 404:
                    raise CLIError(f"资源不存在: /jobs/{job_id}/logs/stream")
                if resp.status_code >= 400:
                    raise CLIError(f"请求失败 HTTP {resp.status_code}: {resp.read().decode()}")
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        payload = line[5:].lstrip()
                        print(payload, flush=True)
    except httpx.RequestError as exc:
        raise CLIError(f"无法连接服务器 {server_url()}: {exc}") from exc
    except KeyboardInterrupt:
        print("\n[已停止跟踪]", file=sys.stderr)


def _watch_mem_short(hb: dict | None) -> str:
    if not hb or hb.get("gpu_mem_used") is None:
        return "-"
    try:
        used_gb = float(hb["gpu_mem_used"]) / 1024 / 1024 / 1024
        total_gb = float(hb.get("gpu_mem_total") or 0) / 1024 / 1024 / 1024
        if total_gb > 0:
            return f"{used_gb:.1f}/{total_gb:.1f} GB"
        return f"{used_gb:.1f} GB"
    except (TypeError, ValueError):
        return "-"


def _watch_gpu_pct(hb: dict | None) -> str:
    if not hb or hb.get("gpu_util") is None:
        return "-"
    return f"{_fmt_float(hb.get('gpu_util'), 1)}%"


def _format_watch_row(metric: dict, hb: dict | None) -> str:
    return (
        f"{str(metric.get('step', '')).rjust(4)}  "
        f"{_fmt_float(metric.get('loss'), 4).rjust(8)}  "
        f"{_fmt_float(metric.get('reward'), 2).rjust(8)}  "
        f"{_watch_gpu_pct(hb).rjust(6)}  "
        f"{_watch_mem_short(hb)}"
    )


def _print_watch_footer(job_id: str) -> None:
    print("─" * 52, flush=True)
    print(f"[Ctrl+C 退出]  日志: ntb logs {job_id} -f", flush=True)


def cmd_watch(args: argparse.Namespace) -> None:
    job_id = args.job_id
    last_step = -1
    header_printed = False

    def ensure_header(job: dict) -> None:
        nonlocal header_printed
        if header_printed:
            return
        agent = job.get("agent_id") or "-"
        status = job.get("status", "?")
        print(f"NetTrainBridge watch  {job_id}  [{status}]  {agent}", flush=True)
        print("─" * 52, flush=True)
        print(f"{'Step':<6}{'Loss':<10}{'Reward':<10}{'GPU':<8}{'Mem'}", flush=True)
        header_printed = True

    try:
        while True:
            job = request_json("GET", f"/jobs/{job_id}")
            hb = request_json_optional("GET", f"/jobs/{job_id}/heartbeat")
            metrics = request_json(
                "GET",
                f"/jobs/{job_id}/metrics",
                params={"since_step": last_step},
            )
            metrics = metrics if isinstance(metrics, list) else []

            if args.json:
                print_json({"job": job, "heartbeat": hb, "metrics": metrics})
            else:
                ensure_header(job)
                for metric in metrics:
                    print(_format_watch_row(metric, hb), flush=True)
                    last_step = max(last_step, int(metric.get("step", last_step)))

            status = job.get("status", "")
            if args.once or status in TERMINAL_STATUSES:
                if not args.json:
                    _print_watch_footer(job_id)
                break

            time.sleep(args.interval)
    except KeyboardInterrupt:
        if not args.json:
            _print_watch_footer(job_id)
        print("\n[已停止监控]", file=sys.stderr)


def cmd_config_path(args: argparse.Namespace) -> None:
    _, active = load_config_file()
    if args.json:
        print_json(
            {
                "active": str(active) if active else None,
                "candidates": [str(p) for p in discover_config_paths()],
                "default": str(default_config_path()),
            }
        )
        return

    print("配置文件查找顺序（先匹配先生效）：")
    for path in discover_config_paths():
        mark = "  ← 当前使用" if active and path.resolve() == active.resolve() else ""
        exists = "存在" if path.is_file() else "不存在"
        print(f"  [{exists}] {path}{mark}")
    print(f"\n默认写入位置: {default_config_path()}")
    print("初始化: ntb config init")


def cmd_config_init(args: argparse.Namespace) -> None:
    target = default_config_path()
    if args.path:
        target = Path(args.path).expanduser()

    created = write_default_config(
        target,
        server_url=args.server_url,
        overwrite=args.force,
    )
    if args.json:
        print_json({"path": str(created), "server_url": args.server_url})
        return

    if created.exists() and not args.force:
        print(f"配置文件已存在: {created}")
        print("如需覆盖请加 --force")
    else:
        print(f"已生成配置文件: {created}")
    print(f"server_url = {args.server_url}")
    print("编辑该文件即可，无需每次设置环境变量。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ntb",
        description="NetTrainBridge 命令行客户端",
    )

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        help="输出原始 JSON",
    )
    common.add_argument(
        "--server",
        default=None,
        help="云服务器地址（默认 NETTRAINBRIDGE_SERVER_URL 或 http://localhost:8000）",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    health = sub.add_parser("health", parents=[common], help="健康检查")
    health.set_defaults(func=cmd_health)

    jobs = sub.add_parser("jobs", parents=[common], help="任务列表")
    jobs.add_argument("--status", choices=["PENDING", "ASSIGNED", "RUNNING", "COMPLETED", "FAILED"])
    jobs.add_argument("--limit", type=int, default=20)
    jobs.set_defaults(func=cmd_jobs)

    job = sub.add_parser("job", parents=[common], help="单任务详情")
    job.add_argument("job_id", help="任务 ID")
    job.set_defaults(func=cmd_job)

    metrics = sub.add_parser("metrics", parents=[common], help="训练指标")
    metrics.add_argument("job_id", help="任务 ID")
    metrics.add_argument("--limit", type=int, default=None, help="返回最近 N 条")
    metrics.add_argument("--since-step", type=int, default=None, dest="since_step", help="step 大于此值的记录")
    metrics.set_defaults(func=cmd_metrics)

    heartbeat = sub.add_parser("heartbeat", parents=[common], help="最新 GPU 心跳")
    heartbeat.add_argument("job_id", help="任务 ID")
    heartbeat.set_defaults(func=cmd_heartbeat)

    logs = sub.add_parser("logs", parents=[common], help="训练日志")
    logs.add_argument("job_id", help="任务 ID")
    logs.add_argument("-f", "--follow", action="store_true", help="实时跟踪 SSE 日志流")
    logs.add_argument("--tail", type=int, default=None, help="仅显示最后 N 行")
    logs.set_defaults(func=cmd_logs)

    watch = sub.add_parser("watch", parents=[common], help="综合监控（指标 + GPU）")
    watch.add_argument("job_id", help="任务 ID")
    watch.add_argument(
        "--interval",
        type=float,
        default=WATCH_INTERVAL,
        help=f"轮询间隔秒数（默认 {WATCH_INTERVAL:g}）",
    )
    watch.add_argument(
        "--once",
        action="store_true",
        help="只拉取一轮（用于脚本/调试）",
    )
    watch.set_defaults(func=cmd_watch)

    config = sub.add_parser("config", parents=[common], help="配置文件管理")
    config_sub = config.add_subparsers(dest="config_command", required=True)

    config_path = config_sub.add_parser("path", parents=[common], help="显示配置文件路径")
    config_path.set_defaults(func=cmd_config_path)

    config_init = config_sub.add_parser("init", parents=[common], help="生成默认配置文件")
    config_init.add_argument(
        "--server-url",
        dest="server_url",
        default="http://47.103.63.175:8000",
        help="云服务器地址",
    )
    config_init.add_argument("--path", default=None, help="写入路径（默认 ~/.nettrainbridge/config.json）")
    config_init.add_argument("--force", action="store_true", help="覆盖已有文件")
    config_init.set_defaults(func=cmd_config_init)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.server:
        os.environ["NETTRAINBRIDGE_SERVER_URL"] = args.server

    try:
        args.func(args)
    except CLIError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0
