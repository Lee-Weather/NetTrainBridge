from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from config import AgentConfig

logger = logging.getLogger("gradmotion.agent")


class JobRunnerError(Exception):
    """任务执行失败时抛出。"""

    def __init__(self, message: str, returncode: int | None = None):
        super().__init__(message)
        self.returncode = returncode


class JobRunner:
    """任务执行器，负责 clone 代码、安装依赖、启动训练。"""

    def __init__(self, config: AgentConfig):
        self.config = config

    # ── 准备阶段 ──

    def prepare(self, repo_url: str, commit_sha: str, job_id: str) -> Path:
        """准备任务环境: clone + checkout + install。

        Args:
            repo_url: 代码仓库地址
            commit_sha: 提交 SHA 或分支名 (如 'main')
            job_id: 任务 ID

        Returns:
            工作目录路径
        """
        job_dir = Path(self.config.workspace) / job_id

        # 清理已存在的目录
        if job_dir.exists():
            logger.info("清理已存在的工作目录: %s", job_dir)
            shutil.rmtree(job_dir)

        job_dir.mkdir(parents=True, exist_ok=True)

        # 1. Clone 仓库
        self._clone_repo(repo_url, job_dir)

        # 2. Checkout 到指定 commit/branch
        self._checkout(job_dir, commit_sha)

        # 3. 安装依赖
        self._install_dependencies(job_dir)

        logger.info("任务环境准备完成: %s", job_dir)
        return job_dir

    def _clone_repo(self, repo_url: str, target_dir: Path):
        """克隆代码仓库。"""
        logger.info("克隆仓库: %s -> %s", repo_url, target_dir)

        cmd = ["git", "clone", repo_url, str(target_dir)]
        env = self._get_git_env()

        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error("git clone 失败: %s", result.stderr)
            raise JobRunnerError(
                f"git clone 失败: {result.stderr}",
                returncode=result.returncode,
            )

        logger.info("克隆完成")

    def _checkout(self, repo_dir: Path, commit_sha: str):
        """切换到指定 commit 或分支。"""
        logger.info("切换到: %s", commit_sha)

        result = subprocess.run(
            ["git", "checkout", commit_sha],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error("git checkout 失败: %s", result.stderr)
            raise JobRunnerError(
                f"git checkout {commit_sha} 失败: {result.stderr}",
                returncode=result.returncode,
            )

        logger.info("切换完成")

    def _install_dependencies(self, repo_dir: Path):
        """安装 Python 依赖。"""
        # 检查 setup.py 或 pyproject.toml
        has_setup_py = (repo_dir / "setup.py").exists()
        has_pyproject = (repo_dir / "pyproject.toml").exists()
        has_requirements = (repo_dir / "requirements.txt").exists()

        if has_setup_py or has_pyproject:
            logger.info("安装包 (pip install -e .)")
            result = self._run(
                ["pip", "install", "-e", "."],
                cwd=repo_dir,
            )
            if result.returncode != 0:
                logger.warning("pip install -e . 失败: %s", result.stderr)
                # 不抛出异常，继续执行

        if has_requirements:
            logger.info("安装依赖 (pip install -r requirements.txt)")
            result = self._run(
                ["pip", "install", "-r", "requirements.txt"],
                cwd=repo_dir,
            )
            if result.returncode != 0:
                logger.warning("pip install -r requirements.txt 失败: %s", result.stderr)

        logger.info("依赖安装完成")

    # ── 训练阶段 ──

    def start(self, job_dir: Path, job_id: str) -> subprocess.Popen:
        """启动训练进程。

        Args:
            job_dir: 工作目录
            job_id: 任务 ID

        Returns:
            训练进程 Popen 对象
        """
        # 构建训练命令
        train_cmd = self.config.train_command.format(job_id=job_id)
        cmd = self._wrap_conda(shlex.split(train_cmd))

        logger.info("启动训练: %s", shlex.join(cmd))

        # 日志文件
        log_file = job_dir / "train.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # 指标文件
        metrics_file = job_dir / "metrics.jsonl"

        # 启动子进程
        env = self._get_git_env()
        env["GRADMOTION_JOB_ID"] = job_id
        env["GRADMOTION_METRICS_FILE"] = str(metrics_file)

        with open(log_file, "w") as f:
            process = subprocess.Popen(
                cmd,
                cwd=job_dir,
                stdout=f,
                stderr=subprocess.STDOUT,
                env=env,
            )

        logger.info("训练进程已启动, PID=%d, 日志=%s", process.pid, log_file)
        return process

    def wait(self, process: subprocess.Popen, timeout: int | None = None) -> int:
        """等待训练完成。

        Args:
            process: 训练进程
            timeout: 超时时间 (秒)

        Returns:
            进程退出码
        """
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("训练进程超时, 终止中...")
            process.terminate()
            try:
                return process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                return process.wait()

    def kill(self, process: subprocess.Popen):
        """终止训练进程。"""
        logger.warning("终止训练进程 PID=%d", process.pid)
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    # ── 辅助方法 ──

    def _wrap_conda(self, cmd: list[str]) -> list[str]:
        """在指定 conda 环境中执行命令。"""
        if not self.config.conda_env:
            return cmd
        return [
            "conda", "run", "-n", self.config.conda_env,
            "--no-capture-output", *cmd,
        ]

    def _run(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        env: dict | None = None,
    ) -> subprocess.CompletedProcess:
        """执行子进程命令，自动套用 conda 环境。"""
        full_cmd = self._wrap_conda(cmd)
        logger.debug("执行命令: %s", shlex.join(full_cmd))
        return subprocess.run(
            full_cmd,
            cwd=cwd,
            env=env or self._get_git_env(),
            capture_output=True,
            text=True,
        )

    def _get_git_env(self) -> dict:
        """获取 git 命令的环境变量 (含代理配置)。"""
        import os
        env = os.environ.copy()

        if self.config.proxy:
            # git 使用 HTTP_PROXY 和 HTTPS_PROXY
            env["HTTP_PROXY"] = self.config.proxy
            env["HTTPS_PROXY"] = self.config.proxy

        return env

    def cleanup(self, job_dir: Path):
        """清理工作目录。"""
        if job_dir.exists():
            logger.info("清理工作目录: %s", job_dir)
            shutil.rmtree(job_dir)

    def get_log_file(self, job_dir: Path) -> Path:
        """获取日志文件路径。"""
        return job_dir / "train.log"

    def get_metrics_file(self, job_dir: Path) -> Path:
        """获取指标文件路径。"""
        return job_dir / "metrics.jsonl"

    def find_best_model(self, job_dir: Path) -> Optional[Path]:
        """查找最佳模型文件。

        搜索顺序:
        1. logs/**/model_*.pt (最新)
        2. log/exported_policies/**/*.pt (JIT 模型)
        """
        # 方案 1: 查找 checkpoint
        pattern = self.config.model_search_pattern
        models = list(job_dir.glob(pattern))
        if models:
            # 按修改时间排序，取最新的
            best = max(models, key=lambda p: p.stat().st_mtime)
            logger.info("找到模型: %s", best)
            return best

        # 方案 2: 查找 JIT 模型
        jit_pattern = self.config.jit_model_search_pattern
        jit_models = list(job_dir.glob(jit_pattern))
        if jit_models:
            best = max(jit_models, key=lambda p: p.stat().st_mtime)
            logger.info("找到 JIT 模型: %s", best)
            return best

        logger.warning("未找到模型文件")
        return None
