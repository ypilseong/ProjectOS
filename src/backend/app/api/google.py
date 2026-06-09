import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.config import config
from app.models.project import TaskStatus
from app.services.google_connector import GoogleConnector
from app.services.project_store import project_store
from app.services.task_manager import task_manager
from app.services.watcher import reparse_and_replace_chunks
from app.utils.logger import reset_log_project, set_log_project

router = APIRouter()


@router.get("/status")
async def google_status():
    return GoogleConnector().status()


@router.get("/auth-url")
async def google_auth_url(state: str = Query("projectos")):
    return {"auth_url": GoogleConnector().auth_url(state=state)}


@router.get("/oauth/callback")
async def google_oauth_callback(code: str, state: str = "projectos"):
    token = GoogleConnector().exchange_code(code)
    return {
        "ok": True,
        "state": state,
        "expires_in": token.get("expires_in"),
        "scopes": token.get("scope", ""),
    }


@router.post("/sync/{project_id}")
async def sync_google_project(project_id: str, body: dict | None = None):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    task = task_manager.create(project_id, "google_sync")
    body = body or {}
    task_options = {
        "include_gmail": bool(body.get("include_gmail", True)),
        "include_drive": bool(body.get("include_drive", True)),
        "gmail_query": body.get("gmail_query"),
        "drive_query": body.get("drive_query"),
        "max_results": body.get("max_results"),
        "trigger": "manual",
    }

    import asyncio

    asyncio.create_task(_run_google_sync_task(task.task_id, project_id, task_options))
    return {"task_id": task.task_id}


async def _run_google_sync_task(task_id: str, project_id: str, options: dict):
    log_token = set_log_project(project_id)
    try:
        task_manager.update(
            task_id,
            status=TaskStatus.RUNNING,
            message="Google 동기화 시작",
            progress=10,
        )
        result = await run_google_sync_pipeline(project_id, **options)
        task_manager.update(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=f"Google 동기화 완료: {result['synced_count']}개 파일",
        )
    except Exception as exc:
        task_manager.update(task_id, status=TaskStatus.FAILED, error=str(exc))
    finally:
        reset_log_project(log_token)


async def run_google_sync_pipeline(
    project_id: str,
    include_gmail: bool = True,
    include_drive: bool = True,
    gmail_query: str | None = None,
    drive_query: str | None = None,
    max_results: int | None = None,
    trigger: str = "manual",
) -> dict:
    result = GoogleConnector().sync_project(
        project_id,
        include_gmail=include_gmail,
        include_drive=include_drive,
        gmail_query=gmail_query,
        drive_query=drive_query,
        max_results=max_results,
    )
    changed_files = {item["filename"] for item in result.get("files", [])}
    if changed_files:
        reparse_and_replace_chunks(project_id, changed_files)
        await _maybe_run_incremental_graph(project_id, trigger=trigger)
    return result


async def _maybe_run_incremental_graph(project_id: str, trigger: str) -> None:
    project_dir = Path(config.PROJECTS_DIR) / project_id
    if not (
        (project_dir / "chunks.json").exists()
        and (project_dir / "ontology.json").exists()
        and (project_dir / "graph.json").exists()
    ):
        return

    from app.api.graph import _run_graph

    task = task_manager.create(project_id, "graph_google_sync")
    await _run_graph(task.task_id, project_id, incremental=True, trigger=f"google_{trigger}")


def load_google_sync_result(project_id: str) -> dict:
    path = Path(config.GOOGLE_STATE_PATH)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get(project_id, {}) if isinstance(data, dict) else {}
