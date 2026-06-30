import os
from pathlib import Path


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
        if os.environ.get("GRADMOTION_HOST"):
            instance.HOST = os.environ["GRADMOTION_HOST"]
        if os.environ.get("GRADMOTION_PORT"):
            instance.PORT = int(os.environ["GRADMOTION_PORT"])
        if os.environ.get("GRADMOTION_DB_PATH"):
            instance.DB_PATH = os.environ["GRADMOTION_DB_PATH"]
        if os.environ.get("GRADMOTION_DATA_DIR"):
            instance.DATA_DIR = os.environ["GRADMOTION_DATA_DIR"]
        if os.environ.get("GRADMOTION_WEBHOOK_SECRET"):
            instance.WEBHOOK_SECRET = os.environ["GRADMOTION_WEBHOOK_SECRET"]
        if os.environ.get("GRADMOTION_ALLOWED_REPOS"):
            instance.ALLOWED_REPOS = [
                item.strip()
                for item in os.environ["GRADMOTION_ALLOWED_REPOS"].split(",")
                if item.strip()
            ]
        return instance
