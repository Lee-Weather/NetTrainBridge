from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("nettrainbridge.agent")


class LogMonitor:
    """基于文件偏移量增量读取训练日志。"""

    def __init__(self, log_file: Path):
        self.log_file = log_file
        self.position = 0

    def reset(self):
        """重置读取位置（新任务开始时调用）。"""
        self.position = 0

    def read_new_lines(self) -> list[str]:
        """读取上次位置之后的新行，跳过空行。"""
        if not self.log_file.exists():
            return []

        try:
            with open(self.log_file, "r", encoding="utf-8", errors="replace") as f:
                file_size = f.seek(0, 2)
                if file_size < self.position:
                    # 日志被截断或轮转，从头读取
                    logger.warning(
                        "日志文件已截断 (%s), 重置读取位置",
                        self.log_file,
                    )
                    self.position = 0

                f.seek(self.position)
                lines = f.readlines()
                self.position = f.tell()
        except OSError as e:
            logger.warning("读取日志失败 %s: %s", self.log_file, e)
            return []

        return [line.rstrip("\n\r") for line in lines if line.strip()]

    def read_new_content(self) -> str:
        """读取新行并合并为单个字符串，便于上报。"""
        lines = self.read_new_lines()
        return "\n".join(lines)
