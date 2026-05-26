import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_get_user_returns_404_when_not_set(client):
    r = client.get("/api/user")
    assert r.status_code == 404


def test_post_user_saves_config(client):
    r = client.post("/api/user", json={"name": "양필성", "display_name": "Pilseong Yang"})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "양필성"
    assert data["display_name"] == "Pilseong Yang"


def test_get_user_returns_saved_config(client):
    client.post("/api/user", json={"name": "양필성", "display_name": "Pilseong Yang"})
    r = client.get("/api/user")
    assert r.status_code == 200
    assert r.json()["name"] == "양필성"


def test_post_user_display_name_defaults_to_name(client):
    r = client.post("/api/user", json={"name": "양필성"})
    assert r.json()["display_name"] == "양필성"
