#!/usr/bin/env python3
"""包装 humanoid/scripts/train.py，将训练日志解析为 GradMotion metrics.jsonl。"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

# agi_origin dh_on_policy_runner.py 实际输出格式
ITERATION_PATTERN = re.compile(r"Learning iteration\s+(\d+)/")
MEAN_REWARD_PATTERN = re.compile(r"Mean reward:\s+([-\d.eE+]+)")
VALUE_LOSS_PATTERN = re.compile(r"Value function loss:\s+([-\d.eE+]+)")
SURROGATE_LOSS_PATTERN = re.compile(r"Surrogate loss:\s+([-\d.eE+]+)")

# 兼容其他 legged_gym 风格单行日志
LEGACY_METRIC_PATTERN = re.compile(
    r"iteration:\s*(\d+).*?mean_reward:\s*([-\d.eE+]+).*?loss:\s*([-\d.eE+]+)"
)


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub("", text)


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


class MetricParser:
    """从 train.py stdout 增量解析指标。"""

    def __init__(self):
        self._iteration: int | None = None
        self._value_loss: float | None = None
        self._surrogate_loss: float | None = None
        self._mean_reward: float | None = None
        self._last_step: int = -1

    def feed_line(self, line: str) -> dict | None:
        clean = strip_ansi(line).strip()
        if not clean:
            return None

        legacy = LEGACY_METRIC_PATTERN.search(clean)
        if legacy:
            return self._emit(
                step=int(legacy.group(1)),
                loss=float(legacy.group(3)),
                reward=float(legacy.group(2)),
            )

        match = ITERATION_PATTERN.search(clean)
        if match:
            self._iteration = int(match.group(1))
            return None

        match = VALUE_LOSS_PATTERN.search(clean)
        if match:
            self._value_loss = float(match.group(1))
            return None

        match = SURROGATE_LOSS_PATTERN.search(clean)
        if match:
            self._surrogate_loss = float(match.group(1))
            return None

        match = MEAN_REWARD_PATTERN.search(clean)
        if match:
            self._mean_reward = float(match.group(1))
            return self._try_emit()

        # 每个 iteration 块末尾有 Total timesteps 行；无 Mean reward 时在此落盘
        if clean.startswith("Total timesteps:"):
            return self._try_emit()

        return None

    def _combined_loss(self) -> float | None:
        if self._value_loss is not None and self._surrogate_loss is not None:
            return (self._value_loss + self._surrogate_loss) / 2
        if self._value_loss is not None:
            return self._value_loss
        if self._surrogate_loss is not None:
            return self._surrogate_loss
        return None

    def _try_emit(self) -> dict | None:
        if self._iteration is None:
            return None

        loss = self._combined_loss()
        if loss is None and self._mean_reward is None:
            return None

        metric = self._emit(
            step=self._iteration,
            loss=loss,
            reward=self._mean_reward,
        )
        self._value_loss = None
        self._surrogate_loss = None
        self._mean_reward = None
        return metric

    def _emit(
        self,
        *,
        step: int,
        loss: float | None,
        reward: float | None,
    ) -> dict | None:
        if step <= self._last_step:
            return None

        record: dict = {"step": step}
        if loss is not None:
            record["loss"] = loss
        if reward is not None:
            record["reward"] = reward

        self._last_step = step
        return record


def run_train_with_metrics(argv: list[str] | None = None) -> int:
    metrics_env = os.environ.get("GRADMOTION_METRICS_FILE")
    if not metrics_env:
        print(
            "[train_with_metrics] ERROR: GRADMOTION_METRICS_FILE not set",
            file=sys.stderr,
            flush=True,
        )
        return 1

    metrics_file = Path(metrics_env)
    train_script = Path(__file__).resolve().parent / "train.py"
    if not train_script.exists():
        print(
            f"[train_with_metrics] ERROR: train.py not found at {train_script}",
            file=sys.stderr,
            flush=True,
        )
        return 1

    cmd = [sys.executable, str(train_script), *(argv if argv is not None else sys.argv[1:])]
    print(f"[train_with_metrics] metrics_file={metrics_file}", flush=True)
    print(f"[train_with_metrics] command={' '.join(cmd)}", flush=True)

    parser = MetricParser()
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=os.environ.copy(),
    )

    assert process.stdout is not None
    try:
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            metric = parser.feed_line(line)
            if metric:
                append_jsonl(metrics_file, metric)
    finally:
        returncode = process.wait()

    if returncode != 0:
        print(
            f"[train_with_metrics] train.py exited with code {returncode}",
            file=sys.stderr,
            flush=True,
        )
    else:
        print("[train_with_metrics] training complete", flush=True)

    return returncode


def _self_test() -> None:
    sample = """
################################################################################
                       Learning iteration 3/1000

                       Computation: 12345 steps/s (collection: 0.100s, learning 0.050s)
                  Value function loss: 0.1234
                       Surrogate loss: 0.5678
                     Mean action noise std: 1.00
                            Mean reward: 2.50
                   Mean episode length: 100.00
--------------------------------------------------------------------------------
                     Total timesteps: 12000
                       Iteration time: 0.15s
                         Total time: 0.45s
                               ETA: 150.0s
"""
    parser = MetricParser()
    metrics: list[dict] = []
    for line in sample.splitlines():
        metric = parser.feed_line(line)
        if metric:
            metrics.append(metric)

    assert len(metrics) == 1, metrics
    assert metrics[0]["step"] == 3
    assert metrics[0]["reward"] == 2.5
    assert abs(metrics[0]["loss"] - 0.3456) < 1e-6
    print("metric parser self-test passed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        _self_test()
    else:
        raise SystemExit(run_train_with_metrics())
