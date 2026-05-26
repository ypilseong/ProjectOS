import asyncio
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import config
from app.models.project import ProjectStatus, TaskStatus
from app.services.project_store import project_store
from app.services.task_manager import task_manager

router = APIRouter()


@router.post("", status_code=201)
async def create_project(body: dict):
    project = project_store.create(
        name=body.get("name", "Untitled"),
        description=body.get("description", ""),
    )
    return project.model_dump()


@router.get("")
async def list_projects():
    return [p.model_dump() for p in project_store.list_all()]


@router.get("/{project_id}")
async def get_project(project_id: str):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.model_dump()


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    shutil.rmtree(Path(config.PROJECTS_DIR) / project_id, ignore_errors=True)
    return {"ok": True}


@router.post("/{project_id}/files")
async def upload_files(
    project_id: str,
    files: list[UploadFile] = File(...),
    file_type: str = Form("note"),
):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    files_dir = Path(config.PROJECTS_DIR) / project_id / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for f in files:
        dest = files_dir / f.filename
        async with aiofiles.open(dest, "wb") as out:
            await out.write(await f.read())
        saved_paths.append(str(dest))
        if f.filename not in project.files:
            project.files.append(f.filename)

    project_store.save(project)
    task = task_manager.create(project_id, "parse")
    asyncio.create_task(_run_parse(task.task_id, project_id, saved_paths, file_type))
    return {"task_id": task.task_id, "files": [f.filename for f in files]}


@router.post("/{project_id}/files/add")
async def add_files(
    project_id: str,
    files: list[UploadFile] = File(...),
    file_type: str = Form("note"),
):
    return await upload_files(project_id, files=files, file_type=file_type)


@router.get("/{project_id}/vault")
async def get_vault_tree(project_id: str):
    vault = Path(config.VAULT_DIR)
    if not vault.exists():
        return []
    return _build_tree(vault)


@router.get("/{project_id}/vault/file")
async def get_vault_file(project_id: str, path: str):
    from fastapi.responses import PlainTextResponse
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return PlainTextResponse(file_path.read_text(encoding="utf-8"))


@router.get("/{project_id}/vault/download")
async def download_vault(project_id: str):
    vault = Path(config.VAULT_DIR)
    tmp = tempfile.mktemp(suffix=".zip")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        if vault.exists():
            for f in vault.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(vault))
    return FileResponse(tmp, filename="vault.zip", media_type="application/zip")


def _build_tree(path: Path) -> list:
    result = []
    try:
        for child in sorted(path.iterdir()):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                result.append({
                    "name": child.name,
                    "type": "folder",
                    "children": _build_tree(child),
                })
            else:
                result.append({
                    "name": child.name,
                    "type": "file",
                    "path": str(child),
                })
    except PermissionError:
        pass
    return result


async def _run_parse(task_id: str, project_id: str, paths: list[str], file_type: str):
    from app.agents.parser_agent import ParserAgent
    try:
        task_manager.update(task_id, status=TaskStatus.RUNNING, message="파싱 시작")
        agent = ParserAgent()
        chunks = agent.run(paths, file_type=file_type)

        out = Path(config.PROJECTS_DIR) / project_id / "chunks.json"
        existing = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []

        import dataclasses
        new_chunks = [dataclasses.asdict(c) for c in chunks]
        combined = existing + new_chunks
        out.write_text(
            json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        task_manager.update(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=f"{len(chunks)}개 청크 생성 완료",
        )
    except Exception as e:
        task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))
