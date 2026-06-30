import os
import sys
from dataclasses import dataclass
from pathlib import Path

from env_util import get_env

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config_loader import get_setting  # noqa: E402


@dataclass
class AgentConfig:
    """Agent 配置：配置文件 → 环境变量 → 默认值。"""

    # 云服务器
    server_url: str = "http://localhost:8000"
    proxy: str = ""  # 公司代理地址，如 http://10.12.201.122:39000

    # Agent 身份
    agent_id: str = "agent-001"

    # 轮询与上报间隔 (秒)
    poll_interval: int = 30
    heartbeat_interval: int = 30
    log_upload_interval: int = 5
    metrics_upload_interval: int = 10

    # 工作目录 (默认用户主目录下，避免 /workspace 无写权限)
    workspace: str = os.path.expanduser("~/czy/nettrainbridge")

    # Conda 环境 (训练与 pip 安装均在此环境中执行)
    conda_env: str = "F1"

    # 训练命令模板 (针对 agi_origin 仓库)
    # 注意: train.py 在 humanoid/scripts/ 目录下
    train_command: str = "python humanoid/scripts/train.py --task=x1_dh_stand --run_name={job_id} --headless"

    # 模型搜索路径 (相对于仓库根目录)
    model_search_pattern: str = "logs/**/model_*.pt"
    jit_model_search_pattern: str = "log/exported_policies/**/*.pt"

    # HTTP 请求
    request_timeout: int = 30
    max_retries: int = 3

    @classmethod
    def load(cls) -> "AgentConfig":
        """从配置文件与环境变量加载。"""
        instance = cls()

        _fields = [
            ("server_url", "NETTRAINBRIDGE_SERVER_URL", "GRADMOTION_SERVER_URL", str, "http://localhost:8000"),
            ("proxy", "NETTRAINBRIDGE_PROXY", "GRADMOTION_PROXY", str, ""),
            ("agent_id", "NETTRAINBRIDGE_AGENT_ID", "GRADMOTION_AGENT_ID", str, "agent-001"),
            ("poll_interval", "NETTRAINBRIDGE_POLL_INTERVAL", "GRADMOTION_POLL_INTERVAL", int, 30),
            ("heartbeat_interval", "NETTRAINBRIDGE_HEARTBEAT_INTERVAL", "GRADMOTION_HEARTBEAT_INTERVAL", int, 30),
            ("log_upload_interval", "NETTRAINBRIDGE_LOG_UPLOAD_INTERVAL", "GRADMOTION_LOG_UPLOAD_INTERVAL", int, 5),
            ("metrics_upload_interval", "NETTRAINBRIDGE_METRICS_UPLOAD_INTERVAL", "GRADMOTION_METRICS_UPLOAD_INTERVAL", int, 10),
            ("workspace", "NETTRAINBRIDGE_WORKSPACE", "GRADMOTION_WORKSPACE", str, instance.workspace),
            ("conda_env", "NETTRAINBRIDGE_CONDA_ENV", "GRADMOTION_CONDA_ENV", str, "F1"),
            ("train_command", "NETTRAINBRIDGE_TRAIN_COMMAND", "GRADMOTION_TRAIN_COMMAND", str, instance.train_command),
            ("request_timeout", "NETTRAINBRIDGE_REQUEST_TIMEOUT", "GRADMOTION_REQUEST_TIMEOUT", int, 30),
            ("max_retries", "NETTRAINBRIDGE_MAX_RETRIES", "GRADMOTION_MAX_RETRIES", int, 3),
        ]

        for field_name, env_new, env_old, field_type, default in _fields:
            raw = get_setting(
                field_name,
                env_new=env_new,
                env_old=env_old,
                section="agent",
                default=default,
            )
            if raw is not None and raw != "":
                setattr(instance, field_name, field_type(raw))

        instance.workspace = os.path.expanduser(instance.workspace)
        return instance
