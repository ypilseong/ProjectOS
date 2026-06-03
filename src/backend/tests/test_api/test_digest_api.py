import json

import networkx as nx
from fastapi.testclient import TestClient

from app.config import config
from app.main import app


def _write_graph(proj_dir, nodes):
    g = nx.DiGraph()
    for nid, name, ntype in nodes:
        g.add_node(nid, name=name, type=ntype, source_files=["f.txt"])
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(g), ensure_ascii=False), encoding="utf-8"
    )


def test_post_digest_creates_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    _write_graph(tmp_path / "p1", [("n1", "Alpha", "Skill")])

    client = TestClient(app)
    resp = client.post("/api/projects/p1/digest")
    assert resp.status_code == 200
    body = resp.json()
    assert "markdown" in body
    assert body["new_node_count"] == 1
    assert (tmp_path / "vault" / "p1" / "Digests" / f"{body['date']}.md").exists()


def test_post_digest_404_when_no_graph(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    (tmp_path / "p1").mkdir()
    client = TestClient(app)
    resp = client.post("/api/projects/p1/digest")
    assert resp.status_code == 404


def test_list_digests_descending(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    d = tmp_path / "vault" / "p1" / "Digests"
    d.mkdir(parents=True)
    (d / "2026-06-01.md").write_text("a", encoding="utf-8")
    (d / "2026-06-03.md").write_text("b", encoding="utf-8")
    client = TestClient(app)
    resp = client.get("/api/projects/p1/digests")
    assert resp.status_code == 200
    assert resp.json() == {"dates": ["2026-06-03", "2026-06-01"]}


def test_list_digests_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    client = TestClient(app)
    resp = client.get("/api/projects/unknown/digests")
    assert resp.status_code == 200
    assert resp.json() == {"dates": []}


def test_get_digest_returns_markdown(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    d = tmp_path / "vault" / "p1" / "Digests"
    d.mkdir(parents=True)
    (d / "2026-06-03.md").write_text("# Digest 2026-06-03", encoding="utf-8")
    client = TestClient(app)
    resp = client.get("/api/projects/p1/digests/2026-06-03")
    assert resp.status_code == 200
    assert resp.json()["markdown"] == "# Digest 2026-06-03"


def test_get_digest_404(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    client = TestClient(app)
    resp = client.get("/api/projects/p1/digests/2099-01-01")
    assert resp.status_code == 404


def test_main_has_digest_service():
    import app.main as main_mod
    assert hasattr(main_mod, "DigestService")
