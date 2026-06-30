import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config_loader import get_setting, config_status_message  # noqa: E402


class ServerConfig:
    """服务器配置：配置文件 → 环境变量 → 默认值。"""

    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DB_PATH: str = "data/server.db"
    DATA_DIR: str = "data"
    LOG_MAX_LINES: int = 5000
    CHECKPOINT_UPLOAD_CHUNK: int = 4 * 1024 * 1024  # 4MB 分片
    WEBHOOK_SECRET: str = ""
    ALLOWED_REPOS: list[str] = []

    @classmethod
    def load(cls) -> "ServerConfig":
        instance = cls()

        host = get_setting("host", env_new="NETTRAINBRIDGE_HOST", env_old="GRADMOTION_HOST", section="server")
        if host:
            instance.HOST = str(host)

        port = get_setting("port", env_new="NETTRAINBRIDGE_PORT", env_old="GRADMOTION_PORT", section="server")
        if port is not None and port != "":
            instance.PORT = int(port)

        db_path = get_setting("db_path", env_new="NETTRAINBRIDGE_DB_PATH", env_old="GRADMOTION_DB_PATH", section="server")
        if db_path:
            instance.DB_PATH = str(db_path)

        data_dir = get_setting("data_dir", env_new="NETTRAINBRIDGE_DATA_DIR", env_old="GRADMOTION_DATA_DIR", section="server")
        if data_dir:
            instance.DATA_DIR = str(data_dir)

        webhook_secret = get_setting(
            "webhook_secret",
            env_new="NETTRAINBRIDGE_WEBHOOK_SECRET",
            env_old="GRADMOTION_WEBHOOK_SECRET",
            section="server",
        )
        if webhook_secret:
            instance.WEBHOOK_SECRET = str(webhook_secret)

        allowed_repos = get_setting(
            "allowed_repos",
            env_new="NETTRAINBRIDGE_ALLOWED_REPOS",
            env_old="GRADMOTION_ALLOWED_REPOS",
            section="server",
        )
        if allowed_repos:
            if isinstance(allowed_repos, list):
                instance.ALLOWED_REPOS = [str(item).strip() for item in allowed_repos if str(item).strip()]
            else:
                instance.ALLOWED_REPOS = [
                    item.strip()
                    for item in str(allowed_repos).split(",")
                    if item.strip()
                ]

        return instance
