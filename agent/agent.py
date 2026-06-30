from __future__ import annotations

import asyncio
import functools
import logging
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from api_client import APIClient, APIError
from config import AgentConfig
from heartbeat import create_heartbeat_reporter
from job_runner import JobRunner, JobRunnerError
from log_monitor import LogMonitor
from metrics_reader import MetricsReader

logger = logging.getLogger("nettrainbridge.agent")


async def _run_in_thread(func, *args, **kwargs):
    """在后台线程执行同步函数（兼容 Python 3.8，无 asyncio.to_thread）。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, functools.partial(func, *args, **kwargs),
    )


@dataclass
class RunningJob:
    """当前正在执行的任务上下文。"""

    job_id: str
    repo_url: str
    commit_sha: str
    job_dir: Path
    process: subprocess.Popen


class Agent:
    """NetTrainBridge Agent 主程序。"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.api_client = APIClient(config)
        self.job_runner = JobRunner(config)
        self.heartbeat_reporter = create_heartbeat_reporter(
            self.api_client, config,
        )

        self._running_job: Optional[RunningJob] = None
        self._log_monitor: Optional[LogMonitor] = None
        self._metrics_reader: Optional[MetricsReader] = None
        self._shutdown_event = asyncio.Event()

    async def run(self):
        """启动 Agent，并发运行主循环与上报任务。"""
        workspace = Path(self.config.workspace)
        try:
            workspace.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(
                "工作目录不可用: %s (%s)。"
                "若曾 export NETTRAINBRIDGE_WORKSPACE，请先 unset 或改为可写路径，"
                "例如: export NETTRAINBRIDGE_WORKSPACE=~/czy/nettrainbridge",
                workspace, e,
            )
            raise

        logger.info(
            "Agent 启动, ID=%s, 服务器=%s, workspace=%s, conda=%s, 轮询=%ds",
            self.config.agent_id,
            self.config.server_url,
            workspace,
            self.config.conda_env or "(系统 Python)",
            self.config.poll_interval,
        )

        await self._recover_interrupted_jobs()

        await asyncio.gather(
            self._main_loop(),
            self._log_loop(),
            self._metrics_loop(),
            self._heartbeat_loop(),
        )

    async def shutdown(self):
        """优雅关闭 Agent。"""
        logger.info("Agent 正在关闭...")
        self._shutdown_event.set()

        if self._running_job and self._running_job.process.poll() is None:
            self.job_runner.kill(self._running_job.process)

        self.heartbeat_reporter.shutdown()
        await self.api_client.close()

    # ── 主循环 ──

    async def _main_loop(self):
        """轮询任务、监控训练进程。"""
        while not self._shutdown_event.is_set():
            try:
                if self._running_job is None:
                    await self._poll_and_claim()
                    interval = self.config.poll_interval
                else:
                    await self._check_process()
                    interval = 2
            except Exception:
                logger.exception("Agent 主循环错误")
                interval = self.config.poll_interval

            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=interval,
                )
                break
            except asyncio.TimeoutError:
                pass

    async def _poll_and_claim(self):
        """轮询并抢占待处理任务。"""
        jobs = await self.api_client.get_pending_jobs()
        if not jobs:
            return

        job = jobs[0]
        job_id = job["id"]
        logger.info("发现任务 %s, 正在抢占...", job_id)

        try:
            claimed = await self.api_client.claim_job(job_id)
        except APIError as e:
            if e.status_code == 409:
                logger.info("任务 %s 已被其他 Agent 抢占", job_id)
                return
            raise

        logger.info("抢占成功, 开始准备环境...")
        await self._start_job(claimed)

    async def _start_job(self, job: dict):
        """准备环境并启动训练。"""
        if self._running_job is not None:
            return

        job_id = job["id"]
        repo_url = job["repo_url"]
        commit_sha = job["commit_sha"]

        try:
            job_dir = await _run_in_thread(
                self.job_runner.prepare, repo_url, commit_sha, job_id,
            )
        except JobRunnerError as e:
            logger.error("任务 %s 准备失败: %s", job_id, e)
            await self._update_status_safe(
                job_id, "FAILED", error_msg=str(e),
            )
            return

        process = await _run_in_thread(
            self.job_runner.start, job_dir, job_id,
        )
        await self._update_status_safe(job_id, "RUNNING")

        self._log_monitor = LogMonitor(self.job_runner.get_log_file(job_dir))
        self._metrics_reader = MetricsReader(
            self.job_runner.get_metrics_file(job_dir),
        )
        self._running_job = RunningJob(
            job_id=job_id,
            repo_url=repo_url,
            commit_sha=commit_sha,
            job_dir=job_dir,
            process=process,
        )
        logger.info("训练进程已启动, 任务 %s 进入 RUNNING", job_id)

    async def _check_process(self):
        """检查训练进程是否结束。"""
        if self._running_job is None:
            return

        if self._running_job.process.poll() is None:
            return

        exit_code = self._running_job.process.returncode
        logger.info(
            "训练完成, 任务 %s, exit_code=%s",
            self._running_job.job_id, exit_code,
        )
        await self._on_training_complete(
            exit_code if exit_code is not None else 1,
        )

    async def _on_training_complete(self, exit_code: int):
        """训练结束：上报剩余数据、上传模型、更新状态。"""
        job = self._running_job
        if job is None:
            return

        await self._flush_logs_and_metrics()

        if exit_code == 0:
            model = await _run_in_thread(
                self.job_runner.find_best_model, job.job_dir,
            )
            if model:
                try:
                    await self.api_client.upload_checkpoint(job.job_id, model)
                    logger.info("模型上传成功: %s", model.name)
                except APIError as e:
                    logger.error("模型上传失败: %s", e)
                    await self._update_status_safe(
                        job.job_id, "FAILED",
                        error_msg=f"模型上传失败: {e}",
                    )
                    self._clear_running_job()
                    return
            else:
                logger.warning("训练成功但未找到模型文件")

            await self._update_status_safe(job.job_id, "COMPLETED")
            logger.info("任务 %s 已完成", job.job_id)
        else:
            await self._update_status_safe(
                job.job_id, "FAILED",
                error_msg=f"Training failed with exit code {exit_code}",
            )
            logger.error("任务 %s 失败, exit_code=%s", job.job_id, exit_code)

        self._clear_running_job()

    def _clear_running_job(self):
        """清理当前任务上下文。"""
        self._running_job = None
        self._log_monitor = None
        self._metrics_reader = None

    # ── 上报循环 ──

    async def _log_loop(self):
        """定期上报训练日志。"""
        while not self._shutdown_event.is_set():
            if self._running_job and self._log_monitor:
                try:
                    content = self._log_monitor.read_new_content()
                    if content:
                        await self.api_client.append_logs(
                            self._running_job.job_id, content,
                        )
                except APIError as e:
                    logger.warning("日志上报失败: %s", e)

            await self._sleep_or_shutdown(self.config.log_upload_interval)

    async def _metrics_loop(self):
        """定期上报训练指标。"""
        while not self._shutdown_event.is_set():
            if self._running_job and self._metrics_reader:
                try:
                    metrics = self._metrics_reader.read_new_metrics()
                    if metrics:
                        await self.api_client.append_metrics(
                            self._running_job.job_id, metrics,
                        )
                except APIError as e:
                    logger.warning("指标上报失败: %s", e)

            await self._sleep_or_shutdown(self.config.metrics_upload_interval)

    async def _heartbeat_loop(self):
        """定期上报心跳。"""
        while not self._shutdown_event.is_set():
            if self._running_job:
                try:
                    await self.heartbeat_reporter.send_once(
                        self._running_job.job_id,
                    )
                except APIError as e:
                    logger.warning("心跳上报失败: %s", e)

            await self._sleep_or_shutdown(self.config.heartbeat_interval)

    async def _flush_logs_and_metrics(self):
        """训练结束前刷完剩余的日志和指标。"""
        if self._running_job is None:
            return

        job_id = self._running_job.job_id
        try:
            if self._log_monitor:
                content = self._log_monitor.read_new_content()
                if content:
                    await self.api_client.append_logs(job_id, content)
            if self._metrics_reader:
                metrics = self._metrics_reader.read_new_metrics()
                if metrics:
                    await self.api_client.append_metrics(job_id, metrics)
        except APIError as e:
            logger.warning("刷写剩余日志/指标失败: %s", e)

    # ── 崩溃恢复 ──

    async def _recover_interrupted_jobs(self):
        """启动时恢复本 Agent 未完成的任务。"""
        workspace = Path(self.config.workspace)
        if not workspace.exists():
            return

        for job_dir in sorted(workspace.iterdir()):
            if not job_dir.is_dir():
                continue

            job_id = job_dir.name
            try:
                job = await self.api_client.get_job(job_id)
            except APIError:
                continue

            if job.get("agent_id") != self.config.agent_id:
                continue

            status = job.get("status")
            if status == "ASSIGNED":
                logger.info("恢复中断的 ASSIGNED 任务: %s", job_id)
                await self._start_job(job)
                return

            if status == "RUNNING":
                logger.warning(
                    "发现中断的 RUNNING 任务 %s, 标记为 FAILED", job_id,
                )
                log_monitor = LogMonitor(
                    self.job_runner.get_log_file(job_dir),
                )
                metrics_reader = MetricsReader(
                    self.job_runner.get_metrics_file(job_dir),
                )
                try:
                    content = log_monitor.read_new_content()
                    if content:
                        await self.api_client.append_logs(job_id, content)
                    metrics = metrics_reader.read_new_metrics()
                    if metrics:
                        await self.api_client.append_metrics(job_id, metrics)
                except APIError as e:
                    logger.warning("恢复上报失败: %s", e)
                await self._update_status_safe(
                    job_id, "FAILED",
                    error_msg="Agent 重启，训练进程已丢失",
                )
                return

    # ── 工具方法 ──

    async def _update_status_safe(
        self,
        job_id: str,
        status: str,
        error_msg: Optional[str] = None,
    ):
        """更新任务状态，失败时仅记录日志。"""
        try:
            await self.api_client.update_status(job_id, status, error_msg)
        except APIError as e:
            logger.error("更新任务 %s 状态失败: %s", job_id, e)

    async def _sleep_or_shutdown(self, seconds: float):
        """可中断的 sleep。"""
        try:
            await asyncio.wait_for(self._shutdown_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass


def setup_logging():
    """配置日志格式。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _run_agent():
    """运行 Agent 并处理退出信号。"""
    config = AgentConfig.load()
    agent = Agent(config)

    loop = asyncio.get_running_loop()
    shutdown_task: Optional[asyncio.Task] = None

    def _request_shutdown():
        nonlocal shutdown_task
        if shutdown_task is None:
            shutdown_task = asyncio.create_task(agent.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            # Windows 不支持 add_signal_handler
            pass

    try:
        await agent.run()
    finally:
        await agent.shutdown()


def main():
    setup_logging()
    try:
        asyncio.run(_run_agent())
    except KeyboardInterrupt:
        logger.info("Agent 已停止")


if __name__ == "__main__":
    main()
