from __future__ import annotations

import asyncio
import functools
import json
import logging
import signal
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from api_client import APIClient, APIError
from checkpoint_layout import (
    DEFAULT_TEST_TASK,
    checkpoint_int_from_spec,
    logs_export_dir,
)
from config import AgentConfig
from fetch_runner import FetchRunner, FetchRunnerError
from pull_runner import PullRunnerError, pull_checkpoint_to_logs
from test_context import resolve_test_context
from heartbeat import create_heartbeat_reporter
from job_runner import JobRunner, JobRunnerError
from log_monitor import LogMonitor
from metrics_reader import MetricsReader

logger = logging.getLogger("nettrainbridge.agent")

CLAIMABLE_JOB_TYPES = frozenset({"train", "sync", "test"})


def _summary_is_mock(summary_path: Path) -> bool:
    """判断 test/summary.json 是否为 Mock 模式。"""
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return False
    return isinstance(data, dict) and data.get("mode") == "mock"


def _job_type(job: dict) -> str:
    return job.get("job_type") or "train"


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
    is_test: bool = False


class Agent:
    """NetTrainBridge Agent 主程序。"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.api_client = APIClient(config)
        self.job_runner = JobRunner(config)
        self.fetch_runner = FetchRunner(config)
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

        job = None
        for candidate in jobs:
            if _job_type(candidate) in CLAIMABLE_JOB_TYPES:
                job = candidate
                break
        if job is None:
            skipped = [_job_type(j) for j in jobs]
            logger.debug("跳过不可抢占任务类型: %s", skipped)
            return

        job_id = job["id"]
        logger.info("发现任务 %s (%s), 正在抢占...", job_id, _job_type(job))

        try:
            claimed = await self.api_client.claim_job(job_id)
        except APIError as e:
            if e.status_code == 409:
                logger.info("任务 %s 已被其他 Agent 抢占", job_id)
                return
            raise

        logger.info("抢占成功, 开始处理...")
        await self._start_job(claimed)

    async def _start_job(self, job: dict):
        """按 job_type 分发：sync 仅 clone；train 走训练流程。"""
        if self._running_job is not None:
            return

        job_type = _job_type(job)
        if job_type == "sync":
            await self._run_sync_job(job)
            return
        if job_type == "test":
            await self._run_test_job(job)
            return
        await self._run_train_job(job)

    async def _gm_phase_after_sync(self, job_id: str) -> str:
        """gm test：sync 后进入 pull（默认）或 fetch（兜底直拉 gm）。"""
        meta = await self.api_client.get_job_meta(job_id) or {}
        if meta.get("fetch_mode") == "gm":
            return "fetch"
        return "pull"

    async def _run_test_job(self, job: dict):
        """test job：sync → pull/fetch(gm) → sim2sim → COMPLETED。"""
        job_id = job["id"]
        repo_url = job["repo_url"]
        commit_sha = job["commit_sha"]
        train_source = job.get("train_source") or "ntb"
        phase = job.get("phase") or "sync"
        job_dir = Path(self.config.workspace) / job_id

        await self._update_status_safe(job_id, "RUNNING")

        try:
            if phase == "sync":
                job_dir = await _run_in_thread(
                    self.job_runner.prepare, repo_url, commit_sha, job_id,
                )
                logger.info("test job %s 代码同步完成", job_id)
                if train_source == "gm":
                    next_phase = await self._gm_phase_after_sync(job_id)
                    updated = await self.api_client.update_phase(job_id, next_phase)
                    phase = updated.get("phase", next_phase)
                else:
                    await self.api_client.update_phase(job_id, "test")
                    phase = "test"

            if phase == "pull" and train_source == "gm":
                meta = await self.api_client.get_job_meta(job_id) or {}
                task = meta.get("task") or DEFAULT_TEST_TASK
                load_run = meta.get("load_run")
                if not load_run:
                    raise PullRunnerError(
                        "test job 缺少 load_run（请 ntb test run --load-run）",
                    )

                model_path = await pull_checkpoint_to_logs(
                    self.api_client,
                    job_id,
                    job_dir,
                    meta,
                )
                checkpoint_int = meta.get("checkpoint")
                if checkpoint_int is None:
                    checkpoint_int = checkpoint_int_from_spec(
                        meta.get("gm_checkpoint", "latest"),
                        model_path.name,
                    )
                rel_model = model_path.relative_to(job_dir)
                await self.api_client.put_job_meta(
                    job_id,
                    {
                        "model_filename": model_path.name,
                        "model_path": str(rel_model),
                        "task": task,
                        "load_run": load_run,
                        "checkpoint": int(checkpoint_int),
                        "checkpoint_staged": True,
                    },
                )
                await self.api_client.update_phase(job_id, "test")
                phase = "test"
                logger.info(
                    "test job %s PULL 完成，已落盘 %s",
                    job_id,
                    model_path.name,
                )

            if phase == "fetch" and train_source == "gm":
                gm_task_id = job.get("gm_task_id")
                if not gm_task_id:
                    raise FetchRunnerError("test job 缺少 gm_task_id")

                meta = await self.api_client.get_job_meta(job_id) or {}
                gm_checkpoint = meta.get("gm_checkpoint", "latest")
                task = meta.get("task") or DEFAULT_TEST_TASK
                load_run = meta.get("load_run")
                if not load_run:
                    raise FetchRunnerError(
                        "test job 缺少 load_run（请 ntb test run --load-run）",
                    )

                models_dir = logs_export_dir(job_dir, task, load_run)
                model_path = await _run_in_thread(
                    self.fetch_runner.fetch_checkpoint,
                    gm_task_id,
                    gm_checkpoint,
                    models_dir,
                )
                checkpoint_int = checkpoint_int_from_spec(gm_checkpoint, model_path.name)
                rel_model = model_path.relative_to(job_dir)
                await self.api_client.upload_checkpoint(job_id, model_path)
                await self.api_client.put_job_meta(
                    job_id,
                    {
                        "model_filename": model_path.name,
                        "model_path": str(rel_model),
                        "gm_task_id": gm_task_id,
                        "gm_checkpoint": gm_checkpoint,
                        "task": task,
                        "load_run": load_run,
                        "checkpoint": checkpoint_int,
                    },
                )
                await self.api_client.update_phase(job_id, "test")
                phase = "test"
                logger.info(
                    "test job %s FETCH 完成，已上传 %s",
                    job_id,
                    model_path.name,
                )

            if phase == "test":
                if self._running_job is not None:
                    return
                if not job_dir.is_dir():
                    raise JobRunnerError(f"工作目录不存在: {job_dir}")
                test_ctx = await resolve_test_context(self.api_client, job, job_dir)
                await self._start_test_sim2sim(job, job_dir, test_ctx)
                return

            logger.warning("test job %s 未知阶段 %s", job_id, phase)

        except JobRunnerError as e:
            logger.error("test job %s 失败: %s", job_id, e)
            await self._update_status_safe(job_id, "FAILED", error_msg=str(e))
        except FetchRunnerError as e:
            logger.error("test job %s FETCH 失败: %s", job_id, e)
            await self._update_status_safe(
                job_id, "FAILED", error_msg=f"FETCH failed: {e}",
            )
        except PullRunnerError as e:
            logger.error("test job %s PULL 失败: %s", job_id, e)
            await self._update_status_safe(
                job_id, "FAILED", error_msg=f"PULL failed: {e}",
            )
        except APIError as e:
            logger.error("test job %s API 失败: %s", job_id, e)
            await self._update_status_safe(
                job_id, "FAILED", error_msg=f"API error: {e}",
            )

    async def _start_test_sim2sim(
        self,
        job: dict,
        job_dir: Path,
        test_ctx: dict,
    ) -> None:
        """启动 sim2sim 子进程并注册监控。"""
        job_id = job["id"]
        process = await _run_in_thread(
            self.job_runner.start_test,
            job_dir,
            job_id,
            test_ctx,
        )
        self._log_monitor = LogMonitor(
            self.job_runner.get_log_file(job_dir, is_test=True),
        )
        self._metrics_reader = MetricsReader(
            self.job_runner.get_metrics_file(job_dir),
            kind="test",
        )
        self._running_job = RunningJob(
            job_id=job_id,
            repo_url=job["repo_url"],
            commit_sha=job["commit_sha"],
            job_dir=job_dir,
            process=process,
            is_test=True,
        )
        logger.info("test job %s sim2sim 已启动", job_id)

    async def _run_sync_job(self, job: dict):
        """仅同步代码到 workspace，不启动训练。"""
        job_id = job["id"]
        repo_url = job["repo_url"]
        commit_sha = job["commit_sha"]

        try:
            job_dir = await _run_in_thread(
                self.job_runner.prepare, repo_url, commit_sha, job_id,
            )
        except JobRunnerError as e:
            logger.error("任务 %s 同步失败: %s", job_id, e)
            await self._update_status_safe(
                job_id, "FAILED", error_msg=str(e),
            )
            return

        await self._update_status_safe(job_id, "COMPLETED")
        logger.info("代码同步完成: %s -> %s", job_id, job_dir)

    async def _run_train_job(self, job: dict):
        """准备环境并启动训练。"""
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
        label = "测试" if self._running_job.is_test else "训练"
        logger.info(
            "%s完成, 任务 %s, exit_code=%s",
            label, self._running_job.job_id, exit_code,
        )
        if self._running_job.is_test:
            await self._on_test_complete(exit_code if exit_code is not None else 1)
        else:
            await self._on_training_complete(
                exit_code if exit_code is not None else 1,
            )

    async def _on_test_complete(self, exit_code: int):
        """sim2sim 结束：刷指标、上传 test CSV、COMPLETED。"""
        job = self._running_job
        if job is None:
            return

        await self._flush_logs_and_metrics()

        if exit_code == 0:
            meta_patch = {
                "job_type": "test",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            csv_path = self.job_runner.find_test_csv(job.job_dir)
            if csv_path is not None:
                try:
                    await self.api_client.upload_test_file(job.job_id, csv_path)
                    logger.info("test CSV 已上传: %s", csv_path.name)
                    meta_patch["test_artifact"] = csv_path.name
                    meta_patch["test_artifact_size"] = csv_path.stat().st_size
                except APIError as e:
                    logger.error("test CSV 上传失败: %s", e)
                    await self._update_status_safe(
                        job.job_id, "FAILED",
                        error_msg=f"test csv upload failed: {e}",
                    )
                    self._clear_running_job()
                    return
            else:
                summary = self.job_runner.get_test_summary_file(job.job_dir)
                if summary.is_file() and _summary_is_mock(summary):
                    try:
                        await self.api_client.upload_test_file(job.job_id, summary)
                        logger.info("mock test summary 已上传: %s", summary.name)
                    except APIError as e:
                        logger.error("mock test summary 上传失败: %s", e)
                        await self._update_status_safe(
                            job.job_id, "FAILED",
                            error_msg=f"mock test summary upload failed: {e}",
                        )
                        self._clear_running_job()
                        return
                else:
                    await self._update_status_safe(
                        job.job_id, "FAILED",
                        error_msg="no isaac_diag csv found for real test",
                    )
                    self._clear_running_job()
                    return

            await self.api_client.put_job_meta(job.job_id, meta_patch)
            await self.api_client.update_phase(job.job_id, "done")
            await self._update_status_safe(job.job_id, "COMPLETED")
            logger.info("test job %s 已完成", job.job_id)
        else:
            await self._update_status_safe(
                job.job_id, "FAILED",
                error_msg=f"Test failed with exit code {exit_code}",
            )
            logger.error("test job %s 失败, exit_code=%s", job.job_id, exit_code)

        self._clear_running_job()

    async def _on_training_complete(self, exit_code: int):
        """训练结束：上报剩余数据、上传模型、更新状态。"""
        job = self._running_job
        if job is None:
            return

        await self._flush_logs_and_metrics()

        model_path: Optional[Path] = None
        if exit_code == 0:
            model_path = await _run_in_thread(
                self.job_runner.find_best_model, job.job_dir,
            )
            if model_path:
                try:
                    await self.api_client.upload_checkpoint(job.job_id, model_path)
                    logger.info("模型上传成功: %s", model_path.name)
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

            await self._write_train_meta(job, model_path)
            await self._update_status_safe(job.job_id, "COMPLETED")
            logger.info("任务 %s 已完成", job.job_id)
        else:
            await self._update_status_safe(
                job.job_id, "FAILED",
                error_msg=f"Training failed with exit code {exit_code}",
            )
            logger.error("任务 %s 失败, exit_code=%s", job.job_id, exit_code)

        self._clear_running_job()

    async def _write_train_meta(
        self,
        job: RunningJob,
        model_path: Optional[Path],
    ) -> None:
        """训练成功后写入 Server meta.json。"""
        meta = {
            "job_id": job.job_id,
            "job_type": "train",
            "train_source": "ntb",
            "repo_url": job.repo_url,
            "commit_sha": job.commit_sha,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        if model_path is not None:
            meta["model_filename"] = model_path.name
        try:
            await self.api_client.put_job_meta(job.job_id, meta)
            logger.info("任务 %s meta 已写入 Server", job.job_id)
        except APIError as e:
            logger.warning("任务 %s meta 写入失败: %s", job.job_id, e)

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
            job_type = _job_type(job)
            if status == "ASSIGNED":
                logger.info("恢复中断的 ASSIGNED 任务: %s", job_id)
                await self._start_job(job)
                return

            if status == "RUNNING" and job_type == "test":
                phase = job.get("phase") or "sync"
                if phase in ("sync", "fetch", "test"):
                    logger.info("恢复中断的 test 任务: %s phase=%s", job_id, phase)
                    await self._run_test_job(job)
                    return

            if status == "RUNNING":
                logger.warning(
                    "发现中断的 RUNNING 任务 %s, 标记为 FAILED", job_id,
                )
                is_test_log = (job_dir / "test" / "test.log").is_file()
                log_monitor = LogMonitor(
                    self.job_runner.get_log_file(job_dir, is_test=is_test_log),
                )
                metrics_reader = MetricsReader(
                    self.job_runner.get_metrics_file(job_dir),
                    kind="test" if is_test_log else "train",
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
                err = (
                    "Agent 重启，测试进程已丢失"
                    if is_test_log
                    else "Agent 重启，训练进程已丢失"
                )
                await self._update_status_safe(job_id, "FAILED", error_msg=err)
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
        import sys
        from pathlib import Path

        _root = Path(__file__).resolve().parent.parent
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        from config_loader import config_status_message  # noqa: E402

        logger.info(config_status_message())
        asyncio.run(_run_agent())
    except KeyboardInterrupt:
        logger.info("Agent 已停止")


if __name__ == "__main__":
    main()
