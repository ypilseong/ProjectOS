import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import json


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


def test_upload_files_accepts_per_file_type_map(client):
    create_r = client.post("/api/projects", json={"name": "Typed Upload Test"})
    pid = create_r.json()["project_id"]

    r = client.post(
        f"/api/projects/{pid}/files",
        files=[
            ("files", ("cv.txt", b"CV content " * 20, "text/plain")),
            ("files", ("paper.txt", b"Paper content " * 20, "text/plain")),
        ],
        data={
            "file_type": "note",
            "file_types": json.dumps({"cv.txt": "cv", "paper.txt": "paper"}),
        },
    )

    assert r.status_code == 200
    assert r.json()["file_types"] == {"cv.txt": "cv", "paper.txt": "paper"}


@pytest.mark.asyncio
async def test_run_parse_preserves_per_file_types(client):
    from app.api.projects import _run_parse
    from app.config import config as _cfg
    from app.services.task_manager import task_manager

    create_r = client.post("/api/projects", json={"name": "Typed Parse Test"})
    pid = create_r.json()["project_id"]
    files_dir = Path(_cfg.PROJECTS_DIR) / pid / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    cv_path = files_dir / "cv.txt"
    memo_path = files_dir / "memo.txt"
    cv_path.write_text("CV text " * 30, encoding="utf-8")
    memo_path.write_text("Memo text " * 30, encoding="utf-8")

    task = task_manager.create(pid, "parse")
    await _run_parse(
        task.task_id,
        pid,
        [str(cv_path), str(memo_path)],
        {"cv.txt": "cv", "memo.txt": "memo"},
    )

    chunks = json.loads((Path(_cfg.PROJECTS_DIR) / pid / "chunks.json").read_text(encoding="utf-8"))
    file_types = {chunk["source_file"]: chunk["file_type"] for chunk in chunks}
    assert file_types == {"cv.txt": "cv", "memo.txt": "memo"}


def test_upload_raw_file(client):
    from app.config import config as _cfg

    create_r = client.post("/api/projects", json={"name": "Raw Upload Test"})
    pid = create_r.json()["project_id"]
    content = b"raw text content for mcp upload"

    r = client.post(
        f"/api/projects/{pid}/files/raw?filename=raw.txt&file_type=note",
        content=content,
        headers={"Content-Type": "application/octet-stream"},
    )

    assert r.status_code == 200
    assert "task_id" in r.json()
    assert r.json()["files"] == ["raw.txt"]
    saved = Path(_cfg.PROJECTS_DIR) / pid / "files" / "raw.txt"
    assert saved.read_bytes() == content


def test_upload_base64_file(client):
    import base64
    from app.config import config as _cfg

    create_r = client.post("/api/projects", json={"name": "Base64 Upload Test"})
    pid = create_r.json()["project_id"]
    content = b"base64 text content for mcp upload"

    r = client.post(
        f"/api/projects/{pid}/files/base64",
        json={
            "filename": "encoded.txt",
            "content_base64": base64.b64encode(content).decode("ascii"),
            "file_type": "note",
        },
    )

    assert r.status_code == 200
    assert "task_id" in r.json()
    saved = Path(_cfg.PROJECTS_DIR) / pid / "files" / "encoded.txt"
    assert saved.read_bytes() == content


def test_upload_base64_file_rejects_invalid_content(client):
    create_r = client.post("/api/projects", json={"name": "Bad Base64 Upload Test"})
    pid = create_r.json()["project_id"]

    r = client.post(
        f"/api/projects/{pid}/files/base64",
        json={"filename": "bad.txt", "content_base64": "not base64 !!!"},
    )

    assert r.status_code == 400
    assert r.json()["detail"] == "content_base64 is invalid"


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


def test_reconcile_endpoint_dry_run_returns_patch(client, tmp_path, monkeypatch):
    import json
    import networkx as nx
    from app.config import config

    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    pid = "pApi"
    g = nx.DiGraph()
    g.add_node("Skill:Python", type="Skill", name="Python", description="언어")
    pdir = tmp_path / "projects" / pid
    pdir.mkdir(parents=True)
    data = nx.node_link_data(g)
    if "edges" in data and "links" not in data:
        data["links"] = data.pop("edges")
    (pdir / "graph.json").write_text(json.dumps(data), encoding="utf-8")
    page = tmp_path / "vault" / pid / "Skills" / "Python.md"
    page.parent.mkdir(parents=True)
    page.write_text('---\ntype: Skill\nname: "Python"\n---\n\n## Overview\n새 설명\n',
                    encoding="utf-8")

    resp = client.post(f"/api/projects/{pid}/reconcile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is False
    assert body["summary"]["nodes_update"] >= 1


def test_reconcile_endpoint_missing_graph_returns_400(client, tmp_path, monkeypatch):
    from app.config import config
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    resp = client.post("/api/projects/nope/reconcile")
    assert resp.status_code == 400
