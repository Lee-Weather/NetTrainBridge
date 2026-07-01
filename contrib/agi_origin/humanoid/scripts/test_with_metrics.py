#!/usr/bin/env python3
"""sim2sim 测试桥接脚本（框架 / Mock 占位）。

本文件用于打通 NTB test 链路，**不包含真实 play/eval 实现**。
后续在 ``run_real_sim2sim()`` 中接入 agi_origin 的 play.py / eval 逻辑。

环境变量（与 train_with_metrics 对齐）：
  - NETTRAINBRIDGE_METRICS_FILE / GRADMOTION_METRICS_FILE → metrics.jsonl
  - NETTRAINBRIDGE_JOB_ID / GRADMOTION_JOB_ID
  - NETTRAINBRIDGE_CHECKPOINT_PATH → 待测模型路径（Agent 注入）

用法：
  python test_with_metrics.py --self-test
  python test_with_metrics.py --mock --checkpoint /path/to/model.pt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# 真实 sim2sim 实现入口（后续填写，当前未实现）
# ---------------------------------------------------------------------------


def run_real_sim2sim(
    *,
    checkpoint_path: Path,
    task: str,
    metrics_file: Path,
    summary_file: Path,
    headless: bool,
) -> int:
    """包装 play.py / eval，解析 stdout 写入 metrics_file。

    TODO(R1): 对接 agi_origin humanoid/scripts/play.py（或等价入口）
    TODO(R1): 从 stdout 解析 reward / success_rate 等测试指标
    TODO(R1): 可选录屏、轨迹文件写入 summary_file 同目录
    """
    raise NotImplementedError(
        "真实 sim2sim 尚未实现；请使用 --mock，或等待 R1 版本接入 play.py"
    )


# ---------------------------------------------------------------------------
# Mock 占位（步骤 7～8 验收用）
# ---------------------------------------------------------------------------


def _metrics_env_path() -> Path:
    for key in ("NETTRAINBRIDGE_METRICS_FILE", "GRADMOTION_METRICS_FILE"):
        value = os.environ.get(key)
        if value:
            return Path(value)
    return Path("metrics.jsonl")


def _summary_path(metrics_file: Path) -> Path:
    # Agent / Server 约定：与 metrics 同级的 test/ 目录
    test_dir = metrics_file.parent / "test"
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir / "summary.json"


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


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


def _self_test() -> None:
    import tempfile

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
    parser = argparse.ArgumentParser(description="NetTrainBridge sim2sim 测试桥接（框架）")
    parser.add_argument("--self-test", action="store_true", help="运行内置自检")
    parser.add_argument("--mock", action="store_true", help="Mock 模式（不跑真实仿真）")
    parser.add_argument("--checkpoint", default=None, help="模型 checkpoint 路径")
    parser.add_argument("--task", default="x1_dh_stand", help="任务名（真实模式用）")
    parser.add_argument("--headless", action="store_true", help="无头模式（真实模式用）")
    parser.add_argument("--mock-steps", type=int, default=3, help="Mock 指标条数")
    args = parser.parse_args(argv)

    if args.self_test:
        _self_test()
        return 0

    metrics_file = _metrics_env_path()
    summary_file = _summary_path(metrics_file)

    ckpt_env = os.environ.get("NETTRAINBRIDGE_CHECKPOINT_PATH")
    checkpoint = Path(args.checkpoint or ckpt_env or "model.pt")

    if args.mock:
        return run_mock_sim2sim(
            checkpoint_path=checkpoint,
            metrics_file=metrics_file,
            summary_file=summary_file,
            steps=args.mock_steps,
        )

    return run_real_sim2sim(
        checkpoint_path=checkpoint,
        task=args.task,
        metrics_file=metrics_file,
        summary_file=summary_file,
        headless=args.headless,
    )


if __name__ == "__main__":
    raise SystemExit(main())
