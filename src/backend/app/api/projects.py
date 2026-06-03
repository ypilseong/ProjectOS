import asyncio
import base64
import dataclasses
import json
import shutil
import tempfile
import zipfile
from difflib import SequenceMatcher
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app.config import config
from app.models.project import ProjectStatus, TaskStatus
from app.services.project_store import project_store
from app.services.task_manager import task_manager

router = APIRouter()


def _project_vault(project_id: str) -> Path:
    return Path(config.VAULT_DIR) / project_id


def _safe_upload_filename(filename: str) -> str:
    safe = Path(filename).name.strip()
    if not safe or safe in {".", ".."}:
        raise HTTPException(status_code=400, detail="filename is required")
    return safe


async def save_file_and_start_parse(
    project_id: str,
    filename: str,
    content: bytes,
    file_type: str = "note",
) -> dict:
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    safe_filename = _safe_upload_filename(filename)
    if not content:
        raise HTTPException(status_code=400, detail="file content is required")

    files_dir = Path(config.PROJECTS_DIR) / project_id / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    dest = files_dir / safe_filename
    async with aiofiles.open(dest, "wb") as out:
        await out.write(content)

    if safe_filename not in project.files:
        project.files.append(safe_filename)
    project.status = ProjectStatus.PARSING
    project_store.save(project)

    task = task_manager.create(project_id, "parse")
    asyncio.create_task(_run_parse(task.task_id, project_id, [str(dest)], file_type))
    return {"task_id": task.task_id, "files": [safe_filename]}


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
    shutil.rmtree(_project_vault(project_id), ignore_errors=True)
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

    project.status = ProjectStatus.PARSING
    project_store.save(project)
    task = task_manager.create(project_id, "parse")
    asyncio.create_task(_run_parse(task.task_id, project_id, saved_paths, file_type))
    return {"task_id": task.task_id, "files": [f.filename for f in files]}


@router.post("/{project_id}/files/raw")
async def upload_raw_file(
    project_id: str,
    request: Request,
    filename: str = Query(...),
    file_type: str = Query("note"),
):
    content = await request.body()
    return await save_file_and_start_parse(project_id, filename, content, file_type)


@router.post("/{project_id}/files/base64")
async def upload_base64_file(project_id: str, body: dict):
    filename = str(body.get("filename") or "")
    file_type = str(body.get("file_type") or "note")
    content_base64 = str(body.get("content_base64") or "")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="content_base64 is invalid")
    return await save_file_and_start_parse(project_id, filename, content, file_type)


@router.post("/{project_id}/files/add")
async def add_files(
    project_id: str,
    files: list[UploadFile] = File(...),
    file_type: str = Form("note"),
):
    return await upload_files(project_id, files=files, file_type=file_type)


@router.get("/{project_id}/vault")
async def get_vault_tree(project_id: str):
    vault = _project_vault(project_id)
    if not vault.exists():
        return []
    return _build_tree(vault)


@router.get("/{project_id}/vault/file")
async def get_vault_file(project_id: str, path: str):
    from fastapi.responses import PlainTextResponse
    vault = _project_vault(project_id).resolve()
    file_path = Path(path).resolve()
    if vault not in file_path.parents and file_path != vault:
        raise HTTPException(status_code=403, detail="File is outside project vault")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return PlainTextResponse(file_path.read_text(encoding="utf-8"))


@router.get("/{project_id}/vault/download")
async def download_vault(project_id: str):
    vault = _project_vault(project_id)
    tmp = tempfile.mktemp(suffix=".zip")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        if vault.exists():
            for f in vault.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(vault))
    return FileResponse(tmp, filename="vault.zip", media_type="application/zip")


