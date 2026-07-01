#!/usr/bin/env python3
"""sim2sim 测试桥接：Mock 占位 + 真实 play.py（R1-1）。

环境变量：
  NETTRAINBRIDGE_METRICS_FILE / GRADMOTION_METRICS_FILE → metrics.jsonl
  NETTRAINBRIDGE_JOB_ID / GRADMOTION_JOB_ID
  NETTRAINBRIDGE_LOAD_RUN / NETTRAINBRIDGE_CHECKPOINT → 覆盖 CLI
  NETTRAINBRIDGE_TEST_OUTPUT_DIR → play CSV 目录（默认 metrics 同级的 test/）
  NETTRAINBRIDGE_PLAY_RENDER → 0（NTB 不录屏）

用法：
  python test_with_metrics.py --self-test
  python test_with_metrics.py --mock --checkpoint /path/to/model.pt
  python test_with_metrics.py --task=x1_dh_stand \\
      --load-run=2026-01-14_09-58-10test_20_video --checkpoint=3000 --headless
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

_CSV_SAVED_RE = re.compile(r"^CSV saved to:\s*(.+)\s*$", re.MULTILINE)
_TRACKING_OK_THRESHOLD = 0.15


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _metrics_env_path() -> Path:
    for key in ("NETTRAINBRIDGE_METRICS_FILE", "GRADMOTION_METRICS_FILE"):
        value = os.environ.get(key)
        if value:
            return Path(value)
    return Path("metrics.jsonl")


def _summary_path(metrics_file: Path) -> Path:
    test_dir = metrics_file.parent / "test"
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir / "summary.json"


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _parse_checkpoint_layout(path: Path) -> tuple[str | None, int | None]:
    """从 logs/.../exported_data/<load_run>/model_N.pt 解析。"""
    if path.name.startswith("model_") and path.suffix == ".pt":
        try:
            checkpoint = int(path.stem.split("_", 1)[1])
        except (IndexError, ValueError):
            checkpoint = None
        else:
            parent = path.parent
            grand = parent.parent
            load_run = parent.name if grand.name == "exported_data" else None
            return load_run, checkpoint
    return None, None


def model_path_for(task: str, load_run: str, checkpoint: int, repo_root: Path | None = None) -> Path:
    root = repo_root or _repo_root()
    return root / "logs" / task / "exported_data" / load_run / f"model_{checkpoint}.pt"


def summarize_isaac_diag_csv(csv_path: Path) -> dict:
    """从 play 产出的 isaac_diag CSV 汇总测试指标。"""
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return {
            "final_reward": 0.0,
            "success_rate": 0.0,
            "csv_rows": 0,
            "error": "empty csv",
        }

    vel_x: list[float] = []
    cmd_x: list[float] = []
    penalties: list[float] = []
    for row in rows:
        vel_x.append(float(row["base_lin_vel_x"]))
        cmd_x.append(float(row["cmd_linear_x"]))
        penalties.append(float(row.get("feet_contact_force_penalty") or 0.0))

    mean_vel = sum(vel_x) / len(vel_x)
    errors = [abs(v - c) for v, c in zip(vel_x, cmd_x)]
    success_rate = sum(1 for e in errors if e < _TRACKING_OK_THRESHOLD) / len(errors)
    mean_penalty = sum(penalties) / len(penalties)

    return {
        "final_reward": round(mean_vel, 4),
        "mean_vel_x": round(mean_vel, 4),
        "mean_tracking_error": round(sum(errors) / len(errors), 4),
        "mean_contact_penalty": round(mean_penalty, 4),
        "success_rate": round(success_rate, 4),
        "csv_rows": len(rows),
        "csv_path": str(csv_path),
    }


def write_metrics_from_csv(csv_path: Path, metrics_file: Path, *, max_points: int = 50) -> int:
    """将 CSV 采样写入 metrics.jsonl（kind=test）。"""
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return 0

    if metrics_file.exists():
        metrics_file.write_text("", encoding="utf-8")

    stride = max(1, len(rows) // max_points)
    count = 0
    for i, row in enumerate(rows):
        if i % stride != 0 and i != len(rows) - 1:
            continue
        step = i + 1
        append_jsonl(
            metrics_file,
            {
                "step": step,
                "loss": float(row.get("feet_contact_force_penalty") or 0.0),
                "reward": float(row["base_lin_vel_x"]),
                "lr": 0.0,
                "kind": "test",
            },
        )
        count += 1
    return count


def _find_csv_in_output(output_dir: Path) -> Path | None:
    candidates = sorted(
        output_dir.glob("isaac_diag_*.csv"),
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def _parse_csv_path_from_stdout(stdout: str, output_dir: Path) -> Path | None:
    match = _CSV_SAVED_RE.search(stdout)
    if match:
        path = Path(match.group(1).strip())
        if path.is_file():
            return path
    return _find_csv_in_output(output_dir)


def run_real_sim2sim(
    *,
    task: str,
    load_run: str,
    checkpoint: int,
    metrics_file: Path,
    summary_file: Path,
    headless: bool,
    checkpoint_path: Path | None = None,
) -> int:
    """subprocess 调 play.py，解析 CSV → metrics.jsonl + summary.json。"""
    repo_root = _repo_root()
    play_script = repo_root / "humanoid" / "scripts" / "play.py"
    if not play_script.is_file():
        print(f"[test_with_metrics] 未找到 play.py: {play_script}", file=sys.stderr)
        return 1

    model_path = checkpoint_path or model_path_for(task, load_run, checkpoint, repo_root)
    if not model_path.is_file():
        print(f"[test_with_metrics] checkpoint 不存在: {model_path}", file=sys.stderr)
        return 1

    job_id = os.environ.get("NETTRAINBRIDGE_JOB_ID") or os.environ.get(
        "GRADMOTION_JOB_ID", "local-test",
    )
    output_dir = Path(
        os.environ.get("NETTRAINBRIDGE_TEST_OUTPUT_DIR") or str(summary_file.parent),
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(play_script),
        f"--task={task}",
        f"--load_run={load_run}",
        f"--checkpoint={checkpoint}",
    ]
    if headless:
        cmd.append("--headless")

    env = os.environ.copy()
    env["NETTRAINBRIDGE_TEST_OUTPUT_DIR"] = str(output_dir)
    env.setdefault("NETTRAINBRIDGE_PLAY_RENDER", "0")
    env.setdefault("NETTRAINBRIDGE_PLAY_LOG_CSV", "1")

    print(
        f"[test_with_metrics] real sim2sim job={job_id} "
        f"load_run={load_run} ckpt={checkpoint}",
    )
    print(f"[test_with_metrics] play -> {play_script}")
    print(f"[test_with_metrics] csv dir -> {output_dir}")

    result = subprocess.run(
        cmd,
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if result.returncode != 0:
        print(
            f"[test_with_metrics] play.py 退出码 {result.returncode}",
            file=sys.stderr,
        )
        return result.returncode

    csv_path = _parse_csv_path_from_stdout(result.stdout, output_dir)
    if csv_path is None:
        print("[test_with_metrics] 未找到 isaac_diag CSV", file=sys.stderr)
        return 1

    stats = summarize_isaac_diag_csv(csv_path)
    metric_count = write_metrics_from_csv(csv_path, metrics_file)

    summary = {
        "job_id": job_id,
        "mode": "real",
        "task": task,
        "load_run": load_run,
        "checkpoint": checkpoint,
        "model_path": str(model_path),
        "metrics_points": metric_count,
        **stats,
    }
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[test_with_metrics] metrics -> {metrics_file} ({metric_count} points)")
    print(f"[test_with_metrics] summary -> {summary_file}")
    print(
        f"[test_with_metrics] success_rate={stats['success_rate']} "
        f"final_reward={stats['final_reward']}",
    )
    print("[test_with_metrics] real sim2sim complete")
    return 0


def run_mock_sim2sim(
    *,
    checkpoint_path: Path,
    metrics_file: Path,
    summary_file: Path,
    steps: int = 3,
    sleep_sec: float = 0.2,
) -> int:
    """模拟 sim2sim：写若干条假指标 + summary.json，不依赖 Isaac。"""
    if not checkpoint_path.exists():
        print(f"[test_with_metrics] checkpoint 不存在: {checkpoint_path}", file=sys.stderr)
        return 1

    job_id = os.environ.get("NETTRAINBRIDGE_JOB_ID") or os.environ.get(
        "GRADMOTION_JOB_ID", "mock-job",
    )
    print(f"[test_with_metrics] mock sim2sim start job={job_id} ckpt={checkpoint_path}")
    print(f"[test_with_metrics] metrics -> {metrics_file}")

    for step in range(1, steps + 1):
        time.sleep(sleep_sec)
        reward = 1.0 + step * 0.1
        append_jsonl(
            metrics_file,
            {
                "step": step,
                "loss": 0.0,
                "reward": reward,
                "lr": 0.0,
                "kind": "test",
                "mock": True,
            },
        )
        print(f"[test_with_metrics] mock step={step} reward={reward:.2f}")

    summary = {
        "job_id": job_id,
        "mode": "mock",
        "checkpoint": str(checkpoint_path),
        "steps": steps,
        "final_reward": 1.0 + steps * 0.1,
        "success_rate": 0.85,
        "note": "占位结果，非真实 sim2sim",
    }
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[test_with_metrics] summary -> {summary_file}")
    print("[test_with_metrics] mock sim2sim complete")
    return 0


def _self_test_csv_parser() -> None:
    import tempfile

    header = "timestamp_ns,cmd_linear_x,base_lin_vel_x,feet_contact_force_penalty\n"
    body = "1,0.4,0.38,0.0\n2,0.4,0.42,1.0\n3,0.4,0.39,0.5\n"
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "isaac_diag_test.csv"
        csv_path.write_text(header + body, encoding="utf-8")
        stats = summarize_isaac_diag_csv(csv_path)
        assert stats["csv_rows"] == 3, stats
        assert stats["success_rate"] == 1.0, stats
        metrics = Path(tmp) / "metrics.jsonl"
        n = write_metrics_from_csv(csv_path, metrics)
        assert n >= 1, n
        lines = metrics.read_text(encoding="utf-8").strip().splitlines()
        rec = json.loads(lines[0])
        assert rec["kind"] == "test"
        assert "mock" not in rec


def _self_test() -> None:
    import tempfile

    _self_test_csv_parser()

    with tempfile.TemporaryDirectory() as tmp:
        ckpt = Path(tmp) / "model_mock.pt"
        ckpt.write_text("mock", encoding="utf-8")
        metrics = Path(tmp) / "metrics.jsonl"
        summary = Path(tmp) / "test" / "summary.json"
        rc = run_mock_sim2sim(
            checkpoint_path=ckpt,
            metrics_file=metrics,
            summary_file=summary,
            steps=2,
            sleep_sec=0,
        )
        assert rc == 0, rc
        lines = metrics.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2, lines
        data = json.loads(summary.read_text(encoding="utf-8"))
        assert data["mode"] == "mock"
        assert data["success_rate"] == 0.85
    print("test_with_metrics self-test passed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NetTrainBridge sim2sim 测试桥接")
    parser.add_argument("--self-test", action="store_true", help="运行内置自检")
    parser.add_argument("--mock", action="store_true", help="Mock 模式（不跑真实仿真）")
    parser.add_argument("--checkpoint", default=None, help="checkpoint 路径或整数（配合 --load-run）")
    parser.add_argument("--load-run", default=None, help="logs/.../exported_data/<load_run>/ 目录名")
    parser.add_argument("--task", default="x1_dh_stand", help="任务名")
    parser.add_argument("--headless", action="store_true", help="无头模式（真实 play）")
    parser.add_argument("--mock-steps", type=int, default=3, help="Mock 指标条数")
    args = parser.parse_args(argv)

    if args.self_test:
        _self_test()
        return 0

    metrics_file = _metrics_env_path()
    summary_file = _summary_path(metrics_file)

    load_run = (
        args.load_run
        or os.environ.get("NETTRAINBRIDGE_LOAD_RUN")
    )
    ckpt_raw = (
        args.checkpoint
        or os.environ.get("NETTRAINBRIDGE_CHECKPOINT")
        or os.environ.get("NETTRAINBRIDGE_CHECKPOINT_PATH")
    )
    checkpoint_path: Path | None = None
    checkpoint_int: int | None = None

    if ckpt_raw is not None:
        p = Path(str(ckpt_raw))
        if p.suffix == ".pt" and p.exists():
            checkpoint_path = p
            parsed_run, parsed_ckpt = _parse_checkpoint_layout(p)
            load_run = load_run or parsed_run
            checkpoint_int = parsed_ckpt
        else:
            try:
                checkpoint_int = int(ckpt_raw)
            except ValueError:
                checkpoint_path = p

    if args.mock:
        ckpt = checkpoint_path or Path(
            ckpt_raw or os.environ.get("NETTRAINBRIDGE_CHECKPOINT_PATH") or "model.pt",
        )
        return run_mock_sim2sim(
            checkpoint_path=Path(ckpt),
            metrics_file=metrics_file,
            summary_file=summary_file,
            steps=args.mock_steps,
        )

    if not load_run or checkpoint_int is None:
        print(
            "[test_with_metrics] 真实模式需要 --load-run 与 --checkpoint=<int> "
            "（或 NETTRAINBRIDGE_LOAD_RUN / NETTRAINBRIDGE_CHECKPOINT）",
            file=sys.stderr,
        )
        return 1

    return run_real_sim2sim(
        task=args.task,
        load_run=load_run,
        checkpoint=checkpoint_int,
        metrics_file=metrics_file,
        summary_file=summary_file,
        headless=args.headless,
        checkpoint_path=checkpoint_path,
    )


if __name__ == "__main__":
    raise SystemExit(main())
