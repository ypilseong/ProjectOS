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
    assert "projectos_get_upload_api" in names
    assert "projectos_list_inbox" in names
    assert "projectos_preview_inbox_file" in names
    assert "projectos_ingest_inbox_file" in names
    assert "projectos_ingest_inbox_files" in names
    assert "projectos_get_task" in names
    assert "projectos_build_ontology" in names
    assert "projectos_build_graph" in names
    assert "projectos_list_projects" in names
    assert "projectos_get_ontology" in names
    assert "projectos_get_graph" in names
    assert "projectos_get_research_candidates" in names
    assert "projectos_review_graph" in names
    assert "projectos_get_graph_summary" in names
    assert "projectos_get_node_context" in names
    assert "projectos_get_subgraph" in names
    assert "projectos_apply_graph_patch" in names
    assert "projectos_query_career_graph" in names
    assert "projectos_run_analysis" in names
    assert "projectos_get_analysis" in names
    assert "projectos_run_profiles" in names
    assert "projectos_get_profiles" in names
    assert "projectos_run_simulation" in names
    assert "projectos_get_simulation" in names
    assert "projectos_generate_digest" in names
    assert "projectos_google_status" in names
    assert "projectos_google_auth_url" in names
    assert "projectos_google_sync" in names


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


def test_mcp_get_upload_api_tool_call():
    project = project_store.create(name="Remote Upload", description="")
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_upload_api",
                "arguments": {
                    "project_id": project.project_id,
                    "base_url": "https://projectos.example.com",
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    payload = result["structuredContent"]
    assert payload["endpoint"] == f"https://projectos.example.com/api/projects/{project.project_id}/files"
    assert payload["content_type"] == "multipart/form-data"
    assert "file_types" in payload["fields"]
    assert "cv" in payload["supported_file_types"]


def test_mcp_list_inbox_tool_call(monkeypatch):
    from app.services import inbox

    class FakeLLM:
        def __init__(self, backend=None):
            self.backend = backend

        async def chat_json(self, messages, **kwargs):
            return {"file_type": "cv", "confidence": 0.8, "reason": "education and experience"}

    monkeypatch.setattr(inbox, "LLMClient", FakeLLM)
    (Path(config.INBOX_DIR) / "cv.txt").write_text(
        "Education\nExperience\nSkills",
        encoding="utf-8",
    )

    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_list_inbox",
                "arguments": {},
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    entry = result["structuredContent"]["entries"][0]
    assert entry["relative_path"] == "cv.txt"
    assert entry["suggested_file_type"] == "cv"


def test_mcp_ingest_inbox_file_auto_classifies(monkeypatch):
    from app.services import inbox

    class FakeLLM:
        def __init__(self, backend=None):
            self.backend = backend

        async def chat_json(self, messages, **kwargs):
            return {"file_type": "paper", "confidence": 0.9, "reason": "abstract and references"}

    monkeypatch.setattr(inbox, "LLMClient", FakeLLM)
    project = project_store.create(name="Inbox Ingest MCP", description="")
    (Path(config.INBOX_DIR) / "paper.txt").write_text(
        "Abstract\nGraph extraction.\nReferences",
        encoding="utf-8",
    )
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "projectos_ingest_inbox_file",
                "arguments": {
                    "project_id": project.project_id,
                    "relative_path": "paper.txt",
                    "file_type": "auto",
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["file_type"] == "paper"
    saved = Path(config.PROJECTS_DIR) / project.project_id / "files" / "paper.txt"
    assert saved.read_text(encoding="utf-8").startswith("Abstract")


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


def test_mcp_get_research_candidates_tool_call():
    project = project_store.create(name="Research Candidates MCP", description="")
    graph = nx.DiGraph()
    graph.add_node("Person:Alice", name="Alice", type="Person", source_files=[])
    graph.add_node("Project:ProjectOS", name="ProjectOS", type="Project", source_files=["readme.md"])
    graph.add_node("Skill:Python", name="Python", type="Skill", source_files=["cv.pdf"])
    graph.add_edge("Project:ProjectOS", "Skill:Python", relation="USES_SKILL")
    project_dir = config_path("PROJECTS_DIR") / project.project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(graph), ensure_ascii=False),
        encoding="utf-8",
    )

    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_research_candidates",
                "arguments": {
                    "project_id": project.project_id,
                    "max_candidates": 5,
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    payload = result["structuredContent"]
    assert payload["project_id"] == project.project_id
    assert payload["summary"]["candidate_count"] > 0
    assert any(
        candidate["id"] == "isolated:Person:Alice"
        for candidate in payload["candidates"]
    )


def test_mcp_review_graph_tool_call():
    project = project_store.create(name="Graph Review MCP", description="")
    graph = nx.DiGraph()
    graph.add_node("Person:Alice", name="Alice", type="Person", source_files=[])
    graph.add_node("Project:ProjectOS", name="ProjectOS", type="Project", source_files=["readme.md"])
    graph.add_node("Skill:Python", name="Python", type="Skill", source_files=["cv.pdf"])
    graph.add_edge("Project:ProjectOS", "Skill:Python", relation="USES_SKILL")
    project_dir = config_path("PROJECTS_DIR") / project.project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(graph), ensure_ascii=False),
        encoding="utf-8",
    )

    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "projectos_review_graph",
                "arguments": {
                    "project_id": project.project_id,
                    "max_candidates": 5,
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    payload = result["structuredContent"]
    assert payload["macro"] == "projectos-review-graph"
    assert payload["project_id"] == project.project_id
    assert payload["read_only"] is True
    assert payload["mode_comparison"][
        "B_deterministic_prefilter_targeted_claude_review"
    ]["recommended"] is True
    assert payload["evaluation_metrics"]["candidate_count"] > 0
    assert payload["targeted_review_candidates"]
    assert payload["token_saving_guidance"]["preferred_mode"] == (
        "B_deterministic_prefilter_targeted_claude_review"
    )


def test_mcp_graph_context_tools_return_compact_payloads():
    project = project_store.create(name="Graph Context MCP", description="")
    graph = nx.DiGraph()
    graph.add_node("Project:ProjectOS", name="ProjectOS", type="Project", source_files=["readme.md"])
    graph.add_node("Skill:Python", name="Python", type="Skill", source_files=["cv.pdf"])
    graph.add_node("Person:Alice", name="Alice", type="Person", source_files=["alice.md"])
    graph.add_edge("Person:Alice", "Project:ProjectOS", relation="CONTRIBUTES_TO")
    graph.add_edge("Project:ProjectOS", "Skill:Python", relation="USES_SKILL")
    project_dir = config_path("PROJECTS_DIR") / project.project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(graph), ensure_ascii=False),
        encoding="utf-8",
    )

    client = TestClient(app)

    summary_resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 41,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_graph_summary",
                "arguments": {"project_id": project.project_id, "max_hubs": 1},
            },
        },
    )
    summary = summary_resp.json()["result"]["structuredContent"]
    assert summary_resp.json()["result"]["isError"] is False
    assert summary["project_id"] == project.project_id
    assert summary["kind"] == "graph_summary"
    assert summary["read_only"] is True
    assert summary["counts"]["nodes"] == 3
    assert [hub["id"] for hub in summary["hubs"]] == ["Project:ProjectOS"]

    node_resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 42,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_node_context",
                "arguments": {
                    "project_id": project.project_id,
                    "node_name": "ProjectOS",
                    "node_type": "Project",
                    "max_neighbors": 2,
                },
            },
        },
    )
    node_payload = node_resp.json()["result"]["structuredContent"]
    assert node_resp.json()["result"]["isError"] is False
    assert node_payload["project_id"] == project.project_id
    assert node_payload["match"]["selected_id"] == "Project:ProjectOS"
    assert node_payload["counts"] == {"in_edges": 1, "out_edges": 1, "neighbors": 2}
    assert node_payload["edges"]["in"][0]["relation"] == "CONTRIBUTES_TO"
    assert node_payload["edges"]["out"][0]["relation"] == "USES_SKILL"

    subgraph_resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 43,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_subgraph",
                "arguments": {
                    "project_id": project.project_id,
                    "node_name": "ProjectOS",
                    "node_type": "Project",
                    "depth": 1,
                    "max_nodes": 2,
                },
            },
        },
    )
    subgraph = subgraph_resp.json()["result"]["structuredContent"]
    assert subgraph_resp.json()["result"]["isError"] is False
    assert subgraph["project_id"] == project.project_id
    assert subgraph["kind"] == "subgraph_context"
    assert subgraph["match"]["selected_id"] == "Project:ProjectOS"
    assert subgraph["counts"]["nodes"] == 2
    assert [node["id"] for node in subgraph["nodes"]] == ["Project:ProjectOS", "Person:Alice"]


