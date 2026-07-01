"""test job FETCH 阶段：从 gm 拉 checkpoint 到本地。"""

from __future__ import annotations

import logging
from pathlib import Path

from config import AgentConfig
from gm_client import (
    GMClient,
    GMClientError,
    model_download_url,
    model_filename,
    select_model,
)

logger = logging.getLogger("nettrainbridge.agent.fetch")


class FetchRunnerError(Exception):
    """FETCH 阶段失败。"""


class FetchRunner:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.gm = GMClient(config)

    def fetch_checkpoint(
        self,
        gm_task_id: str,
        gm_checkpoint: str,
        dest_dir: Path,
    ) -> Path:
        """从 gm 下载指定 checkpoint 到 dest_dir，返回本地文件路径。"""
        specifier = (gm_checkpoint or "latest").strip() or "latest"
        list_filter = None if specifier == "latest" else specifier

        try:
            models = self.gm.list_models(gm_task_id, checkpoint=list_filter)
            model = select_model(models, specifier)
            url = model_download_url(model)
            filename = model_filename(model)
            dest = dest_dir / filename
            self.gm.download(url, dest)
        except GMClientError as exc:
            raise FetchRunnerError(str(exc)) from exc

        logger.info(
            "FETCH 完成 gm_task=%s checkpoint=%s -> %s",
            gm_task_id,
            specifier,
            dest,
        )
        return dest
