import base64
import asyncio
import json
from pathlib import Path
from typing import Any

import networkx as nx

from app.config import config
from app.models.graph import TextChunk
from app.services.digest import generate_digest
from app.services.project_store import project_store
from app.utils.trace import read_traces


def _tool(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


def list_mcp_tools() -> list[dict]:
    return [
        _tool(
            "projectos_create_project",
            "Create a new ProjectOS project and return its project_id.",
            {
                "name": {"type": "string"},
                "description": {"type": "string", "default": ""},
            },
            ["name"],
        ),
        _tool(
            "projectos_upload_file",
            "Upload a file into a ProjectOS project and start document parsing.",
            {
                "project_id": {"type": "string"},
                "filename": {"type": "string"},
                "content_base64": {
                    "type": "string",
                    "description": "Base64-encoded file bytes. Use this for binary files such as PDF or DOCX.",
                },
                "content_text": {
                    "type": "string",
                    "description": "Plain text file content. Used only when content_base64 is omitted.",
                },
                "file_type": {"type": "string", "default": "note"},
            },
            ["project_id", "filename"],
        ),
        _tool(
            "projectos_get_task",
            "Return the status/progress of a ProjectOS background task.",
            {"task_id": {"type": "string"}},
            ["task_id"],
        ),
        _tool(
            "projectos_build_ontology",
            "Start ontology extraction for a project after uploaded files have been parsed.",
            {"project_id": {"type": "string"}},
            ["project_id"],
        ),
        _tool(
            "projectos_build_graph",
            "Start initial graph build for a project after ontology extraction has completed.",
            {
                "project_id": {"type": "string"},
                "incremental": {"type": "boolean", "default": False},
            },
            ["project_id"],
        ),
        _tool(
            "projectos_list_projects",
            "List ProjectOS projects available as career-memory contexts.",
            {},
        ),
        _tool(
            "projectos_get_graph_health",
            "Return graph and Obsidian vault health diagnostics for a project.",
            {"project_id": {"type": "string"}},
            ["project_id"],
        ),
        _tool(
            "projectos_query_career_graph",
            "Answer a natural-language question using the project's graph, chunks, and vault notes.",
            {
                "project_id": {"type": "string"},
                "question": {"type": "string"},
            },
            ["project_id", "question"],
        ),
        _tool(
            "projectos_generate_digest",
            "Generate today's deterministic ProjectOS digest for a built project.",
            {"project_id": {"type": "string"}},
            ["project_id"],
        ),
        _tool(
            "projectos_list_digests",
            "List digest dates for a project, newest first.",
            {"project_id": {"type": "string"}},
            ["project_id"],
        ),
        _tool(
            "projectos_get_digest",
            "Read a specific ProjectOS digest markdown file.",
            {
                "project_id": {"type": "string"},
                "date": {"type": "string", "description": "Digest date in YYYY-MM-DD format."},
            },
            ["project_id", "date"],
        ),
        _tool(
            "projectos_get_vault_note",
            "Read a markdown note from a project's Obsidian vault by relative path.",
            {
                "project_id": {"type": "string"},
                "path": {"type": "string"},
            },
            ["project_id", "path"],
        ),
        _tool(
            "projectos_read_traces",
            "Read recent decision traces for graph builds, watcher runs, digests, and related operations.",
            {
                "project_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
            },
            ["project_id"],
        ),
    ]


def _text_result(text: str, structured: dict | None = None, is_error: bool = False) -> dict:
    result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    if structured is not None:
        result["structuredContent"] = structured
    return result


def _project_dir(project_id: str) -> Path:
    return Path(config.PROJECTS_DIR) / project_id


def _require_project(project_id: str) -> None:
    if not project_store.get(project_id):
        raise ValueError("Project not found")


def _load_graph(project_id: str) -> nx.DiGraph:
    graph_path = _project_dir(project_id) / "graph.json"
    if not graph_path.exists():
        raise ValueError("Graph not built yet")
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    return nx.node_link_graph(data)


def _load_chunks(project_id: str) -> list[TextChunk]:
    chunks_path = _project_dir(project_id) / "chunks.json"
    if not chunks_path.exists():
        return []
    return [
        TextChunk(**chunk)
        for chunk in json.loads(chunks_path.read_text(encoding="utf-8"))
    ]


async def call_mcp_tool(name: str, arguments: dict | None = None) -> dict:
    args = arguments or {}
    try:
        if name == "projectos_create_project":
            project_name = str(args["name"]).strip()
            if not project_name:
                raise ValueError("name is required")
            project = project_store.create(
                name=project_name,
                description=str(args.get("description") or ""),
            )
            payload = project.model_dump(mode="json")
            return _text_result(
                json.dumps(payload, ensure_ascii=False),
                {"project": payload, "project_id": project.project_id},
            )

        if name == "projectos_upload_file":
            from app.api.projects import save_file_and_start_parse

            project_id = str(args["project_id"])
            filename = str(args["filename"])
            file_type = str(args.get("file_type") or "note")
            if args.get("content_base64"):
                try:
                    content = base64.b64decode(str(args["content_base64"]), validate=True)
                except Exception:
                    raise ValueError("content_base64 is invalid")
            elif args.get("content_text") is not None:
                content = str(args["content_text"]).encode("utf-8")
            else:
                raise ValueError("content_base64 or content_text is required")
            result = await save_file_and_start_parse(
                project_id,
                filename,
                content,
                file_type,
            )
            return _text_result(
                json.dumps(result, ensure_ascii=False),
                result,
            )

        if name == "projectos_get_task":
            from app.services.task_manager import task_manager

            task_id = str(args["task_id"])
            task = task_manager.get(task_id)
            if not task:
                raise ValueError("Task not found")
            payload = task.model_dump(mode="json")
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)

        if name == "projectos_build_ontology":
            from app.api.graph import _run_ontology
            from app.models.project import ProjectStatus
            from app.services.task_manager import task_manager

            project_id = str(args["project_id"])
            project = project_store.get(project_id)
            if not project:
                raise ValueError("Project not found")
            chunks_path = _project_dir(project_id) / "chunks.json"
            if not chunks_path.exists():
                raise ValueError("chunks.json not found — upload files and wait for parse first")
            project.status = ProjectStatus.ONTOLOGY
            project_store.save(project)
            task = task_manager.create(project_id, "ontology")
            asyncio.create_task(_run_ontology(task.task_id, project_id))
            payload = task.model_dump(mode="json")
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)

        if name == "projectos_build_graph":
            from app.api.graph import _run_graph
            from app.models.project import ProjectStatus
            from app.services.task_manager import task_manager

            project_id = str(args["project_id"])
            incremental = bool(args.get("incremental", False))
            project = project_store.get(project_id)
            if not project:
                raise ValueError("Project not found")
            ontology_path = _project_dir(project_id) / "ontology.json"
            if not ontology_path.exists():
                raise ValueError("ontology.json not found — run projectos_build_ontology first")
            project.status = ProjectStatus.BUILDING
            project_store.save(project)
            task_type = "graph_incremental" if incremental else "graph"
            task = task_manager.create(project_id, task_type)
            asyncio.create_task(_run_graph(task.task_id, project_id, incremental=incremental))
            payload = task.model_dump(mode="json")
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)

        if name == "projectos_list_projects":
            projects = [
                project.model_dump(mode="json")
                for project in project_store.list_all()
            ]
            return _text_result(
                json.dumps(projects, ensure_ascii=False),
                {"projects": projects},
            )

        if name == "projectos_get_graph_health":
            from app.utils.graph_health import run_health_check

            project_id = str(args["project_id"])
            _require_project(project_id)
            graph = _load_graph(project_id)
            health = run_health_check(
                graph,
                vault_path=str(Path(config.VAULT_DIR) / project_id),
            )
            return _text_result(
                json.dumps(health, ensure_ascii=False),
                {"health": health},
            )

        if name == "projectos_query_career_graph":
            from app.agents.query_agent import QueryAgent

            project_id = str(args["project_id"])
            question = str(args["question"]).strip()
            if not question:
                raise ValueError("question is required")
            _require_project(project_id)
            graph = _load_graph(project_id)
            chunks = _load_chunks(project_id)
            vault_path = str(Path(config.VAULT_DIR) / project_id)
            answer = ""
            async for token in QueryAgent().stream(question, graph, chunks, vault_path=vault_path):
                answer += token
            return _text_result(answer, {"answer": answer})

        if name == "projectos_generate_digest":
            project_id = str(args["project_id"])
            _require_project(project_id)
            result = generate_digest(project_id, trigger="mcp")
            if result is None:
                raise ValueError("Graph not built yet")
            return _text_result(result["markdown"], result)

        if name == "projectos_list_digests":
            project_id = str(args["project_id"])
            _require_project(project_id)
            digests_dir = Path(config.VAULT_DIR) / project_id / "Digests"
            dates = []
            if digests_dir.exists():
                dates = sorted(
                    (path.stem for path in digests_dir.glob("*.md") if path.is_file()),
                    reverse=True,
                )
            return _text_result("\n".join(dates), {"dates": dates})

        if name == "projectos_get_digest":
            project_id = str(args["project_id"])
            digest_date = str(args["date"])
            _require_project(project_id)
            path = Path(config.VAULT_DIR) / project_id / "Digests" / f"{digest_date}.md"
            if not path.exists():
                raise ValueError("Digest not found")
            markdown = path.read_text(encoding="utf-8")
            return _text_result(markdown, {"date": digest_date, "markdown": markdown})

        if name == "projectos_get_vault_note":
            project_id = str(args["project_id"])
            rel_path = str(args["path"])
            _require_project(project_id)
            vault = (Path(config.VAULT_DIR) / project_id).resolve()
            note_path = (vault / rel_path).resolve()
            if vault not in note_path.parents and note_path != vault:
                raise ValueError("File is outside project vault")
            if not note_path.exists() or not note_path.is_file():
                raise ValueError("Vault note not found")
            markdown = note_path.read_text(encoding="utf-8")
            return _text_result(
                markdown,
                {"path": str(note_path.relative_to(vault)), "markdown": markdown},
            )

        if name == "projectos_read_traces":
            project_id = str(args["project_id"])
            _require_project(project_id)
            limit = int(args.get("limit", 100))
            limit = max(1, min(limit, 500))
            traces = read_traces(project_id)[-limit:]
            return _text_result(
                json.dumps(traces, ensure_ascii=False),
                {"traces": traces},
            )

        return _text_result(f"Unknown tool: {name}", is_error=True)
    except Exception as exc:
        return _text_result(str(exc), is_error=True)
