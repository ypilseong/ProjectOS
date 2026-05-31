import json
from pathlib import Path

from fastapi.testclient import TestClient


def test_get_settings_defaults_to_local():
    from app.main import app

    client = TestClient(app)
    r = client.get("/api/settings")

    assert r.status_code == 200
    assert r.json()["llm_backend"] == "local"
    assert r.json()["graph_build_mode"] == "chunk"
    assert r.json()["graph_extraction_backend"] == "local"


def test_post_settings_saves_backend_and_updates_runtime_config():
    from app.config import config
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/api/settings",
        json={
            "llm_backend": "claude_code",
            "graph_build_mode": "claude_task",
            "graph_extraction_backend": "claude_code",
            "claude_code_model": "claude-haiku-4-5",
            "chunk_size": 1800,
            "chunk_overlap": 150,
        },
    )

    assert r.status_code == 200
    assert r.json()["llm_backend"] == "claude_code"
    assert r.json()["graph_build_mode"] == "claude_task"
    assert r.json()["graph_extraction_backend"] == "claude_code"
    assert r.json()["claude_code_model"] == "claude-haiku-4-5"
    assert r.json()["chunk_size"] == 1800
    assert r.json()["chunk_overlap"] == 150
    assert config.LLM_BACKEND == "claude_code"
    assert config.GRAPH_BUILD_MODE == "claude_task"
    assert config.GRAPH_EXTRACTION_BACKEND == "claude_code"
    assert config.CLAUDE_CODE_MODEL == "claude-haiku-4-5"
    saved = json.loads(Path(config.SETTINGS_PATH).read_text())
    assert saved["graph_build_mode"] == "claude_task"


def test_get_settings_loads_saved_backend_and_updates_runtime_config():
    from app.config import config
    from app.main import app

    Path(config.SETTINGS_PATH).write_text(
        json.dumps({
            "llm_backend": "claude_code",
            "graph_build_mode": "claude_task",
            "graph_extraction_backend": "claude_code",
            "claude_code_model": "claude-haiku-4-5",
            "chunk_size": 1800,
            "chunk_overlap": 150,
        }),
        encoding="utf-8",
    )
    config.LLM_BACKEND = "local"
    config.GRAPH_BUILD_MODE = "chunk"

    client = TestClient(app)
    r = client.get("/api/settings")

    assert r.status_code == 200
    assert r.json()["llm_backend"] == "claude_code"
    assert r.json()["graph_build_mode"] == "claude_task"
    assert config.LLM_BACKEND == "claude_code"
    assert config.GRAPH_BUILD_MODE == "claude_task"


def test_settings_accepts_openai_alias_as_local():
    from app.config import config
    from app.main import app

    client = TestClient(app)
    r = client.post("/api/settings", json={"llm_backend": "openai"})

    assert r.status_code == 200
    assert r.json()["llm_backend"] == "local"
    assert config.LLM_BACKEND == "local"


def test_settings_normalizes_invalid_chunk_overlap():
    from app.config import config
    from app.main import app

    client = TestClient(app)
    r = client.post("/api/settings", json={"chunk_size": 1000, "chunk_overlap": 1000})

    assert r.status_code == 200
    assert r.json()["chunk_size"] == 1000
    assert r.json()["chunk_overlap"] == 100
    assert config.CHUNK_OVERLAP == 100
