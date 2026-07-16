import json
from pathlib import Path

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from networkx.readwrite import json_graph

from app.config import config


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def _write_project(tmp_path: Path) -> str:
    project_id = "testproj"
    proj_dir = tmp_path / project_id
    proj_dir.mkdir()
    (proj_dir / "simulations").mkdir()

    graph = nx.DiGraph()
    graph.add_node("Person:양필성", type="Person", name="양필성")
    out = json_graph.node_link_data(graph)
    (proj_dir / "graph.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    (proj_dir / "chunks.json").write_text("[]", encoding="utf-8")

    simulation = {
        "schema_version": "2.0",
        "run_id": "sim_test_run",
        "graph_delta": {
            "summary": {"proposed_nodes": 1, "proposed_edges": 1,
                        "applied_nodes": 0, "applied_edges": 0, "skipped": 0},
            "nodes": [{
                "delta_id": "delta_node_001", "operation": "add",
                "node_id": "Skill:Monte Carlo Simulation",
                "type": "Skill", "name": "Monte Carlo Simulation",
                "description": "표본 기반 수렴 분석", "confidence": 0.8,
                "evidence_refs": ["Person:양필성"], "duplicate_of": "",
                "status": "proposed", "status_reason": "",
            }],
            "edges": [{
                "delta_id": "delta_edge_001", "operation": "add",
                "source_type": "Person", "source_name": "양필성",
                "target_type": "Skill", "target_name": "Monte Carlo Simulation",
                "relation": "USES_SKILL", "confidence": 0.7,
                "evidence_refs": ["Person:양필성"],
                "status": "proposed", "status_reason": "",
            }],
        },
    }
    text = json.dumps(simulation, ensure_ascii=False)
    (proj_dir / "simulation.json").write_text(text, encoding="utf-8")
    (proj_dir / "simulations" / "sim_test_run.json").write_text(text, encoding="utf-8")
    return project_id


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    return _write_project(tmp_path)


def test_apply_delta_endpoint_returns_applied_status(client, project):
    resp = client.post(
        f"/api/projects/{project}/simulation/delta/apply",
        json={"delta_id": "delta_node_001"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["delta"]["status"] == "applied"
    assert body["applied"]["nodes_added"] == 1


def test_apply_unknown_delta_returns_404(client, project):
    resp = client.post(
        f"/api/projects/{project}/simulation/delta/apply",
        json={"delta_id": "delta_node_999"},
    )
    assert resp.status_code == 404


def test_apply_twice_returns_409(client, project):
    client.post(f"/api/projects/{project}/simulation/delta/apply", json={"delta_id": "delta_node_001"})
    resp = client.post(f"/api/projects/{project}/simulation/delta/apply", json={"delta_id": "delta_node_001"})
    assert resp.status_code == 409


def test_reject_delta_endpoint_persists_reason(client, project):
    resp = client.post(
        f"/api/projects/{project}/simulation/delta/reject",
        json={"delta_id": "delta_edge_001", "reason": "근거 부족"},
    )
    assert resp.status_code == 200
    assert resp.json()["delta"]["status"] == "rejected"
    assert resp.json()["delta"]["status_reason"] == "근거 부족"
