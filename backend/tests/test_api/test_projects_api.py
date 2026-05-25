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
