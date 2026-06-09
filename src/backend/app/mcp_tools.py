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
                "file_type": {
                    "type": "string",
                    "default": "note",
                    "enum": ["cv", "paper", "report", "memo", "email", "note"],
                    "description": "Document type for prompt selection. Set this per uploaded file.",
                },
            },
            ["project_id", "filename"],
        ),
        _tool(
            "projectos_get_upload_api",
            (
                "Return the direct multipart upload API for remote deployments. "
                "Use this instead of projectos_upload_file when file bytes should not pass through Claude Desktop."
            ),
            {
                "project_id": {"type": "string"},
                "base_url": {
                    "type": "string",
                    "description": "Optional public backend URL. Defaults to BACKEND_PUBLIC_URL.",
                },
            },
            ["project_id"],
        ),
        _tool(
            "projectos_list_inbox",
            (
                "List the synced ProjectOS inbox folder. Files are classified by the local LLM "
                "from a short server-side preview, not by filename alone."
            ),
            {
                "relative_path": {"type": "string", "default": ""},
                "recursive": {"type": "boolean", "default": False},
                "max_items": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
                "classify_files": {"type": "boolean", "default": True},
            },
        ),
        _tool(
            "projectos_preview_inbox_file",
            "Return a short server-side text preview and local-LLM document type classification for an inbox file.",
            {
                "relative_path": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 200, "maximum": 5000, "default": 1500},
            },
            ["relative_path"],
        ),
        _tool(
            "projectos_ingest_inbox_file",
            "Ingest one synced inbox file into a ProjectOS project. Use file_type=auto to let the local LLM classify it.",
            {
                "project_id": {"type": "string"},
                "relative_path": {"type": "string"},
                "file_type": {
                    "type": "string",
                    "default": "auto",
                    "enum": ["auto", "cv", "paper", "report", "memo", "email", "note"],
                },
            },
            ["project_id", "relative_path"],
        ),
        _tool(
            "projectos_ingest_inbox_files",
            "Ingest multiple synced inbox files. Missing or auto file types are classified by the local LLM.",
            {
                "project_id": {"type": "string"},
                "relative_paths": {"type": "array", "items": {"type": "string"}},
                "file_types": {
                    "type": "object",
                    "default": {},
                    "description": "Optional map of relative_path to file_type. Use auto or omit a file to classify locally.",
                },
            },
            ["project_id", "relative_paths"],
        ),
        _tool(
            "projectos_ingest_clip",
            (
                "Ingest an Obsidian Web Clipper markdown file from the inbox into a project, "
                "capturing the user's intent first. Call without capture_context to receive the "
                "required questions (status=needs_context); ask the user, then call again with "
                "capture_context to start ingestion. The intent guides graph extraction and is "
                "recorded as a Capture node."
            ),
            {
                "project_id": {"type": "string"},
                "relative_path": {"type": "string"},
                "file_type": {
                    "type": "string",
                    "default": "auto",
                    "enum": ["auto", "cv", "paper", "report", "memo", "email", "note"],
                },
                "capture_context": {
                    "type": "object",
                    "description": "{capture_reason, current_focus, reflection_intent}. Omit to get the question contract.",
                    "properties": {
                        "capture_reason": {"type": "string"},
                        "current_focus": {"type": "string"},
                        "reflection_intent": {"type": "string"},
                    },
                },
            },
            ["project_id", "relative_path"],
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
            "projectos_get_hot_context",
            "Return a compact session-entry primer for a project: key people, hub entities, recent build activity, gaps, and summary stats.",
            {"project_id": {"type": "string"}},
            ["project_id"],
        ),
        _tool(
            "projectos_get_research_candidates",
            (
                "Return deterministic research/backfill/review candidates for graph weak spots. "
                "This is read-only and does not run web search or mutate the graph."
            ),
            {
                "project_id": {"type": "string"},
                "max_candidates": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "min_degree": {"type": "integer", "minimum": 0, "maximum": 10, "default": 1},
                "component_size_threshold": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 20,
                    "default": 3,
                },
            },
            ["project_id"],
        ),
        _tool(
            "projectos_review_graph",
            (
                "Return a read-only graph review workflow comparing full Claude review "
                "against deterministic targeted review candidates."
            ),
            {
                "project_id": {"type": "string"},
                "max_candidates": {"type": "integer", "minimum": 1, "maximum": 100, "default": 8},
                "min_degree": {"type": "integer", "minimum": 0, "maximum": 10, "default": 1},
                "component_size_threshold": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 20,
                    "default": 3,
                },
            },
            ["project_id"],
        ),
        _tool(
            "projectos_get_graph_summary",
            (
                "Return a compact read-only graph summary for Claude Desktop "
                "without sending the full graph JSON."
            ),
            {
                "project_id": {"type": "string"},
                "max_hubs": {"type": "integer", "minimum": 0, "maximum": 50, "default": 10},
            },
            ["project_id"],
        ),
        _tool(
            "projectos_get_node_context",
            "Return compact read-only one-hop graph context for a node name or id. "
            "Set include_evidence=true to also attach up to max_evidence source-chunk "
            "excerpts with citation labels.",
            {
                "project_id": {"type": "string"},
                "node_name": {"type": "string"},
                "node_type": {"type": "string", "default": ""},
                "max_neighbors": {"type": "integer", "minimum": 0, "maximum": 100, "default": 20},
                "include_evidence": {"type": "boolean", "default": False},
                "max_evidence": {"type": "integer", "minimum": 0, "maximum": 10, "default": 3},
            },
            ["project_id", "node_name"],
        ),
        _tool(
            "projectos_get_subgraph",
            "Return a compact read-only bounded subgraph around a node name or id.",
            {
                "project_id": {"type": "string"},
                "node_name": {"type": "string"},
                "node_type": {"type": "string", "default": ""},
                "depth": {"type": "integer", "minimum": 0, "maximum": 3, "default": 1},
                "max_nodes": {"type": "integer", "minimum": 0, "maximum": 100, "default": 25},
            },
            ["project_id", "node_name"],
        ),
        _tool(
            "projectos_get_ontology",
            "Return the extracted ontology for a project.",
            {"project_id": {"type": "string"}},
            ["project_id"],
        ),
        _tool(
            "projectos_get_graph",
            "Return the built graph JSON for a project.",
            {"project_id": {"type": "string"}},
            ["project_id"],
        ),
        _tool(
            "projectos_apply_graph_patch",
            "Apply reviewer-approved graph changes, persist graph.json, and rebuild the Obsidian vault.",
            {
                "project_id": {"type": "string"},
                "patch": {
                    "type": "object",
                    "description": (
                        "Patch object with nodes_add, nodes_update, nodes_delete, "
                        "edges_add, and edges_delete arrays."
                    ),
                },
            },
            ["project_id", "patch"],
        ),
        _tool(
            "projectos_reconcile_vault",
            "Reconcile manual Obsidian vault edits back into the graph. "
            "Dry-run by default; pass apply=true to persist and rebuild the vault.",
            {
                "project_id": {"type": "string"},
                "apply": {"type": "boolean"},
            },
            ["project_id"],
        ),
        _tool(
            "projectos_query_career_graph",
            "Answer a natural-language question using the project's graph, chunks, and vault notes. "
            "Citations are enforced: invalid answers are regenerated with corrective feedback up to max_citation_retries.",
            {
                "project_id": {"type": "string"},
                "question": {"type": "string"},
                "max_citation_retries": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 3,
                    "default": 1,
                    "description": "Max regenerations when citation validation fails (0 = report only, no retry).",
                },
            },
            ["project_id", "question"],
        ),
        _tool(
            "projectos_run_analysis",
            "Start document and graph analysis for a project.",
            {"project_id": {"type": "string"}},
            ["project_id"],
        ),
        _tool(
            "projectos_get_analysis",
            "Read the latest analysis result for a project.",
            {"project_id": {"type": "string"}},
            ["project_id"],
        ),
        _tool(
            "projectos_run_profiles",
            "Start profile/persona summary generation from a built graph.",
            {"project_id": {"type": "string"}},
            ["project_id"],
        ),
        _tool(
            "projectos_get_profiles",
            "Read generated career profiles for a project.",
            {"project_id": {"type": "string"}},
            ["project_id"],
        ),
        _tool(
            "projectos_run_simulation",
            "Start persona/environment simulation over the current graph and return a task_id.",
            {
                "project_id": {"type": "string"},
                "query": {"type": "string", "default": ""},
                "cv_text": {"type": "string", "default": ""},
                "apply_graph": {"type": "boolean", "default": True},
                "update_vault": {"type": "boolean", "default": True},
            },
            ["project_id"],
        ),
        _tool(
            "projectos_get_simulation",
            "Read the latest simulation report for a project.",
            {"project_id": {"type": "string"}},
            ["project_id"],
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
        _tool(
            "projectos_google_status",
            "Return Google connector status and configured scopes.",
            {},
        ),
        _tool(
            "projectos_google_auth_url",
            "Return the Google OAuth consent URL for Gmail and Drive access.",
            {"state": {"type": "string", "default": "projectos"}},
        ),
        _tool(
            "projectos_google_sync",
            "Sync Gmail and/or Google Drive into a ProjectOS project, then parse and incrementally update the graph if ready.",
            {
                "project_id": {"type": "string"},
                "include_gmail": {"type": "boolean", "default": True},
                "include_drive": {"type": "boolean", "default": True},
                "gmail_query": {"type": "string", "default": ""},
                "drive_query": {"type": "string", "default": ""},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
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

        if name == "projectos_get_upload_api":
            project_id = str(args["project_id"])
            if not project_store.get(project_id):
                raise ValueError("Project not found")
            base_url = str(args.get("base_url") or config.BACKEND_PUBLIC_URL).rstrip("/")
            endpoint = f"{base_url}/api/projects/{project_id}/files"
            payload = {
                "project_id": project_id,
                "method": "POST",
                "endpoint": endpoint,
                "content_type": "multipart/form-data",
                "fields": {
                    "files": "Repeat this form field once per file.",
                    "file_type": "Fallback type. Use note when file_types is provided.",
                    "file_types": (
                        "JSON object keyed by uploaded filename, e.g. "
                        "{\"cv.pdf\":\"cv\",\"paper.pdf\":\"paper\"}."
                    ),
                },
                "supported_file_types": ["cv", "paper", "report", "memo", "email", "note"],
                "curl_example": (
                    "curl -X POST "
                    f"{endpoint!r} "
                    "-F 'files=@/path/to/cv.pdf' "
                    "-F 'files=@/path/to/paper.pdf' "
                    "-F 'file_type=note' "
                    "-F 'file_types={\"cv.pdf\":\"cv\",\"paper.pdf\":\"paper\"}'"
                ),
                "next_steps": [
                    "Upload files directly to this endpoint from the user's browser or terminal.",
                    "Use the returned task_id with projectos_get_task until parsing is completed.",
                    "Then call projectos_build_ontology and projectos_build_graph.",
                ],
            }
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)

        if name == "projectos_list_inbox":
            from app.services.inbox import list_inbox

            payload = await list_inbox(
                str(args.get("relative_path") or ""),
                recursive=bool(args.get("recursive", False)),
                max_items=int(args.get("max_items", 50)),
                classify_files=bool(args.get("classify_files", True)),
            )
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)

        if name == "projectos_preview_inbox_file":
            from app.services.inbox import classify_inbox_file

            payload = await classify_inbox_file(
                str(args["relative_path"]),
                max_chars=int(args.get("max_chars", config.INBOX_PREVIEW_CHARS)),
            )
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)

        if name == "projectos_ingest_inbox_file":
            from app.api.projects import save_file_and_start_parse
            from app.services.inbox import read_inbox_file_for_ingest

            project_id = str(args["project_id"])
            if not project_store.get(project_id):
                raise ValueError("Project not found")
            file_payload = await read_inbox_file_for_ingest(
                str(args["relative_path"]),
                file_type=str(args.get("file_type") or "auto"),
            )
            result = await save_file_and_start_parse(
                project_id,
                file_payload["filename"],
                file_payload["content"],
                file_payload["file_type"],
            )
            payload = {
                **result,
                "relative_path": file_payload["relative_path"],
                "file_type": file_payload["file_type"],
                "classification": file_payload["classification"],
            }
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)

        if name == "projectos_ingest_inbox_files":
            from app.api.projects import save_file_and_start_parse
            from app.services.inbox import read_inbox_file_for_ingest

            project_id = str(args["project_id"])
            if not project_store.get(project_id):
                raise ValueError("Project not found")
            relative_paths = args.get("relative_paths")
            if not isinstance(relative_paths, list) or not relative_paths:
                raise ValueError("relative_paths must be a non-empty array")
            file_types = args.get("file_types") or {}
            if not isinstance(file_types, dict):
                raise ValueError("file_types must be an object")

            ingested = []
            for rel in relative_paths:
                relative_path = str(rel)
                file_payload = await read_inbox_file_for_ingest(
                    relative_path,
                    file_type=str(file_types.get(relative_path) or "auto"),
                )
                result = await save_file_and_start_parse(
                    project_id,
                    file_payload["filename"],
                    file_payload["content"],
                    file_payload["file_type"],
                )
                ingested.append({
                    "relative_path": file_payload["relative_path"],
                    "filename": file_payload["filename"],
                    "file_type": file_payload["file_type"],
                    "task_id": result["task_id"],
                    "classification": file_payload["classification"],
                })
            payload = {"project_id": project_id, "ingested": ingested}
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)

        if name == "projectos_ingest_clip":
            from app.api.projects import save_file_and_start_parse
            from app.services.capture_context import (
                is_complete_context,
                save_capture,
            )
            from app.services.inbox import read_inbox_file_for_ingest

            project_id = str(args["project_id"])
            if not project_store.get(project_id):
                raise ValueError("Project not found")
            relative_path = str(args["relative_path"])
            capture_context = args.get("capture_context")
            if not is_complete_context(capture_context):
                payload = {
                    "status": "needs_context",
                    "project_id": project_id,
                    "relative_path": relative_path,
                    "required_questions": [
                        {"field": "capture_reason",
                         "question": "Why did you capture this content?"},
                        {"field": "current_focus",
                         "question": "What are you currently working on that this relates to?"},
                        {"field": "reflection_intent",
                         "question": "How should this be reflected in your knowledge graph?"},
                    ],
                }
                return _text_result(json.dumps(payload, ensure_ascii=False), payload)

            file_payload = await read_inbox_file_for_ingest(
                relative_path,
                file_type=str(args.get("file_type") or "auto"),
            )
            result = await save_file_and_start_parse(
                project_id,
                file_payload["filename"],
                file_payload["content"],
                file_payload["file_type"],
            )
            saved_source_file = result["files"][0]
            saved_context = save_capture(project_id, saved_source_file, capture_context)
            payload = {
                "status": "ingested",
                "project_id": project_id,
                "task_id": result["task_id"],
                "source_file": saved_source_file,
                "relative_path": file_payload["relative_path"],
                "file_type": file_payload["file_type"],
                "capture_context": saved_context,
                "classification": file_payload["classification"],
            }
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)

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

        if name == "projectos_get_hot_context":
            from app.services.hot_context import compose_hot_context, render_hot_markdown
            from app.services.vault_reconcile import _rendered_graph

            project_id = str(args["project_id"])
            _require_project(project_id)
            graph = _load_graph(project_id)
            rendered = _rendered_graph(graph)
            log_path = Path(config.VAULT_DIR) / project_id / "log.md"
            recent_log = (
                log_path.read_text(encoding="utf-8").splitlines()
                if log_path.exists()
                else None
            )
            ctx = compose_hot_context(rendered, project_id, recent_log=recent_log)
            return _text_result(render_hot_markdown(ctx), ctx)

        if name == "projectos_get_research_candidates":
            from app.services.autoresearch import generate_autoresearch_candidates
            from app.utils.graph_health import run_health_check

            project_id = str(args["project_id"])
            _require_project(project_id)
            graph = _load_graph(project_id)
            chunks = _load_chunks(project_id)
            health = run_health_check(
                graph,
                vault_path=str(Path(config.VAULT_DIR) / project_id),
            )
            candidates = generate_autoresearch_candidates(
                graph,
                chunks=chunks,
                health=health,
                max_candidates=int(args.get("max_candidates", 20)),
                min_degree=int(args.get("min_degree", 1)),
                component_size_threshold=int(args.get("component_size_threshold", 3)),
            )
            by_kind: dict[str, int] = {}
            for candidate in candidates:
                kind = str(candidate.get("kind") or "unknown")
                by_kind[kind] = by_kind.get(kind, 0) + 1
            summary = {
                "candidate_count": len(candidates),
                "by_kind": by_kind,
            }
            lines = [
                f"Research candidates: {len(candidates)}",
                *(f"- {kind}: {count}" for kind, count in sorted(by_kind.items())),
            ]
            payload = {
                "project_id": project_id,
                "candidates": candidates,
                "summary": summary,
            }
            return _text_result("\n".join(lines), payload)

        if name == "projectos_review_graph":
            from app.services.autoresearch import generate_autoresearch_candidates
            from app.services.graph_review import build_graph_review_workflow
            from app.utils.graph_health import run_health_check

            project_id = str(args["project_id"])
            _require_project(project_id)
            graph = _load_graph(project_id)
            chunks = _load_chunks(project_id)
            health = run_health_check(
                graph,
                vault_path=str(Path(config.VAULT_DIR) / project_id),
            )
            candidates = generate_autoresearch_candidates(
                graph,
                chunks=chunks,
                health=health,
                max_candidates=int(args.get("max_candidates", 8)),
                min_degree=int(args.get("min_degree", 1)),
                component_size_threshold=int(args.get("component_size_threshold", 3)),
            )
            workflow = build_graph_review_workflow(
                graph,
                chunks=chunks,
                health=health,
                autoresearch_candidates=candidates,
                project_id=project_id,
                max_candidates=int(args.get("max_candidates", 8)),
            )
            metrics = workflow["evaluation_metrics"]
            text = "\n".join([
                "Graph review workflow: projectos-review-graph",
                "Recommended mode: B_deterministic_prefilter_targeted_claude_review",
                f"Targeted candidates: {len(workflow['targeted_review_candidates'])}",
                f"Graph: {metrics['node_count']} nodes, {metrics['edge_count']} edges",
            ])
            return _text_result(text, workflow)

        if name == "projectos_get_graph_summary":
            from app.services.graph_context import summarize_graph_context

            project_id = str(args["project_id"])
            _require_project(project_id)
            graph = _load_graph(project_id)
            payload = summarize_graph_context(
                graph,
                max_hubs=int(args.get("max_hubs", 10)),
            )
            payload["project_id"] = project_id
            text = "\n".join([
                "Graph summary context",
                f"Nodes: {payload['counts']['nodes']}",
                f"Edges: {payload['counts']['edges']}",
                f"Hubs returned: {len(payload['hubs'])}",
            ])
            return _text_result(text, payload)

        if name == "projectos_get_node_context":
            from app.agents.query_agent import QueryAgent
            from app.services.graph_context import get_node_context
            from app.utils.hybrid_retrieval import hybrid_search

            project_id = str(args["project_id"])
            _require_project(project_id)
            graph = _load_graph(project_id)
            node_name = str(args["node_name"])
            node_type = str(args.get("node_type") or "") or None
            max_neighbors = int(args.get("max_neighbors", 20))

            evidence = None
            if bool(args.get("include_evidence", False)):
                max_evidence = int(args.get("max_evidence", 3))
                chunks = _load_chunks(project_id)
                evidence = []
                if chunks and max_evidence > 0:
                    items = {c.chunk_id: c.text for c in chunks}
                    ranked = await hybrid_search(
                        node_name, project_id, "chunks", items, top_n=max_evidence)
                    by_id = {c.chunk_id: c for c in chunks}
                    evidence = [
                        {
                            "label": QueryAgent._chunk_source_label(by_id[cid]),
                            "text": by_id[cid].text,
                        }
                        for cid in ranked
                        if cid in by_id
                    ]

            payload = get_node_context(
                graph,
                node_name,
                node_type=node_type,
                max_neighbors=max_neighbors,
                evidence=evidence,
            )
            payload["project_id"] = project_id
            selected = payload["match"]["selected_id"] or "not found"
            text = "\n".join([
                "Node context",
                f"Selected: {selected}",
                f"In edges: {payload['counts']['in_edges']}",
                f"Out edges: {payload['counts']['out_edges']}",
            ])
            return _text_result(text, payload)

        if name == "projectos_get_subgraph":
            from app.services.graph_context import get_subgraph_context

            project_id = str(args["project_id"])
            _require_project(project_id)
            graph = _load_graph(project_id)
            payload = get_subgraph_context(
                graph,
                str(args["node_name"]),
                node_type=str(args.get("node_type") or "") or None,
                depth=int(args.get("depth", 1)),
                max_nodes=int(args.get("max_nodes", 25)),
            )
            payload["project_id"] = project_id
            selected = payload["match"]["selected_id"] or "not found"
            text = "\n".join([
                "Subgraph context",
                f"Selected: {selected}",
                f"Nodes returned: {payload['counts']['nodes']}",
                f"Edges returned: {payload['counts']['edges']}",
            ])
            return _text_result(text, payload)

        if name == "projectos_get_ontology":
            project_id = str(args["project_id"])
            _require_project(project_id)
            ontology_path = _project_dir(project_id) / "ontology.json"
            if not ontology_path.exists():
                raise ValueError("Ontology not built yet")
            ontology = json.loads(ontology_path.read_text(encoding="utf-8"))
            return _text_result(
                json.dumps(ontology, ensure_ascii=False),
                {"ontology": ontology},
            )

        if name == "projectos_get_graph":
            project_id = str(args["project_id"])
            _require_project(project_id)
            graph = _load_graph(project_id)
            payload = nx.node_link_data(graph)
            if "edges" in payload and "links" not in payload:
                payload["links"] = payload.pop("edges")
            return _text_result(
                json.dumps(payload, ensure_ascii=False),
                {"graph": payload},
            )

        if name == "projectos_apply_graph_patch":
            from app.utils.graph_patch import apply_project_graph_patch
            from app.utils.trace import record_trace

            project_id = str(args["project_id"])
            _require_project(project_id)
            patch = args.get("patch")
            if isinstance(patch, str):
                try:
                    patch = json.loads(patch)
                except json.JSONDecodeError:
                    raise ValueError("patch string must be valid JSON")
            if not isinstance(patch, dict):
                raise ValueError("patch must be an object")
            result = apply_project_graph_patch(project_id, patch)
            try:
                record_trace(project_id, "graph_patch", **result["changes"])
            except Exception:
                pass
            return _text_result(
                json.dumps(result, ensure_ascii=False),
                result,
            )

        if name == "projectos_reconcile_vault":
            from app.services.vault_reconcile import reconcile_vault

            project_id = str(args["project_id"])
            _require_project(project_id)
            apply = bool(args.get("apply", False))
            result = reconcile_vault(project_id, apply=apply)
            return _text_result(json.dumps(result, ensure_ascii=False), result)

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
            max_retries = int(args.get("max_citation_retries", 1))
            agent = QueryAgent()
            result = await agent.answer_with_enforced_citations(
                question, graph, chunks, vault_path=vault_path, max_retries=max_retries
            )
            result["project_id"] = project_id
            return _text_result(result["answer"], result)

        if name == "projectos_run_analysis":
            from app.api.projects import _run_analysis
            from app.services.task_manager import task_manager

            project_id = str(args["project_id"])
            _require_project(project_id)
            chunks_path = _project_dir(project_id) / "chunks.json"
            if not chunks_path.exists():
                raise ValueError("No files uploaded yet — upload files first")
            task = task_manager.create(project_id, "analysis")
            asyncio.create_task(_run_analysis(task.task_id, project_id))
            payload = task.model_dump(mode="json")
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)

        if name == "projectos_get_analysis":
            project_id = str(args["project_id"])
            _require_project(project_id)
            path = _project_dir(project_id) / "analysis.json"
            if not path.exists():
                raise ValueError("Analysis not run yet")
            analysis = json.loads(path.read_text(encoding="utf-8"))
            return _text_result(
                json.dumps(analysis, ensure_ascii=False),
                {"analysis": analysis},
            )

        if name == "projectos_run_profiles":
            from app.api.projects import _run_profiles
            from app.services.task_manager import task_manager

            project_id = str(args["project_id"])
            _require_project(project_id)
            graph_path = _project_dir(project_id) / "graph.json"
            if not graph_path.exists():
                raise ValueError("Graph not built yet — run graph build first")
            task = task_manager.create(project_id, "profiles")
            asyncio.create_task(_run_profiles(task.task_id, project_id))
            payload = task.model_dump(mode="json")
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)

        if name == "projectos_get_profiles":
            project_id = str(args["project_id"])
            _require_project(project_id)
            path = _project_dir(project_id) / "profiles.json"
            if not path.exists():
                raise ValueError("Profiles not built yet")
            profiles = json.loads(path.read_text(encoding="utf-8"))
            return _text_result(
                json.dumps(profiles, ensure_ascii=False),
                {"profiles": profiles},
            )

        if name == "projectos_run_simulation":
            from app.api.projects import _run_simulation
            from app.services.task_manager import task_manager

            project_id = str(args["project_id"])
            _require_project(project_id)
            graph_path = _project_dir(project_id) / "graph.json"
            chunks_path = _project_dir(project_id) / "chunks.json"
            if not graph_path.exists():
                raise ValueError("Graph not built yet — run graph build first")
            if not chunks_path.exists():
                raise ValueError("No parsed documents found — upload files first")
            task = task_manager.create(project_id, "simulation")
            asyncio.create_task(
                _run_simulation(
                    task.task_id,
                    project_id,
                    query=str(args.get("query") or ""),
                    cv_text=str(args.get("cv_text") or ""),
                    apply_graph=bool(args.get("apply_graph", True)),
                    update_vault=bool(args.get("update_vault", True)),
                )
            )
            payload = task.model_dump(mode="json")
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)

        if name == "projectos_get_simulation":
            project_id = str(args["project_id"])
            _require_project(project_id)
            path = _project_dir(project_id) / "simulation.json"
            if not path.exists():
                raise ValueError("Simulation not run yet")
            simulation = json.loads(path.read_text(encoding="utf-8"))
            return _text_result(
                json.dumps(simulation, ensure_ascii=False),
                {"simulation": simulation},
            )

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

        if name == "projectos_google_status":
            from app.services.google_connector import GoogleConnector

            status = GoogleConnector().status()
            return _text_result(json.dumps(status, ensure_ascii=False), status)

        if name == "projectos_google_auth_url":
            from app.services.google_connector import GoogleConnector

            auth_url = GoogleConnector().auth_url(state=str(args.get("state") or "projectos"))
            return _text_result(auth_url, {"auth_url": auth_url})

        if name == "projectos_google_sync":
            from app.api.google import _run_google_sync_task
            from app.services.task_manager import task_manager

            project_id = str(args["project_id"])
            _require_project(project_id)
            max_results = int(args.get("max_results", config.GOOGLE_SYNC_MAX_RESULTS))
            max_results = max(1, min(max_results, 100))
            task = task_manager.create(project_id, "google_sync")
            asyncio.create_task(
                _run_google_sync_task(
                    task.task_id,
                    project_id,
                    {
                        "include_gmail": bool(args.get("include_gmail", True)),
                        "include_drive": bool(args.get("include_drive", True)),
                        "gmail_query": str(args.get("gmail_query") or config.GOOGLE_GMAIL_QUERY),
                        "drive_query": str(args.get("drive_query") or config.GOOGLE_DRIVE_QUERY),
                        "max_results": max_results,
                        "trigger": "mcp",
                    },
                )
            )
            payload = task.model_dump(mode="json")
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)

        return _text_result(f"Unknown tool: {name}", is_error=True)
    except Exception as exc:
        return _text_result(str(exc), is_error=True)
