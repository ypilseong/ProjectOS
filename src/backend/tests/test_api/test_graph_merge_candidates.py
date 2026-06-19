import json
from pathlib import Path

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from app.config import config


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def _write_graph_with_candidates(project_id: str) -> None:
    """Two similar Skill nodes both linked to a Person, with collected candidates."""
    from app.utils.merge_review import collect_merge_candidates

    g = nx.DiGraph()
    g.add_node("Person:Kim", type="Person", name="Kim", source_files=["cv.pdf"])
    g.add_node(
        "Skill:TensorFlow", type="Skill", name="TensorFlow", source_files=["cv.pdf"]
    )
    g.add_node(
        "Skill:Tensorflow", type="Skill", name="Tensorflow", source_files=["p.pdf"]
    )
    g.add_edge("Person:Kim", "Skill:TensorFlow", relation="USES_SKILL")
    g.add_edge("Person:Kim", "Skill:Tensorflow", relation="USES_SKILL")
    g.graph["merge_candidates"] = collect_merge_candidates(g)

    proj_dir = Path(config.PROJECTS_DIR) / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    out = nx.node_link_data(g)
    if "edges" in out and "links" not in out:
        out["links"] = out.pop("edges")
    (proj_dir / "graph.json").write_text(json.dumps(out), encoding="utf-8")


def _load_graph_json(project_id: str) -> dict:
    p = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_apply_merges_nodes_and_refreshes_candidates(client):
    _write_graph_with_candidates("proj_apply")

    r = client.post(
        "/api/projects/proj_apply/graph/merge-candidates/apply",
        json={"keep_id": "Skill:TensorFlow", "candidate_id": "Skill:Tensorflow"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["merged"] is True
    # The dup node is gone from the persisted graph.
    node_ids = {n["id"] for n in _load_graph_json("proj_apply")["nodes"]}
    assert "Skill:Tensorflow" not in node_ids
    assert "Skill:TensorFlow" in node_ids
    # The merged pair no longer appears among candidates.
    pairs = {
        frozenset({c["keep_id"], c["candidate_id"]}) for c in body["merge_candidates"]
    }
    assert frozenset({"Skill:TensorFlow", "Skill:Tensorflow"}) not in pairs


def test_apply_with_stale_node_returns_409(client):
    _write_graph_with_candidates("proj_stale")

    r = client.post(
        "/api/projects/proj_stale/graph/merge-candidates/apply",
        json={"keep_id": "Skill:TensorFlow", "candidate_id": "Skill:DoesNotExist"},
    )

    assert r.status_code == 409


def test_apply_missing_graph_returns_404(client):
    r = client.post(
        "/api/projects/no_project/graph/merge-candidates/apply",
        json={"keep_id": "Skill:A", "candidate_id": "Skill:B"},
    )

    assert r.status_code == 404
