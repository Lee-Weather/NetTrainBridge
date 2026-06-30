import os
from dataclasses import dataclass

from env_util import get_env


@dataclass
class AgentConfig:
    """Agent 配置，支持环境变量覆盖。"""

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
        """从环境变量加载配置，未设置则使用默认值。"""
        instance = cls()

        _env_map = [
            ("NETTRAINBRIDGE_SERVER_URL", "GRADMOTION_SERVER_URL", "server_url", str),
            ("NETTRAINBRIDGE_PROXY", "GRADMOTION_PROXY", "proxy", str),
            ("NETTRAINBRIDGE_AGENT_ID", "GRADMOTION_AGENT_ID", "agent_id", str),
            ("NETTRAINBRIDGE_POLL_INTERVAL", "GRADMOTION_POLL_INTERVAL", "poll_interval", int),
            ("NETTRAINBRIDGE_HEARTBEAT_INTERVAL", "GRADMOTION_HEARTBEAT_INTERVAL", "heartbeat_interval", int),
            ("NETTRAINBRIDGE_LOG_UPLOAD_INTERVAL", "GRADMOTION_LOG_UPLOAD_INTERVAL", "log_upload_interval", int),
            ("NETTRAINBRIDGE_METRICS_UPLOAD_INTERVAL", "GRADMOTION_METRICS_UPLOAD_INTERVAL", "metrics_upload_interval", int),
            ("NETTRAINBRIDGE_WORKSPACE", "GRADMOTION_WORKSPACE", "workspace", str),
            ("NETTRAINBRIDGE_CONDA_ENV", "GRADMOTION_CONDA_ENV", "conda_env", str),
            ("NETTRAINBRIDGE_TRAIN_COMMAND", "GRADMOTION_TRAIN_COMMAND", "train_command", str),
            ("NETTRAINBRIDGE_REQUEST_TIMEOUT", "GRADMOTION_REQUEST_TIMEOUT", "request_timeout", int),
            ("NETTRAINBRIDGE_MAX_RETRIES", "GRADMOTION_MAX_RETRIES", "max_retries", int),
        ]

        for new_key, old_key, field_name, field_type in _env_map:
            value = get_env(new_key, old_key)
            if value is not None:
                setattr(instance, field_name, field_type(value))

        instance.workspace = os.path.expanduser(instance.workspace)
        return instance
