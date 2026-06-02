from fastapi.testclient import TestClient

from app.main import app


def test_get_skills_returns_catalog():
    client = TestClient(app)
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    body = resp.json()
    assert "skills" in body
    assert len(body["skills"]) >= 6
    names = {s["name"] for s in body["skills"]}
    assert "query_career_graph" in names
    for s in body["skills"]:
        assert {"name", "role", "cost_profile", "execution_mode"} <= set(s.keys())
