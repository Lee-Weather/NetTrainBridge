from fastapi import APIRouter, BackgroundTasks, Request

import database
from api.jobs import create_job
from models import JobCreate

router = APIRouter(tags=["webhook"])


@router.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """接收 GitHub push 事件，自动创建训练任务。"""
    payload = await request.json()

    event = request.headers.get("X-GitHub-Event", "")
    if event != "push":
        return {"status": "ignored", "reason": f"event {event} not handled"}

    repo_url = payload.get("repository", {}).get("clone_url")
    ref = payload.get("ref", "")
    commit_sha = payload.get("after", "")

    if not repo_url or not commit_sha:
        return {"status": "ignored", "reason": "missing repo_url or commit_sha"}

    # branch: refs/heads/main -> main
    branch = ref.replace("refs/heads/", "") if ref else "main"

    # 在后台创建任务（避免阻塞 webhook 响应）
    background_tasks.add_task(
        _create_job_task,
        JobCreate(repo_url=repo_url, commit_sha=commit_sha),
    )

    return {
        "status": "accepted",
        "repo_url": repo_url,
        "commit_sha": commit_sha,
        "branch": branch,
    }


def _create_job_task(req: JobCreate):
    """后台任务：创建任务（同步调用）。"""
    import asyncio
    asyncio.run(create_job(req))