@router.get("/{project_id}/vault/export")
async def export_vault(project_id: str):
    import networkx as nx

    from app.agents.obsidian_writer_agent import ObsidianWriterAgent
    from app.models.graph import CareerProfile

    project = project_store.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    proj_dir = Path(config.PROJECTS_DIR) / project_id
    graph_path = proj_dir / "graph.json"
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail="Graph not built yet")

    graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
    if "links" in graph_data and "edges" not in graph_data:
        graph_data["edges"] = graph_data.pop("links")
    graph = nx.node_link_graph(graph_data)

    profiles = []
    profiles_path = proj_dir / "profiles.json"
    if profiles_path.exists():
        profiles = [
            CareerProfile(**profile)
            for profile in json.loads(profiles_path.read_text(encoding="utf-8"))
        ]

    payload = ObsidianWriterAgent().build_payload(
        graph,
        profiles,
        project_id=project_id,
    )
    return payload.model_dump()


@router.post("/{project_id}/analysis")
async def run_analysis(project_id: str):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    chunks_path = Path(config.PROJECTS_DIR) / project_id / "chunks.json"
    if not chunks_path.exists():
        raise HTTPException(
            status_code=400,
            detail="No files uploaded yet — upload files first",
        )

    task = task_manager.create(project_id, "analysis")
    asyncio.create_task(_run_analysis(task.task_id, project_id))
    return {"task_id": task.task_id}


@router.get("/{project_id}/analysis")
async def get_analysis(project_id: str):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    p = Path(config.PROJECTS_DIR) / project_id / "analysis.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Analysis not run yet")
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/{project_id}/profiles")
async def get_profiles(project_id: str):
    p = Path(config.PROJECTS_DIR) / project_id / "profiles.json"
    if not p.exists():
        raise HTTPException(404, "Profiles not built yet")
    return json.loads(p.read_text(encoding="utf-8"))


@router.post("/{project_id}/profiles")
async def run_profiles(project_id: str):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    graph_path = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    if not graph_path.exists():
        raise HTTPException(400, "Graph not built yet — run graph build first")
    task = task_manager.create(project_id, "profiles")
    asyncio.create_task(_run_profiles(task.task_id, project_id))
    return {"task_id": task.task_id}


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
    from app.utils.logger import reset_log_project, set_log_project
    log_token = set_log_project(project_id)
    try:
        total_files = len(paths)
        task_manager.update(
            task_id,
            status=TaskStatus.RUNNING,
            message=f"파싱 시작 (0/{total_files})",
            progress=5,
        )
        agent = ParserAgent()

        def on_file_progress(current: int, total: int, filename: str):
            ratio = current / total if total else 1
            task_manager.update(
                task_id,
                message=f"파일 파싱 중... ({current}/{total}) {filename}",
                progress=5 + int(ratio * 85),
            )

        chunks = agent.run(
            paths,
            file_type=file_type,
            progress_callback=on_file_progress,
        )

        out = Path(config.PROJECTS_DIR) / project_id / "chunks.json"
        existing = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []

        import dataclasses
        new_chunks = [dataclasses.asdict(c) for c in chunks]
        combined = existing + new_chunks
        out.write_text(
            json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        project = project_store.get(project_id)
        if project:
            project.status = ProjectStatus.CREATED
            project_store.save(project)

        task_manager.update(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=f"{len(chunks)}개 청크 생성 완료",
        )
    except Exception as e:
        project = project_store.get(project_id)
        if project:
            project.status = ProjectStatus.FAILED
            project_store.save(project)
        task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))
    finally:
        reset_log_project(log_token)


