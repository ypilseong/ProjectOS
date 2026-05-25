import pytest
from pathlib import Path


@pytest.fixture
def store(tmp_path, monkeypatch):
    from app.services.project_store import ProjectStore
    from app import config as config_module
    monkeypatch.setattr(config_module.config, "PROJECTS_DIR", str(tmp_path))
    return ProjectStore()


def test_create_project(store):
    p = store.create("Test Project", "A test")
    assert p.project_id
    assert p.name == "Test Project"
    assert p.description == "A test"


def test_get_project(store):
    p = store.create("My Graph")
    retrieved = store.get(p.project_id)
    assert retrieved.project_id == p.project_id
    assert retrieved.name == "My Graph"


def test_list_projects(store):
    store.create("Project A")
    store.create("Project B")
    all_projects = store.list_all()
    assert len(all_projects) == 2


def test_get_missing_project(store):
    assert store.get("doesnotexist") is None
