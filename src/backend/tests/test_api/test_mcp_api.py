import json
from pathlib import Path

import networkx as nx
from fastapi.testclient import TestClient

from app.config import config
from app.main import app
from app.services.project_store import project_store


def _write_graph(project_id: str):
    graph = nx.DiGraph()
    graph.add_node("n1", name="Alpha", type="Skill", source_files=["f.txt"])
    project_dir = config_path("PROJECTS_DIR") / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(graph), ensure_ascii=False),
        encoding="utf-8",
    )


def config_path(name: str):
    from pathlib import Path

    return Path(getattr(config, name))


def test_mcp_initialize():
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert body["result"]["serverInfo"]["name"] == "projectos"
    assert "tools" in body["result"]["capabilities"]


def test_mcp_tools_list_includes_projectos_tools():
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )

    names = {tool["name"] for tool in resp.json()["result"]["tools"]}
    assert "projectos_create_project" in names
    assert "projectos_upload_file" in names
    assert "projectos_get_task" in names
    assert "projectos_build_ontology" in names
    assert "projectos_build_graph" in names
    assert "projectos_list_projects" in names
    assert "projectos_query_career_graph" in names
    assert "projectos_generate_digest" in names


def test_mcp_create_project_tool_call():
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_create_project",
                "arguments": {
                    "name": "Created from MCP",
                    "description": "Claude Desktop test",
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    project_id = result["structuredContent"]["project_id"]
    project = project_store.get(project_id)
    assert project is not None
    assert project.name == "Created from MCP"
    assert project.description == "Claude Desktop test"


def test_mcp_create_project_requires_name():
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_create_project",
                "arguments": {"name": "  "},
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is True
    assert "name is required" in result["content"][0]["text"]


def test_mcp_upload_file_tool_call_text_content():
    project = project_store.create(name="Upload From MCP", description="")
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_upload_file",
                "arguments": {
                    "project_id": project.project_id,
                    "filename": "note.txt",
                    "content_text": "hello from claude desktop",
                    "file_type": "note",
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert "task_id" in result["structuredContent"]
    saved = Path(config.PROJECTS_DIR) / project.project_id / "files" / "note.txt"
    assert saved.read_text(encoding="utf-8") == "hello from claude desktop"


def test_mcp_upload_file_tool_call_base64_content():
    import base64

    project = project_store.create(name="Upload Binary From MCP", description="")
    client = TestClient(app)
    content = b"%PDF-1.4 fake pdf bytes"
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_upload_file",
                "arguments": {
                    "project_id": project.project_id,
                    "filename": "cv.pdf",
                    "content_base64": base64.b64encode(content).decode("ascii"),
                    "file_type": "resume",
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    saved = Path(config.PROJECTS_DIR) / project.project_id / "files" / "cv.pdf"
    assert saved.read_bytes() == content


def test_mcp_upload_file_requires_content():
    project = project_store.create(name="Upload Missing Content", description="")
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_upload_file",
                "arguments": {
                    "project_id": project.project_id,
                    "filename": "empty.txt",
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is True
    assert "content_base64 or content_text is required" in result["content"][0]["text"]


def test_mcp_get_task_tool_call():
    from app.services.task_manager import task_manager

    project = project_store.create(name="Task MCP", description="")
    task = task_manager.create(project.project_id, "parse")
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_task",
                "arguments": {"task_id": task.task_id},
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["task_id"] == task.task_id
    assert result["structuredContent"]["task_type"] == "parse"


def test_mcp_build_ontology_requires_chunks():
    project = project_store.create(name="No Chunks MCP", description="")
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_build_ontology",
                "arguments": {"project_id": project.project_id},
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is True
    assert "upload files and wait for parse" in result["content"][0]["text"]


def test_mcp_build_ontology_starts_task(monkeypatch):
    project = project_store.create(name="Ontology MCP", description="")
    project_dir = Path(config.PROJECTS_DIR) / project.project_id
    (project_dir / "chunks.json").write_text("[]", encoding="utf-8")
    seen = {}

    async def fake_run_ontology(task_id, project_id):
        seen["task_id"] = task_id
        seen["project_id"] = project_id

    monkeypatch.setattr("app.api.graph._run_ontology", fake_run_ontology)

    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_build_ontology",
                "arguments": {"project_id": project.project_id},
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["task_type"] == "ontology"
    assert seen["project_id"] == project.project_id


def test_mcp_build_graph_requires_ontology():
    project = project_store.create(name="No Ontology MCP", description="")
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_build_graph",
                "arguments": {"project_id": project.project_id},
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is True
    assert "run projectos_build_ontology first" in result["content"][0]["text"]


def test_mcp_build_graph_starts_task(monkeypatch):
    project = project_store.create(name="Graph MCP", description="")
    project_dir = Path(config.PROJECTS_DIR) / project.project_id
    (project_dir / "ontology.json").write_text(
        json.dumps({"entity_types": [], "edge_types": [], "analysis_summary": ""}),
        encoding="utf-8",
    )
    seen = {}

    async def fake_run_graph(task_id, project_id, incremental):
        seen["task_id"] = task_id
        seen["project_id"] = project_id
        seen["incremental"] = incremental

    monkeypatch.setattr("app.api.graph._run_graph", fake_run_graph)

    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_build_graph",
                "arguments": {"project_id": project.project_id},
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["task_type"] == "graph"
    assert seen == {
        "task_id": result["structuredContent"]["task_id"],
        "project_id": project.project_id,
        "incremental": False,
    }


def test_mcp_list_projects_tool_call():
    project = project_store.create(name="Demo", description="MCP test")
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_list_projects",
                "arguments": {},
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["projects"][0]["project_id"] == project.project_id


def test_mcp_get_graph_health_tool_call():
    project = project_store.create(name="Demo", description="")
    _write_graph(project.project_id)
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_graph_health",
                "arguments": {"project_id": project.project_id},
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert "health" in result["structuredContent"]


def test_mcp_get_vault_note_rejects_path_escape():
    project = project_store.create(name="Demo", description="")
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_vault_note",
                "arguments": {"project_id": project.project_id, "path": "../outside.md"},
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is True
    assert "outside project vault" in result["content"][0]["text"]


def test_mcp_notification_returns_accepted():
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )

    assert resp.status_code == 202


def test_mcp_ping():
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 6, "method": "ping"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"jsonrpc": "2.0", "id": 6, "result": {}}
