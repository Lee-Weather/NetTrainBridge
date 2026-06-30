import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import database
from api import jobs, webhook, logs, metrics, checkpoint, heartbeat
from config import ServerConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("nettrainbridge")

_config = ServerConfig.load()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库
    logger.info("Initializing database at %s", _config.DB_PATH)
    database.init_db()
    logger.info("NetTrainBridge Server started on %s:%s", _config.HOST, _config.PORT)
    yield
    logger.info("NetTrainBridge Server shutting down")


app = FastAPI(title="NetTrainBridge Server", lifespan=lifespan)

# 注册路由
app.include_router(jobs.router)
app.include_router(webhook.router)
app.include_router(logs.router)
app.include_router(metrics.router)
app.include_router(checkpoint.router)
app.include_router(heartbeat.router)


@app.get("/")
async def root():
    """API 入口说明（无 Web GUI）。"""
    return {
        "name": "NetTrainBridge Server",
        "docs": "/docs",
        "health": "/health",
        "cli": "ntb jobs / ntb watch <job_id>",
    }


@app.get("/health")
async def health():
    """健康检查接口。"""
    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s %s -> %s", request.method, request.url, exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=_config.HOST,
        port=_config.PORT,
    )
