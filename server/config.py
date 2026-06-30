import os

from env_util import get_env


class ServerConfig:
    """服务器配置，支持环境变量覆盖。"""

    # 默认值（开发环境用项目内路径，生产环境通过环境变量覆盖）
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DB_PATH: str = "data/server.db"
    DATA_DIR: str = "data"
    LOG_MAX_LINES: int = 5000
    CHECKPOINT_UPLOAD_CHUNK: int = 4 * 1024 * 1024  # 4MB 分片
    WEBHOOK_SECRET: str = ""
    ALLOWED_REPOS: list[str] = []  # 空列表表示不限制仓库

    @classmethod
    def load(cls) -> "ServerConfig":
        """从环境变量加载配置，未设置则使用默认值。"""
        instance = cls()

        host = get_env("NETTRAINBRIDGE_HOST", "GRADMOTION_HOST")
        if host:
            instance.HOST = host

        port = get_env("NETTRAINBRIDGE_PORT", "GRADMOTION_PORT")
        if port:
            instance.PORT = int(port)

        db_path = get_env("NETTRAINBRIDGE_DB_PATH", "GRADMOTION_DB_PATH")
        if db_path:
            instance.DB_PATH = db_path

        data_dir = get_env("NETTRAINBRIDGE_DATA_DIR", "GRADMOTION_DATA_DIR")
        if data_dir:
            instance.DATA_DIR = data_dir

        webhook_secret = get_env("NETTRAINBRIDGE_WEBHOOK_SECRET", "GRADMOTION_WEBHOOK_SECRET")
        if webhook_secret:
            instance.WEBHOOK_SECRET = webhook_secret

        allowed_repos = get_env("NETTRAINBRIDGE_ALLOWED_REPOS", "GRADMOTION_ALLOWED_REPOS")
        if allowed_repos:
            instance.ALLOWED_REPOS = [
                item.strip()
                for item in allowed_repos.split(",")
                if item.strip()
            ]

        return instance
