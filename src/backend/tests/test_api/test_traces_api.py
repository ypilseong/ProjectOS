from fastapi.testclient import TestClient

from app.config import config
from app.main import app
from app.utils.trace import record_trace


def test_get_traces_returns_records(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    record_trace("p1", "graph_build", backend="local", nodes=3, edges=2)
    client = TestClient(app)
    resp = client.get("/api/projects/p1/traces")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["traces"]) == 1
    assert body["traces"][0]["operation"] == "graph_build"


def test_get_traces_empty_for_unknown_project(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    client = TestClient(app)
    resp = client.get("/api/projects/unknown/traces")
    assert resp.status_code == 200
    assert resp.json() == {"traces": []}
