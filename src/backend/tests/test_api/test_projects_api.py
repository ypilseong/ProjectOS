import pytest
from fastapi.testclient import TestClient
from pathlib import Path


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_create_project(client):
    r = client.post("/api/projects", json={"name": "Test Project", "description": "A test"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Test Project"
    assert "project_id" in data


def test_list_projects(client):
    client.post("/api/projects", json={"name": "Project A"})
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1


def test_get_project(client):
    create_r = client.post("/api/projects", json={"name": "My Graph"})
    pid = create_r.json()["project_id"]
    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 200
    assert r.json()["project_id"] == pid


def test_get_missing_project(client):
    r = client.get("/api/projects/doesnotexist")
    assert r.status_code == 404


def test_delete_project(client):
    create_r = client.post("/api/projects", json={"name": "To Delete"})
    pid = create_r.json()["project_id"]
    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_upload_files(client, tmp_path):
    create_r = client.post("/api/projects", json={"name": "Upload Test"})
    pid = create_r.json()["project_id"]
    content = b"Test content for parsing " * 20
    r = client.post(
        f"/api/projects/{pid}/files",
        files=[("files", ("test.txt", content, "text/plain"))],
        data={"file_type": "note"},
    )
    assert r.status_code == 200
    assert "task_id" in r.json()


def test_get_vault_tree_empty(client):
    create_r = client.post("/api/projects", json={"name": "Vault Test"})
    pid = create_r.json()["project_id"]
    r = client.get(f"/api/projects/{pid}/vault")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_export_vault_returns_404_when_graph_missing(client):
    create_r = client.post("/api/projects", json={"name": "Vault Export Missing"})
    pid = create_r.json()["project_id"]

    r = client.get(f"/api/projects/{pid}/vault/export")

    assert r.status_code == 404
    assert r.json()["detail"] == "Graph not built yet"


def test_export_vault_returns_payload(client):
    import json as _json

    import networkx as nx
    from networkx.readwrite import json_graph

    from app.config import config as _cfg

    create_r = client.post("/api/projects", json={"name": "Vault Export"})
    pid = create_r.json()["project_id"]
    proj_dir = Path(_cfg.PROJECTS_DIR) / pid

    graph = nx.DiGraph()
    graph.add_node(
        "Person:Yang Pilseong",
        type="Person",
        name="Yang Pilseong",
        description="Researcher",
        source_files=["cv.pdf"],
        source_chunk_ids=["c1"],
    )
    graph.add_node(
        "Skill:Python",
        type="Skill",
        name="Python",
        description="Programming language",
        source_files=["cv.pdf"],
        source_chunk_ids=["c1"],
    )
    graph.add_edge("Person:Yang Pilseong", "Skill:Python", relation="USES_SKILL")
    graph_data = json_graph.node_link_data(graph)
    (proj_dir / "graph.json").write_text(
        _json.dumps(graph_data, ensure_ascii=False),
        encoding="utf-8",
    )

    r = client.get(f"/api/projects/{pid}/vault/export")

    assert r.status_code == 200
    payload = r.json()
    assert set(payload) == {"notes", "canvas", "index", "log_entry"}
    assert payload["canvas"]["filename"] == "_index.canvas"
    assert payload["index"]["filename"] == "_index.md"
    assert any(
        note["folder"] == "Career" and note["filename"] == "Yang Pilseong.md"
        for note in payload["notes"]
    )
    person_note = next(
        note for note in payload["notes"]
        if note["folder"] == "Career" and note["filename"] == "Yang Pilseong.md"
    )
    assert "## Details" in person_note["content"]
    assert "### 보유 기술" in person_note["content"]
    assert "Project: " + pid in payload["log_entry"]


def test_get_analysis_returns_404_when_not_run(client):
    r = client.post("/api/projects", json={"name": "Analysis Test"})
    pid = r.json()["project_id"]
    r2 = client.get(f"/api/projects/{pid}/analysis")
    assert r2.status_code == 404


def test_run_analysis_returns_400_when_no_chunks(client):
    r = client.post("/api/projects", json={"name": "No Chunks"})
    pid = r.json()["project_id"]
    r2 = client.post(f"/api/projects/{pid}/analysis")
    assert r2.status_code == 400


def test_run_analysis_returns_task_id_when_chunks_exist(client):
    import json as _json
    from unittest.mock import AsyncMock, patch

    from app.config import config as _cfg

    r = client.post("/api/projects", json={"name": "Has Chunks"})
    pid = r.json()["project_id"]

    proj_dir = Path(_cfg.PROJECTS_DIR) / pid
    proj_dir.mkdir(parents=True, exist_ok=True)
    chunks_data = [
        {
            "chunk_id": "c1",
            "text": "test",
            "source_file": "cv.pdf",
            "file_type": "note",
            "page_num": None,
            "char_offset": 0,
        }
    ]
    (proj_dir / "chunks.json").write_text(_json.dumps(chunks_data))

    mock_result = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "summary": "테스트",
        "issues": [],
        "improved_draft": "초안",
    }
    with patch(
        "app.agents.analysis_agent.AnalysisAgent.run",
        new=AsyncMock(return_value=mock_result),
    ):
        r2 = client.post(f"/api/projects/{pid}/analysis")

    assert r2.status_code == 200
    assert "task_id" in r2.json()


def test_get_profiles_returns_404_when_not_run(client):
    r = client.post("/api/projects", json={"name": "Profiles Test"})
    pid = r.json()["project_id"]
    r2 = client.get(f"/api/projects/{pid}/profiles")
    assert r2.status_code == 404


def test_run_profiles_returns_400_when_no_graph(client):
    r = client.post("/api/projects", json={"name": "No Graph"})
    pid = r.json()["project_id"]
    r2 = client.post(f"/api/projects/{pid}/profiles")
    assert r2.status_code == 400


def test_run_profiles_returns_task_id_when_graph_and_user_exist(client):
    import json as _json
    from pathlib import Path
    from app.config import config as _cfg
    from unittest.mock import patch, AsyncMock

    r = client.post("/api/projects", json={"name": "Has Graph"})
    pid = r.json()["project_id"]

    proj_dir = Path(_cfg.PROJECTS_DIR) / pid
    graph_data = {
        "directed": True, "multigraph": False, "graph": {},
        "nodes": [{"type": "Person", "name": "양필성", "id": "Person:양필성",
                   "description": "", "source_files": [], "attributes": {}}],
        "links": [],
    }
    (proj_dir / "graph.json").write_text(_json.dumps(graph_data))
    Path(_cfg.USER_CONFIG_PATH).write_text(
        _json.dumps({"name": "양필성", "display_name": "Pilseong Yang"})
    )

    with patch("app.agents.profile_agent.ProfileAgent.run", new=AsyncMock(return_value=[])):
        r2 = client.post(f"/api/projects/{pid}/profiles")

    assert r2.status_code == 200
    assert "task_id" in r2.json()


def test_get_simulation_returns_404_when_not_run(client):
    r = client.post("/api/projects", json={"name": "Simulation Test"})
    pid = r.json()["project_id"]
    r2 = client.get(f"/api/projects/{pid}/simulation")
    assert r2.status_code == 404


def test_run_simulation_requires_graph(client):
    r = client.post("/api/projects", json={"name": "No Simulation Graph"})
    pid = r.json()["project_id"]
    r2 = client.post(f"/api/projects/{pid}/simulation", json={"query": "Improve CV"})
    assert r2.status_code == 400


def test_run_simulation_returns_task_id_when_graph_and_chunks_exist(client):
    import json as _json
    from pathlib import Path
    from unittest.mock import AsyncMock, patch

    from app.config import config as _cfg

    r = client.post("/api/projects", json={"name": "Simulation Ready"})
    pid = r.json()["project_id"]
    proj_dir = Path(_cfg.PROJECTS_DIR) / pid
    graph_data = {
        "directed": True,
        "multigraph": False,
        "graph": {},
        "nodes": [{"type": "Person", "name": "Yang", "id": "Person:Yang"}],
        "links": [],
    }
    chunks_data = [
        {
            "chunk_id": "c1",
            "text": "Yang built ProjectOS.",
            "source_file": "cv.pdf",
            "file_type": "cv",
            "page_num": None,
            "char_offset": 0,
        }
    ]
    (proj_dir / "graph.json").write_text(_json.dumps(graph_data), encoding="utf-8")
    (proj_dir / "chunks.json").write_text(_json.dumps(chunks_data), encoding="utf-8")

    mock_result = {
        "personas": [],
        "environment": {},
        "timeline": [],
        "graph_enhancements": {"nodes": [], "edges": []},
        "cv_improvements": {},
        "report": {"answer": "ok"},
        "applied_graph_changes": {"nodes_added": 0, "edges_added": 0},
    }
    with patch(
        "app.agents.simulation_agent.ProjectSimulationAgent.run",
        new=AsyncMock(return_value=mock_result),
    ):
        r2 = client.post(
            f"/api/projects/{pid}/simulation",
            json={"query": "Improve CV", "apply_graph": False, "update_vault": False},
        )

    assert r2.status_code == 200
    assert "task_id" in r2.json()
