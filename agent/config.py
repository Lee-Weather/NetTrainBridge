import os
from dataclasses import dataclass


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
    workspace: str = os.path.expanduser("~/czy/gradmotion")

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

        _env_map = {
            "GRADMOTION_SERVER_URL": ("server_url", str),
            "GRADMOTION_PROXY": ("proxy", str),
            "GRADMOTION_AGENT_ID": ("agent_id", str),
            "GRADMOTION_POLL_INTERVAL": ("poll_interval", int),
            "GRADMOTION_HEARTBEAT_INTERVAL": ("heartbeat_interval", int),
            "GRADMOTION_LOG_UPLOAD_INTERVAL": ("log_upload_interval", int),
            "GRADMOTION_METRICS_UPLOAD_INTERVAL": ("metrics_upload_interval", int),
            "GRADMOTION_WORKSPACE": ("workspace", str),
            "GRADMOTION_CONDA_ENV": ("conda_env", str),
            "GRADMOTION_TRAIN_COMMAND": ("train_command", str),
            "GRADMOTION_REQUEST_TIMEOUT": ("request_timeout", int),
            "GRADMOTION_MAX_RETRIES": ("max_retries", int),
        }

        for env_key, (field_name, field_type) in _env_map.items():
            value = os.environ.get(env_key)
            if value is not None:
                setattr(instance, field_name, field_type(value))

        instance.workspace = os.path.expanduser(instance.workspace)
        return instance

