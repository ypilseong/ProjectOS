import json
from pathlib import Path

import networkx as nx
import pytest
from networkx.readwrite import json_graph

from app.config import config


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
    return _write_project(tmp_path), tmp_path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_apply_node_delta_adds_node_and_updates_statuses(project):
    from app.services.simulation_delta import apply_simulation_delta

    project_id, tmp_path = project
    result = apply_simulation_delta(project_id, "delta_node_001")

    assert result["delta"]["status"] == "applied"
    assert result["applied"]["nodes_added"] == 1

    graph_data = _load(tmp_path / project_id / "graph.json")
    node_ids = {n["id"] for n in graph_data["nodes"]}
    assert "Skill:Monte Carlo Simulation" in node_ids

    saved = _load(tmp_path / project_id / "simulation.json")
    assert saved["graph_delta"]["nodes"][0]["status"] == "applied"
    assert saved["graph_delta"]["summary"]["applied_nodes"] == 1
    archived = _load(tmp_path / project_id / "simulations" / "sim_test_run.json")
    assert archived["graph_delta"]["nodes"][0]["status"] == "applied"


def test_apply_edge_delta_after_node(project):
    from app.services.simulation_delta import apply_simulation_delta

    project_id, tmp_path = project
    apply_simulation_delta(project_id, "delta_node_001")
    result = apply_simulation_delta(project_id, "delta_edge_001")

    assert result["delta"]["status"] == "applied"
    graph_data = _load(tmp_path / project_id / "graph.json")
    edge_key = "links" if "links" in graph_data else "edges"
    pairs = {(e["source"], e["target"]) for e in graph_data[edge_key]}
    assert ("Person:양필성", "Skill:Monte Carlo Simulation") in pairs


def test_apply_twice_raises_conflict(project):
    from app.services.simulation_delta import SimulationDeltaError, apply_simulation_delta

    project_id, _ = project
    apply_simulation_delta(project_id, "delta_node_001")
    with pytest.raises(SimulationDeltaError) as exc:
        apply_simulation_delta(project_id, "delta_node_001")
    assert exc.value.status_code == 409


def test_reject_marks_delta_rejected_without_touching_graph(project):
    from app.services.simulation_delta import reject_simulation_delta

    project_id, tmp_path = project
    result = reject_simulation_delta(project_id, "delta_node_001", reason="근거 부족")

    assert result["delta"]["status"] == "rejected"
    assert result["delta"]["status_reason"] == "근거 부족"
    graph_data = _load(tmp_path / project_id / "graph.json")
    node_ids = {n["id"] for n in graph_data["nodes"]}
    assert "Skill:Monte Carlo Simulation" not in node_ids


def test_unknown_delta_raises_404(project):
    from app.services.simulation_delta import SimulationDeltaError, apply_simulation_delta

    project_id, _ = project
    with pytest.raises(SimulationDeltaError) as exc:
        apply_simulation_delta(project_id, "delta_node_999")
    assert exc.value.status_code == 404
