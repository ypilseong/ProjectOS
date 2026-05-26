import json
import pytest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def two_project_dirs(tmp_path):
    for proj_id, name in [("proj1", "프로젝트A"), ("proj2", "프로젝트B")]:
        d = tmp_path / proj_id
        d.mkdir()
        (d / "meta.json").write_text(
            json.dumps({"project_id": proj_id, "name": name, "status": "ready"})
        )
        graph = {
            "nodes": [
                {"id": "n1", "name": "홍길동", "type": "Person"},
                {"id": "n2", "name": "Python", "type": "Skill"},
            ],
            "links": [{"source": "n1", "target": "n2", "relation": "USES_SKILL"}],
        }
        (d / "graph.json").write_text(json.dumps(graph))
    return tmp_path


def test_global_graph_empty_when_no_graphs(client, tmp_path):
    with patch("app.api.graph.config") as mock_cfg:
        mock_cfg.PROJECTS_DIR = str(tmp_path)
        r = client.get("/api/graph/global")
    assert r.status_code == 200
    data = r.json()
    assert data["nodes"] == []
    assert data["links"] == []
    assert data["projects"] == []


def test_global_graph_namespaces_node_ids(client, two_project_dirs):
    with patch("app.api.graph.config") as mock_cfg:
        mock_cfg.PROJECTS_DIR = str(two_project_dirs)
        r = client.get("/api/graph/global")
    assert r.status_code == 200
    data = r.json()
    node_ids = {n["id"] for n in data["nodes"]}
    assert "proj1::n1" in node_ids
    assert "proj2::n1" in node_ids
    assert len(node_ids) == 4  # 충돌 없이 4개


def test_global_graph_links_use_namespaced_ids(client, two_project_dirs):
    with patch("app.api.graph.config") as mock_cfg:
        mock_cfg.PROJECTS_DIR = str(two_project_dirs)
        r = client.get("/api/graph/global")
    data = r.json()
    link_sources = {lnk["source"] for lnk in data["links"]}
    assert "proj1::n1" in link_sources
    assert "proj2::n1" in link_sources


def test_global_graph_includes_project_metadata(client, two_project_dirs):
    with patch("app.api.graph.config") as mock_cfg:
        mock_cfg.PROJECTS_DIR = str(two_project_dirs)
        r = client.get("/api/graph/global")
    data = r.json()
    project_ids = {p["id"] for p in data["projects"]}
    assert "proj1" in project_ids
    assert "proj2" in project_ids
    names = {p["name"] for p in data["projects"]}
    assert "프로젝트A" in names


def test_global_graph_skips_projects_without_graph(client, tmp_path):
    d = tmp_path / "nograph"
    d.mkdir()
    (d / "meta.json").write_text(
        json.dumps({"project_id": "nograph", "name": "No Graph"})
    )
    # graph.json 없음
    with patch("app.api.graph.config") as mock_cfg:
        mock_cfg.PROJECTS_DIR = str(tmp_path)
        r = client.get("/api/graph/global")
    data = r.json()
    assert data["nodes"] == []
    assert data["projects"] == []
