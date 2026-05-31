import os

# Provide a dummy API key so LLMClient can be instantiated during tests
# without hitting real credentials validation at module import time.
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

import pytest


@pytest.fixture(autouse=True)
def isolate_filesystem(tmp_path, monkeypatch):
    from app.config import config

    projects_dir = tmp_path / "projects"
    vault_dir = tmp_path / "vault"
    logs_dir = tmp_path / "logs"
    projects_dir.mkdir()
    vault_dir.mkdir()
    logs_dir.mkdir()

    monkeypatch.setattr(config, "PROJECTS_DIR", str(projects_dir))
    monkeypatch.setattr(config, "VAULT_DIR", str(vault_dir))
    monkeypatch.setattr(config, "LOG_DIR", str(logs_dir))
    monkeypatch.setattr(config, "USER_CONFIG_PATH", str(tmp_path / "user.json"))
    monkeypatch.setattr(config, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(config, "LLM_BACKEND", "local")
    monkeypatch.setattr(config, "GRAPH_EXTRACTION_BACKEND", "local")
    monkeypatch.setattr(config, "GRAPH_BUILD_MODE", "chunk")
    monkeypatch.setattr(config, "CLAUDE_CODE_MODEL", "")
    monkeypatch.setattr(config, "CLAUDE_TASKS_DIR", str(tmp_path / "claude_tasks"))
    monkeypatch.setattr(config, "CLAUDE_TASK_BARE", False)
    monkeypatch.setattr(config, "CLAUDE_TASK_TIMEOUT", 600.0)
    monkeypatch.setattr(config, "CHUNK_SIZE", 500)
    monkeypatch.setattr(config, "CHUNK_OVERLAP", 50)

    yield