async def _run_analysis(task_id: str, project_id: str):
    import networkx as nx
    from app.agents.analysis_agent import AnalysisAgent
    from app.models.graph import TextChunk
    from app.utils.logger import reset_log_project, set_log_project

    log_token = set_log_project(project_id)
    try:
        task_manager.update(
            task_id,
            status=TaskStatus.RUNNING,
            message="청크 로딩 중...",
            progress=10,
        )
        proj_dir = Path(config.PROJECTS_DIR) / project_id
        chunks_data = json.loads((proj_dir / "chunks.json").read_text(encoding="utf-8"))
        chunks = [TextChunk(**c) for c in chunks_data]

        graph = None
        graph_path = proj_dir / "graph.json"
        if graph_path.exists():
            data = json.loads(graph_path.read_text(encoding="utf-8"))
            graph = nx.node_link_graph(data)

        task_manager.update(task_id, message="LLM 분석 중... (1/3)", progress=30)
        agent = AnalysisAgent()
        result = await agent.run(chunks, graph)

        task_manager.update(task_id, message="결과 저장 중... (2/3)", progress=90)
        (proj_dir / "analysis.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        task_manager.update(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=f"분석 완료 (3/3): {len(result.get('issues', []))}개 개선 포인트 발견",
        )
    except Exception as e:
        task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))
    finally:
        reset_log_project(log_token)


def _find_user_person(graph, user_name: str, display_name: str) -> str | None:
    threshold = 0.7
    best_id, best_score = None, 0.0
    for nid, data in graph.nodes(data=True):
        if data.get("type") != "Person":
            continue
        node_name = data.get("name", "").lower()
        s = max(
            SequenceMatcher(None, user_name.lower(), node_name).ratio(),
            SequenceMatcher(None, display_name.lower(), node_name).ratio(),
        )
        if s > best_score:
            best_score, best_id = s, nid
    return best_id if best_score >= threshold else None


def _most_connected_person(graph) -> str | None:
    persons = [nid for nid, d in graph.nodes(data=True) if d.get("type") == "Person"]
    return max(persons, key=lambda n: graph.degree(n)) if persons else None


async def _run_profiles(task_id: str, project_id: str):
    import networkx as nx
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent
    from app.agents.profile_agent import ProfileAgent
    from app.utils.logger import get_logger, reset_log_project, set_log_project

    logger = get_logger(__name__)
    log_token = set_log_project(project_id)
    try:
        task_manager.update(task_id, status=TaskStatus.RUNNING, message="그래프 로딩 중...", progress=10)
        proj_dir = Path(config.PROJECTS_DIR) / project_id

        data = json.loads((proj_dir / "graph.json").read_text(encoding="utf-8"))
        if "links" in data and "edges" not in data:
            data["edges"] = data.pop("links")
        graph = nx.node_link_graph(data)

        user_path = Path(config.USER_CONFIG_PATH)
        if not user_path.exists():
            raise ValueError("User config not set — set user name first")
        user_data = json.loads(user_path.read_text(encoding="utf-8"))
        user_name = user_data.get("name", "")
        display_name = user_data.get("display_name") or user_name

        person_id = _find_user_person(graph, user_name, display_name)
        if not person_id:
            person_id = _most_connected_person(graph)
            if person_id:
                logger.warning(f"No fuzzy match for '{user_name}' — using most connected: {person_id}")
            else:
                raise ValueError("No Person nodes found in graph")

        task_manager.update(task_id, message=f"프로필 생성 중... {person_id}", progress=30)
        profile_agent = ProfileAgent()

        def on_progress(current: int, total: int, name: str):
            task_manager.update(
                task_id,
                message=f"프로필 생성 중... ({current}/{total}) {name}",
                progress=30 + int((current / total if total else 1) * 50),
            )

        profiles = await profile_agent.run(graph, person_ids=[person_id], progress_callback=on_progress)
        profiles_data = [dataclasses.asdict(p) for p in profiles]
        (proj_dir / "profiles.json").write_text(
            json.dumps(profiles_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        task_manager.update(task_id, message="Obsidian vault 업데이트 중...", progress=85)
        writer = ObsidianWriterAgent()
        vault_path = str(Path(config.VAULT_DIR) / project_id)
        writer.run(graph, profiles, vault_path=vault_path, delta=True, project_id=project_id)

        task_manager.update(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=f"프로필 생성 완료: {len(profiles)}개",
        )
    except Exception as e:
        project = project_store.get(project_id)
        if project:
            project.status = ProjectStatus.FAILED
            project_store.save(project)
        task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))
    finally:
        reset_log_project(log_token)
