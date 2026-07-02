#!/usr/bin/env python3
"""NetTrainBridge 命令行客户端 (ntb)。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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
DEPRECATED_TRIGGER_MSG = (
    "警告: ntb trigger 已弃用，请改用 ntb train run（默认训练请优先使用 gm）"
)


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


def request_download(path: str, dest: Path) -> int:
    """下载二进制文件到本地。"""
    url = server_url().rstrip("/") + path
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, headers=auth_headers()) as client:
            resp = client.get(url)
    except httpx.RequestError as exc:
        raise CLIError(f"无法连接服务器 {server_url()}: {exc}") from exc

    if resp.status_code == 404:
        raise CLIError(f"资源不存在: {path}")
    if resp.status_code >= 400:
        raise CLIError(f"下载失败 HTTP {resp.status_code}: {resp.text.strip()}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return len(resp.content)


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
    if getattr(args, "jobs_command", None) == "clear":
        cmd_jobs_clear(args)
        return

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


def cmd_jobs_clear(args: argparse.Namespace) -> None:
    """清空 Server 上全部任务（不可恢复）。"""
    if not args.yes:
        raise CLIError("危险操作：请使用 ntb jobs clear --yes 确认清空所有任务")

    data = request_json("DELETE", "/jobs", params={"confirm": "true"})
    if args.json:
        print_json(data)
        return

    deleted = data.get("deleted_jobs", 0) if isinstance(data, dict) else 0
    dirs = data.get("deleted_dirs", 0) if isinstance(data, dict) else 0
    orphans = data.get("orphan_dirs", 0) if isinstance(data, dict) else 0
    print(f"已清空任务: 数据库 {deleted} 条, 目录 {dirs} 个", end="")
    if orphans:
        print(f"（含孤儿目录 {orphans} 个）", end="")
    print()


def _git_output(*git_args: str) -> str:
    """执行 git 命令并返回 stdout。"""
    try:
        result = subprocess.run(
            ["git", *git_args],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise CLIError("未找到 git 命令，请安装 git 或使用 --repo / --commit 手动指定") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise CLIError(f"git {' '.join(git_args)} 失败: {stderr or exc}") from exc
    return result.stdout.strip()


def resolve_git_repo() -> str:
    """从当前目录 git 仓库读取 origin 远程地址。"""
    return _git_output("remote", "get-url", "origin")


def resolve_git_commit(*, branch: str | None = None) -> str:
    """解析 commit SHA：指定分支时优先 origin/<branch>。"""
    if branch:
        for ref in (f"origin/{branch}", branch):
            try:
                return _git_output("rev-parse", ref)
            except CLIError:
                continue
        raise CLIError(f"无法解析分支 {branch!r}，请确认已 fetch 或使用 --commit 指定")
    return _git_output("rev-parse", "HEAD")


def _resolve_repo_commit(args: argparse.Namespace) -> tuple[str, str]:
    """从 CLI 参数解析 repo_url 与 commit_sha。"""
    if getattr(args, "commit", None) and getattr(args, "branch", None):
        raise CLIError("--commit 与 --branch 不能同时指定")
    repo_url = args.repo or resolve_git_repo()
    commit_sha = args.commit or resolve_git_commit(branch=getattr(args, "branch", None))
    return repo_url, commit_sha


def _create_job(
    repo_url: str,
    commit_sha: str,
    *,
    job_type: str = "train",
    **extra: Any,
) -> dict:
    """创建任务（POST /jobs）。"""
    payload: dict[str, Any] = {
        "repo_url": repo_url,
        "commit_sha": commit_sha,
        "job_type": job_type,
    }
    payload.update(extra)
    return request_json("POST", "/jobs", json=payload)


def _create_train_job(repo_url: str, commit_sha: str) -> dict:
    """创建兜底训练任务。"""
    return _create_job(repo_url, commit_sha, job_type="train")


def _print_job_created(
    data: dict,
    *,
    watch_hint: bool = True,
    action: str = "监控",
) -> None:
    job_id = data.get("id", "")
    job_type = data.get("job_type", "train")
    print(f"已创建任务 {job_id}  [{data.get('status')}]  type={job_type}")
    print(f"  仓库:   {data.get('repo_url')}")
    print(f"  Commit: {data.get('commit_sha')}")
    if watch_hint:
        print(f"{action}: ntb watch {job_id}")


def cmd_train_run(args: argparse.Namespace) -> None:
    """创建兜底训练任务（ntb train run）。"""
    repo_url, commit_sha = _resolve_repo_commit(args)
    data = _create_train_job(repo_url, commit_sha)

    if args.json:
        print_json(data)
    else:
        _print_job_created(data, watch_hint=not args.watch)

    if args.watch:
        watch_args = argparse.Namespace(
            job_id=data["id"],
            json=args.json,
            interval=args.interval,
            once=False,
            server=args.server,
        )
        cmd_watch(watch_args)


def cmd_sync(args: argparse.Namespace) -> None:
    """仅同步代码到训练机（clone + checkout，不训练）。"""
    repo_url, commit_sha = _resolve_repo_commit(args)
    data = _create_job(repo_url, commit_sha, job_type="sync")

    if args.json:
        print_json(data)
    else:
        _print_job_created(data, watch_hint=False, action="查看")
        print(f"  等待 Agent 同步完成后: ntb job {data.get('id')}")


def cmd_test_run(args: argparse.Namespace) -> None:
    """创建 sim2sim 测试任务（ntb test run）。"""
    if args.gm_task_id and args.train_job_id:
        raise CLIError("--gm-task-id 与 --train-job-id 不能同时指定")
    if not args.gm_task_id and not args.train_job_id:
        raise CLIError("必须指定 --gm-task-id 或 --train-job-id 之一")
    if not args.load_run:
        raise CLIError(
            "--load-run 为必填（训练 logs 目录名，"
            "如 2026-01-14_09-58-10test_20_video）",
        )

    repo_url, commit_sha = _resolve_repo_commit(args)
    extra: dict[str, Any] = {
        "job_type": "test",
        "load_run": args.load_run,
        "task": args.task or "x1_dh_stand",
    }
    if args.gm_task_id:
        extra["gm_task_id"] = args.gm_task_id
        extra["gm_checkpoint"] = args.checkpoint
        if args.checkpoint.isdigit():
            extra["checkpoint"] = int(args.checkpoint)
    else:
        extra["parent_train_job_id"] = args.train_job_id
        if not str(args.checkpoint).isdigit():
            raise CLIError("ntb 路径请用 --checkpoint 指定整数（如 3000）")
        extra["checkpoint"] = int(args.checkpoint)

    data = _create_job(repo_url, commit_sha, **extra)

    if args.json:
        print_json(data)
    else:
        _print_job_created(data, watch_hint=not args.watch, action="监控")
        print(f"  load_run:    {args.load_run}")
        print(f"  task:        {args.task or 'x1_dh_stand'}")
        if data.get("gm_task_id"):
            print(f"  gm 任务:     {data.get('gm_task_id')}")
            meta = request_json_optional("GET", f"/jobs/{data['id']}/meta")
            if meta and meta.get("gm_checkpoint"):
                print(f"  gm ckpt:     {meta.get('gm_checkpoint')}")
        if data.get("parent_train_job_id"):
            print(f"  训练任务:    {data.get('parent_train_job_id')}")
            if extra.get("checkpoint") is not None:
                print(f"  checkpoint:  {extra['checkpoint']}")

    if args.watch:
        watch_args = argparse.Namespace(
            job_id=data["id"],
            json=args.json,
            interval=args.interval,
            once=False,
            server=args.server,
        )
        cmd_watch(watch_args)


def cmd_trigger(args: argparse.Namespace) -> None:
    """已弃用：转发到 ntb train run。"""
    print(DEPRECATED_TRIGGER_MSG, file=sys.stderr)
    cmd_train_run(args)


def cmd_job(args: argparse.Namespace) -> None:
    data = request_json("GET", f"/jobs/{args.job_id}")
    if args.json:
        print_json(data)
        return

    fields = [
        ("ID", data.get("id")),
        ("类型", data.get("job_type") or "train"),
        ("状态", data.get("status")),
        ("仓库", data.get("repo_url")),
        ("Commit", data.get("commit_sha")),
        ("Agent", data.get("agent_id") or "-"),
        ("创建时间", data.get("create_time") or "-"),
        ("开始时间", data.get("start_time") or "-"),
        ("结束时间", data.get("end_time") or "-"),
    ]
    if data.get("train_source"):
        fields.append(("训练来源", data.get("train_source")))
    if data.get("gm_task_id"):
        fields.append(("gm 任务", data.get("gm_task_id")))
    if data.get("parent_train_job_id"):
        fields.append(("父训练任务", data.get("parent_train_job_id")))
    if data.get("phase"):
        fields.append(("阶段", data.get("phase")))
    if data.get("error_msg"):
        fields.append(("错误", data.get("error_msg")))

    meta = request_json_optional("GET", f"/jobs/{args.job_id}/meta")
    if meta and isinstance(meta, dict):
        if meta.get("load_run"):
            fields.append(("load_run", meta.get("load_run")))
        if meta.get("task"):
            fields.append(("task", meta.get("task")))
        if meta.get("checkpoint") is not None:
            fields.append(("checkpoint", meta.get("checkpoint")))
        if meta.get("gm_checkpoint"):
            fields.append(("gm checkpoint", meta.get("gm_checkpoint")))
        if meta.get("model_filename"):
            fields.append(("模型文件", meta.get("model_filename")))

    label_width = max(len(name) for name, _ in fields)
    for name, value in fields:
        print(f"{name.ljust(label_width)}  {value}")


def _format_size(size: Any) -> str:
    if size is None:
        return "-"
    try:
        nbytes = int(size)
    except (TypeError, ValueError):
        return str(size)
    if nbytes < 1024:
        return f"{nbytes} B"
    if nbytes < 1024 * 1024:
        return f"{nbytes / 1024:.1f} KB"
    return f"{nbytes / 1024 / 1024:.1f} MB"


def _format_checkpoint_table(files: list[dict]) -> str:
    if not files:
        return "（无 checkpoint）"
    headers = ("FILENAME", "SIZE", "LOCATION", "PRIMARY")
    rows: list[tuple[str, ...]] = []
    for item in files:
        rows.append(
            (
                item.get("filename", ""),
                _format_size(item.get("size")),
                item.get("location", ""),
                "yes" if item.get("primary") else "",
            ),
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


def cmd_checkpoint_list(args: argparse.Namespace) -> None:
    data = request_json("GET", f"/jobs/{args.job_id}/checkpoint")
    if args.json:
        print_json(data)
        return
    files = data.get("files") if isinstance(data, dict) else []
    print(f"Checkpoint 列表 — job {args.job_id}")
    print(_format_checkpoint_table(files or []))


def cmd_checkpoint_download(args: argparse.Namespace) -> None:
    filename = args.filename
    if not filename:
        listing = request_json("GET", f"/jobs/{args.job_id}/checkpoint")
        files = listing.get("files") if isinstance(listing, dict) else []
        primary = next((f for f in files if f.get("primary")), None)
        if primary and primary.get("filename"):
            filename = primary["filename"]
        elif files:
            filename = files[0].get("filename")
        if not filename:
            meta = listing.get("meta") if isinstance(listing, dict) else {}
            filename = (meta or {}).get("model_filename")
    if not filename:
        raise CLIError("无可用 checkpoint，请使用 --filename 指定")

    dest = Path(args.output) if args.output else Path(filename)
    size = request_download(f"/jobs/{args.job_id}/checkpoint/{filename}", dest)
    if args.json:
        print_json({"job_id": args.job_id, "filename": filename, "path": str(dest), "size": size})
    else:
        print(f"已下载 checkpoint: {dest} ({_format_size(size)})")


def _format_artifacts_table(files: list[dict]) -> str:
    if not files:
        return "（无测试产物）"
    headers = ("PATH", "SIZE")
    rows = [(f.get("path", ""), _format_size(f.get("size"))) for f in files]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = [fmt_row(headers), fmt_row(tuple("-" * w for w in widths))]
    lines.extend(fmt_row(row) for row in rows)
    return "\n".join(lines)


def cmd_artifacts_list(args: argparse.Namespace) -> None:
    data = request_json("GET", f"/jobs/{args.job_id}/artifacts")
    if args.json:
        print_json(data)
        return
    files = data.get("files") if isinstance(data, dict) else []
    print(f"测试产物 — job {args.job_id}")
    print(_format_artifacts_table(files or []))


def cmd_artifacts_download(args: argparse.Namespace) -> None:
    dest = Path(args.output)
    size = request_download(f"/jobs/{args.job_id}/artifacts/download", dest)
    if args.json:
        print_json({"job_id": args.job_id, "path": str(dest), "size": size})
    else:
        print(f"已下载测试产物: {dest} ({_format_size(size)})")


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


def _add_git_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=None, help="仓库 URL（默认读取 git remote origin）")
    parser.add_argument("--commit", default=None, help="Commit SHA（默认当前 HEAD）")
    parser.add_argument(
        "--branch",
        default=None,
        help="分支名（解析 origin/<branch>，与 --commit 互斥）",
    )


def _add_train_watch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--watch",
        action="store_true",
        help="创建后立即进入 watch 监控",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=WATCH_INTERVAL,
        help=f"配合 --watch 的轮询间隔秒数（默认 {WATCH_INTERVAL:g}）",
    )


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

    jobs = sub.add_parser("jobs", parents=[common], help="任务列表 / 清空")
    jobs_sub = jobs.add_subparsers(dest="jobs_command", required=False)
    jobs.add_argument("--status", choices=["PENDING", "ASSIGNED", "RUNNING", "COMPLETED", "FAILED"])
    jobs.add_argument("--limit", type=int, default=20)
    jobs.set_defaults(func=cmd_jobs)

    jobs_list = jobs_sub.add_parser("list", parents=[common], help="列出任务（默认）")
    jobs_list.add_argument("--status", choices=["PENDING", "ASSIGNED", "RUNNING", "COMPLETED", "FAILED"])
    jobs_list.add_argument("--limit", type=int, default=20)
    jobs_list.set_defaults(func=cmd_jobs)

    jobs_clear = jobs_sub.add_parser("clear", parents=[common], help="清空所有任务")
    jobs_clear.add_argument(
        "--yes",
        action="store_true",
        help="确认删除（不可恢复）",
    )
    jobs_clear.set_defaults(func=cmd_jobs)

    train = sub.add_parser("train", parents=[common], help="兜底训练（gm 不可用时）")
    train_sub = train.add_subparsers(dest="train_command", required=True)

    train_run = train_sub.add_parser("run", parents=[common], help="创建训练任务")
    _add_git_source_args(train_run)
    _add_train_watch_args(train_run)
    train_run.set_defaults(func=cmd_train_run)

    sync = sub.add_parser("sync", parents=[common], help="仅同步代码到训练机（步骤 3）")
    _add_git_source_args(sync)
    sync.set_defaults(func=cmd_sync)

    test = sub.add_parser("test", parents=[common], help="sim2sim 测试（步骤 5 占位创建）")
    test_sub = test.add_subparsers(dest="test_command", required=True)

    test_run = test_sub.add_parser("run", parents=[common], help="创建测试任务")
    _add_git_source_args(test_run)
    _add_train_watch_args(test_run)
    test_run.add_argument(
        "--load-run",
        dest="load_run",
        required=True,
        help="训练 logs 目录名（如 2026-01-14_09-58-10test_20_video）",
    )
    test_run.add_argument(
        "--task",
        default="x1_dh_stand",
        help="训练任务名（默认 x1_dh_stand）",
    )
    test_run.add_argument(
        "--gm-task-id",
        dest="gm_task_id",
        default=None,
        help="gm 训练任务 ID（与 --train-job-id 二选一）",
    )
    test_run.add_argument(
        "--train-job-id",
        dest="train_job_id",
        default=None,
        help="ntb 训练任务 ID（与 --gm-task-id 二选一）",
    )
    test_run.add_argument(
        "--checkpoint",
        default="latest",
        help="gm checkpoint 选择（仅 --gm-task-id 时有效，默认 latest）",
    )
    test_run.set_defaults(func=cmd_test_run)

    trigger = sub.add_parser(
        "trigger",
        parents=[common],
        help="[已弃用] 请改用 ntb train run",
        description="[已弃用] 请改用 ntb train run",
    )
    _add_git_source_args(trigger)
    _add_train_watch_args(trigger)
    trigger.set_defaults(func=cmd_trigger)

    job = sub.add_parser("job", parents=[common], help="单任务详情")
    job.add_argument("job_id", help="任务 ID")
    job.set_defaults(func=cmd_job)

    checkpoint = sub.add_parser("checkpoint", parents=[common], help="模型 checkpoint")
    checkpoint_sub = checkpoint.add_subparsers(dest="checkpoint_command", required=True)

    checkpoint_list = checkpoint_sub.add_parser("list", parents=[common], help="列出 checkpoint")
    checkpoint_list.add_argument("job_id", help="任务 ID")
    checkpoint_list.set_defaults(func=cmd_checkpoint_list)

    checkpoint_dl = checkpoint_sub.add_parser("download", parents=[common], help="下载 checkpoint")
    checkpoint_dl.add_argument("job_id", help="任务 ID")
    checkpoint_dl.add_argument(
        "-o",
        "--output",
        default=None,
        help="保存路径（默认使用文件名）",
    )
    checkpoint_dl.add_argument(
        "--filename",
        default=None,
        help="指定文件名（默认 meta 主模型或列表第一项）",
    )
    checkpoint_dl.set_defaults(func=cmd_checkpoint_download)

    artifacts = sub.add_parser("artifacts", parents=[common], help="测试产物（test job）")
    artifacts_sub = artifacts.add_subparsers(dest="artifacts_command", required=True)

    artifacts_list = artifacts_sub.add_parser("list", parents=[common], help="列出测试产物")
    artifacts_list.add_argument("job_id", help="任务 ID")
    artifacts_list.set_defaults(func=cmd_artifacts_list)

    artifacts_dl = artifacts_sub.add_parser("download", parents=[common], help="打包下载 zip")
    artifacts_dl.add_argument("job_id", help="任务 ID")
    artifacts_dl.add_argument(
        "-o",
        "--output",
        required=True,
        help="保存 zip 路径",
    )
    artifacts_dl.set_defaults(func=cmd_artifacts_download)

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
