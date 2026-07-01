from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("nettrainbridge.agent")

# 与云服务器 MetricCreate 对齐的字段
_METRIC_FIELDS = ("step", "loss", "reward", "lr")


class MetricsReader:
    """解析 metrics.jsonl，增量读取新指标。"""

    def __init__(self, metrics_file: Path, *, kind: str = "train"):
        self.metrics_file = metrics_file
        self.kind = kind
        self.last_step = -1

    def reset(self):
        """重置已读进度（新任务开始时调用）。"""
        self.last_step = -1

    def read_new_metrics(self) -> list[dict]:
        """读取 step > last_step 的新指标。

        Returns:
            格式: [{"step": 100, "loss": 0.5, "reward": 1.2}, ...]
        """
        if not self.metrics_file.exists():
            return []

        new_metrics: list[dict] = []

        try:
            with open(
                self.metrics_file, "r", encoding="utf-8", errors="replace",
            ) as f:
                for line_no, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "跳过无效指标行 %s:%d: %s",
                            self.metrics_file, line_no, e,
                        )
                        continue

                    if not isinstance(record, dict):
                        logger.warning(
                            "跳过非对象指标行 %s:%d",
                            self.metrics_file, line_no,
                        )
                        continue

                    step = record.get("step")
                    if not isinstance(step, int):
                        logger.warning(
                            "跳过缺少 step 的指标行 %s:%d",
                            self.metrics_file, line_no,
                        )
                        continue

                    if step <= self.last_step:
                        continue

                    metric = {"step": step, "kind": record.get("kind", self.kind)}
                    for field in _METRIC_FIELDS:
                        if field == "step":
                            continue
                        value = record.get(field)
                        if value is not None:
                            metric[field] = value

                    new_metrics.append(metric)
                    self.last_step = step

        except OSError as e:
            logger.warning("读取指标失败 %s: %s", self.metrics_file, e)
            return []

        return new_metrics
