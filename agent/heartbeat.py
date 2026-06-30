from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from api_client import APIClient, APIError
from config import AgentConfig

logger = logging.getLogger("nettrainbridge.agent")


@dataclass
class GPUInfo:
    """GPU 状态快照。"""

    gpu_util: Optional[float] = None
    gpu_mem_used: Optional[float] = None
    gpu_mem_total: Optional[float] = None


class HeartbeatReporter:
    """定期采集 GPU 状态并上报云服务器。"""

    def __init__(self, api_client: APIClient, interval: int = 30):
        self.api_client = api_client
        self.interval = interval
        self._nvml_initialized = False

    def collect_gpu_info(self) -> GPUInfo:
        """使用 pynvml 采集 GPU 信息，无 GPU 时返回空值。"""
        try:
            import pynvml

            if not self._nvml_initialized:
                pynvml.nvmlInit()
                self._nvml_initialized = True

            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return GPUInfo(
                gpu_util=float(util.gpu),
                gpu_mem_used=mem.used / 1024**3,
                gpu_mem_total=mem.total / 1024**3,
            )
        except Exception as e:
            logger.debug("GPU 信息采集失败: %s", e)
            return GPUInfo()

    async def send_once(self, job_id: str) -> dict:
        """采集并上报一次心跳。"""
        info = self.collect_gpu_info()
        result = await self.api_client.send_heartbeat(
            job_id,
            gpu_util=info.gpu_util,
            gpu_mem_used=info.gpu_mem_used,
            gpu_mem_total=info.gpu_mem_total,
        )
        if info.gpu_util is not None:
            logger.info(
                "心跳上报: GPU %s%%, 显存 %.1f/%.1f GB",
                info.gpu_util,
                info.gpu_mem_used or 0,
                info.gpu_mem_total or 0,
            )
        else:
            logger.info("心跳上报: 无 GPU 数据")
        return result

    async def run(
        self,
        job_id: str,
        stop_event: Optional[asyncio.Event] = None,
    ):
        """心跳上报循环，直到 stop_event 被设置。"""
        while not (stop_event and stop_event.is_set()):
            try:
                await self.send_once(job_id)
            except APIError as e:
                logger.warning("心跳上报失败: %s", e)

            if stop_event and stop_event.is_set():
                break
            await asyncio.sleep(self.interval)

    def shutdown(self):
        """释放 pynvml 资源。"""
        if not self._nvml_initialized:
            return
        try:
            import pynvml
            pynvml.nvmlShutdown()
        except Exception as e:
            logger.debug("pynvml 关闭失败: %s", e)
        finally:
            self._nvml_initialized = False


def create_heartbeat_reporter(
    api_client: APIClient,
    config: AgentConfig,
) -> HeartbeatReporter:
    """根据 Agent 配置创建心跳上报器。"""
    return HeartbeatReporter(api_client, interval=config.heartbeat_interval)