def test_mcp_get_node_context_include_evidence_attaches_labeled_chunks():
    project = project_store.create(name="Node Context Evidence", description="")
    graph = nx.DiGraph()
    graph.add_node("Project:ProjectOS", name="ProjectOS", type="Project", source_files=["cv.pdf"])
    graph.add_node("Person:Alice", name="Alice", type="Person", source_files=["alice.md"])
    graph.add_edge("Person:Alice", "Project:ProjectOS", relation="CONTRIBUTES_TO")
    project_dir = config_path("PROJECTS_DIR") / project.project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(graph), ensure_ascii=False),
        encoding="utf-8",
    )
    (project_dir / "chunks.json").write_text(
        json.dumps(
            [
                {
                    "chunk_id": "c1",
                    "text": "ProjectOS builds a NetworkX graph from local files.",
                    "source_file": "cv.pdf",
                    "file_type": "cv",
                    "page_num": 1,
                    "char_offset": 0,
                },
                {
                    "chunk_id": "c2",
                    "text": "An unrelated note about cooking pasta.",
                    "source_file": "memo.md",
                    "file_type": "note",
                    "page_num": 1,
                    "char_offset": 0,
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_node_context",
                "arguments": {
                    "project_id": project.project_id,
                    "node_name": "ProjectOS",
                    "node_type": "Project",
                    "include_evidence": True,
                    "max_evidence": 2,
                },
            },
        },
    )

    payload = resp.json()["result"]["structuredContent"]
    assert resp.json()["result"]["isError"] is False
    assert "evidence" in payload
    assert len(payload["evidence"]) >= 1
    first = payload["evidence"][0]
    assert first["label"] == "[cv.pdf#c1 p.1 char:0]"
    assert "ProjectOS" in first["text"]
    assert set(payload["counts"]) == {"in_edges", "out_edges", "neighbors"}


def test_mcp_get_graph_tool_call():
    project = project_store.create(name="Graph Read MCP", description="")
    _write_graph(project.project_id)
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_graph",
                "arguments": {"project_id": project.project_id},
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["graph"]["nodes"][0]["name"] == "Alpha"


def test_mcp_query_career_graph_returns_citation_report(monkeypatch):
    project = project_store.create(name="Query Citation MCP", description="")
    graph = nx.DiGraph()
    graph.add_node("Skill:Python", name="Python", type="Skill", source_files=["cv.pdf"])
    project_dir = config_path("PROJECTS_DIR") / project.project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(graph), ensure_ascii=False),
        encoding="utf-8",
    )

    async def fake_generate(self, prompt):
        return "Python을 사용합니다 [cv.pdf]. 추가 내용은 근거가 없습니다 [made-up.pdf]."

    monkeypatch.setattr("app.agents.query_agent.QueryAgent._generate", fake_generate)

    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "projectos_query_career_graph",
                "arguments": {
                    "project_id": project.project_id,
                    "question": "Python",
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    payload = result["structuredContent"]
    assert payload["answer"].startswith("Python을 사용합니다")
    assert "[cv.pdf]" in payload["allowed_citation_labels"]
    assert payload["citation_report"]["used_labels"] == ["[cv.pdf]"]
    assert payload["citation_report"]["unknown_labels"] == ["[made-up.pdf]"]
    assert payload["citation_report"]["valid"] is False
    # default max_citation_retries=1 → one regeneration attempt on invalid answer
    assert payload["attempts"] == 2


def test_mcp_query_career_graph_enforces_citations_via_regeneration(monkeypatch):
    project = project_store.create(name="Query Enforce MCP", description="")
    graph = nx.DiGraph()
    graph.add_node("Skill:Python", name="Python", type="Skill", source_files=["cv.pdf"])
    project_dir = config_path("PROJECTS_DIR") / project.project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(graph), ensure_ascii=False),
        encoding="utf-8",
    )

    answers = iter([
        "Python을 사용합니다 [made-up.pdf].",
        "Python을 사용합니다 [cv.pdf].",
    ])

    async def fake_generate(self, prompt):
        return next(answers)

    monkeypatch.setattr("app.agents.query_agent.QueryAgent._generate", fake_generate)

    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "projectos_query_career_graph",
                "arguments": {
                    "project_id": project.project_id,
                    "question": "Python",
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    payload = result["structuredContent"]
    assert payload["attempts"] == 2
    assert payload["answer"] == "Python을 사용합니다 [cv.pdf]."
    assert payload["citation_report"]["valid"] is True
    assert payload["project_id"] == project.project_id


def test_mcp_apply_graph_patch_tool_call():
    project = project_store.create(name="Graph Patch MCP", description="")
    _write_graph(project.project_id)
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "projectos_apply_graph_patch",
                "arguments": {
                    "project_id": project.project_id,
                    "patch": {
                        "nodes_add": [
                            {
                                "type": "Project",
                                "name": "ProjectOS",
                                "description": "Career graph system",
                            }
                        ],
                        "edges_add": [
                            {
                                "source_id": "n1",
                                "target_type": "Project",
                                "target_name": "ProjectOS",
                                "relation": "RELATED_TO",
                            }
                        ],
                    },
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["changes"]["nodes_added"] == 1
    assert result["structuredContent"]["changes"]["edges_added"] == 1

    graph_data = json.loads(
        (Path(config.PROJECTS_DIR) / project.project_id / "graph.json").read_text(encoding="utf-8")
    )
    if "links" in graph_data and "edges" not in graph_data:
        graph_data["edges"] = graph_data.pop("links")
    graph = nx.node_link_graph(graph_data)
    assert "Project:ProjectOS" in graph
    assert graph.has_edge("n1", "Project:ProjectOS")


def test_mcp_apply_graph_patch_requires_object():
    project = project_store.create(name="Graph Patch Invalid MCP", description="")
    _write_graph(project.project_id)
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "projectos_apply_graph_patch",
                "arguments": {
                    "project_id": project.project_id,
                    "patch": [],
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is True
    assert "patch must be an object" in result["content"][0]["text"]


def test_mcp_apply_graph_patch_accepts_json_string_patch():
    project = project_store.create(name="Graph Patch String MCP", description="")
    _write_graph(project.project_id)
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "projectos_apply_graph_patch",
                "arguments": {
                    "project_id": project.project_id,
                    "patch": json.dumps({
                        "nodes_add": [
                            {"type": "Project", "name": "ProjectOS"}
                        ]
                    }),
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["changes"]["nodes_added"] == 1


def test_mcp_run_simulation_starts_task(monkeypatch):
    project = project_store.create(name="Simulation MCP", description="")
    project_dir = Path(config.PROJECTS_DIR) / project.project_id
    (project_dir / "chunks.json").write_text("[]", encoding="utf-8")
    _write_graph(project.project_id)
    seen = {}

    async def fake_run_simulation(task_id, project_id, query, cv_text, apply_graph, update_vault):
        seen["task_id"] = task_id
        seen["project_id"] = project_id
        seen["query"] = query
        seen["apply_graph"] = apply_graph
        seen["update_vault"] = update_vault

    monkeypatch.setattr("app.api.projects._run_simulation", fake_run_simulation)

    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "projectos_run_simulation",
                "arguments": {
                    "project_id": project.project_id,
                    "query": "분석 리포트를 작성하세요",
                    "apply_graph": False,
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["task_type"] == "simulation"
    assert seen == {
        "task_id": result["structuredContent"]["task_id"],
        "project_id": project.project_id,
        "query": "분석 리포트를 작성하세요",
        "apply_graph": False,
        "update_vault": True,
    }


def test_mcp_get_simulation_tool_call():
    project = project_store.create(name="Simulation Read MCP", description="")
    project_dir = Path(config.PROJECTS_DIR) / project.project_id
    payload = {"report": {"title": "Simulation Report", "answer": "ok"}}
    (project_dir / "simulation.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_simulation",
                "arguments": {"project_id": project.project_id},
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["simulation"]["report"]["answer"] == "ok"


def test_mcp_google_auth_url_tool_call(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "client-id")
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "projectos_google_auth_url",
                "arguments": {"state": "abc"},
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert "accounts.google.com" in result["structuredContent"]["auth_url"]
    assert "state=abc" in result["structuredContent"]["auth_url"]


def test_mcp_google_sync_starts_task(monkeypatch):
    project = project_store.create(name="Google Sync MCP", description="")
    seen = {}

    async def fake_google_sync_task(task_id, project_id, options):
        seen["task_id"] = task_id
        seen["project_id"] = project_id
        seen["options"] = options

    monkeypatch.setattr("app.api.google._run_google_sync_task", fake_google_sync_task)

    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "projectos_google_sync",
                "arguments": {
                    "project_id": project.project_id,
                    "include_gmail": True,
                    "include_drive": False,
                    "gmail_query": "newer_than:1d",
                    "max_results": 5,
                },
            },
        },
    )

    result = resp.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["task_type"] == "google_sync"
    assert seen["task_id"] == result["structuredContent"]["task_id"]
    assert seen["project_id"] == project.project_id
    assert seen["options"]["include_gmail"] is True
    assert seen["options"]["include_drive"] is False
    assert seen["options"]["gmail_query"] == "newer_than:1d"
    assert seen["options"]["trigger"] == "mcp"


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


def test_mcp_tools_list_includes_reconcile_vault():
    from app.mcp_tools import list_mcp_tools
    names = {t["name"] for t in list_mcp_tools()}
    assert "projectos_reconcile_vault" in names


def test_mcp_reconcile_vault_dry_run_tool_call():
    project = project_store.create(name="Reconcile MCP", description="")
    _write_graph(project.project_id)
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "projectos_reconcile_vault",
                "arguments": {"project_id": project.project_id},
            },
        },
    )
    result = resp.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["applied"] is False
    assert "summary" in result["structuredContent"]


def test_mcp_hot_context_tool_registered():
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    names = {tool["name"] for tool in resp.json()["result"]["tools"]}
    assert "projectos_get_hot_context" in names


def test_mcp_hot_context_returns_structured():
    project = project_store.create(name="Hot MCP", description="")
    _write_graph(project.project_id)
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_hot_context",
                "arguments": {"project_id": project.project_id},
            },
        },
    )
    result = resp.json()["result"]
    assert result["isError"] is False
    sc = result["structuredContent"]
    assert "persona" in sc
    assert "hubs_by_type" in sc
    assert "stats" in sc


def test_mcp_hot_context_unbuilt_is_error():
    project = project_store.create(name="Hot Unbuilt MCP", description="")
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_hot_context",
                "arguments": {"project_id": project.project_id},
            },
        },
    )
    result = resp.json()["result"]
    assert result["isError"] is True
