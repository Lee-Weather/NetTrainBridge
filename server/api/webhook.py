import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from api.jobs import create_job_sync, find_job_by_repo_commit, normalize_repo_url
from config import ServerConfig
from models import JobCreate

router = APIRouter(tags=["webhook"])
_config = ServerConfig.load()
logger = logging.getLogger("nettrainbridge")


def _verify_github_signature(body: bytes, signature_header: str | None) -> bool:
    """校验 GitHub Webhook 签名（未配置 secret 时跳过）。"""
    secret = _config.WEBHOOK_SECRET
    if not secret:
        return True
    if not signature_header:
        return False

    if signature_header.startswith("sha256="):
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={digest}", signature_header)

    if signature_header.startswith("sha1="):
        digest = hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
        return hmac.compare_digest(f"sha1={digest}", signature_header)

    return False


def _is_repo_allowed(repo_url: str) -> bool:
    """检查仓库是否在白名单内（白名单为空则允许全部）。"""
    if not _config.ALLOWED_REPOS:
        return True
    normalized = normalize_repo_url(repo_url)
    allowed = {normalize_repo_url(item) for item in _config.ALLOWED_REPOS}
    return normalized in allowed


@router.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """接收 GitHub push 事件，自动创建训练任务。"""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256") or request.headers.get(
        "X-Hub-Signature"
    )
    if not _verify_github_signature(body, signature):
        logger.warning("Webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = request.headers.get("X-GitHub-Event", "")
    if event != "push":
        return {"status": "ignored", "reason": f"event {event} not handled"}

    repo_url = payload.get("repository", {}).get("clone_url")
    ref = payload.get("ref", "")
    commit_sha = payload.get("after", "")

    if not repo_url or not commit_sha:
        return {"status": "ignored", "reason": "missing repo_url or commit_sha"}

    if commit_sha == "0000000000000000000000000000000000000000":
        return {"status": "ignored", "reason": "branch deletion push ignored"}

    if not _is_repo_allowed(repo_url):
        logger.info("Webhook ignored repo not in whitelist: %s", repo_url)
        return {
            "status": "ignored",
            "reason": "repository not in allowed list",
            "repo_url": repo_url,
        }

    branch = ref.replace("refs/heads/", "") if ref else "main"

    existing = find_job_by_repo_commit(repo_url, commit_sha)
    if existing:
        logger.info(
            "Webhook duplicate job for %s@%s -> %s",
            repo_url,
            commit_sha,
            existing.id,
        )
        return {
            "status": "duplicate",
            "job_id": existing.id,
            "repo_url": repo_url,
            "commit_sha": commit_sha,
            "branch": branch,
        }

    req = JobCreate(repo_url=repo_url, commit_sha=commit_sha)
    background_tasks.add_task(_create_job_task, req)

    return {
        "status": "accepted",
        "repo_url": repo_url,
        "commit_sha": commit_sha,
        "branch": branch,
    }


def _create_job_task(req: JobCreate):
    """后台任务：同步创建任务。"""
    try:
        job = create_job_sync(req)
        logger.info("Webhook created job %s for %s@%s", job.id, req.repo_url, req.commit_sha)
    except Exception:
        logger.exception("Webhook failed to create job for %s@%s", req.repo_url, req.commit_sha)
