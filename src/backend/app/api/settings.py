import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.config import config

router = APIRouter()

_VALID_BACKENDS = {"local", "claude_code"}
_VALID_GRAPH_BUILD_MODES = {"chunk", "claude_task"}
_BACKEND_ALIASES = {
    "openai": "local",
    "local": "local",
    "claude": "claude_code",
    "claude_code": "claude_code",
}
_GRAPH_BACKEND_ALIASES = {
    "openai": "local",
    "local": "local",
    "claude": "claude_code",
    "claude_code": "claude_code",
}


def _normalize_backend(value: str | None) -> str:
    normalized = _BACKEND_ALIASES.get((value or "").strip().lower())
    if normalized:
        return normalized
    return "local"


def _normalize_graph_backend(value: str | None) -> str:
    normalized = _GRAPH_BACKEND_ALIASES.get((value or "").strip().lower())
    if normalized:
        return normalized
    return "local"


def _normalize_graph_build_mode(value: str | None) -> str:
    mode = (value or "").strip().lower()
    return mode if mode in _VALID_GRAPH_BUILD_MODES else "chunk"


def _normalize_claude_model(value: str | None) -> str:
    return (value or "").strip()


def _normalize_positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _current_settings() -> dict:
    return {
        "llm_backend": _normalize_backend(config.LLM_BACKEND),
        "graph_build_mode": _normalize_graph_build_mode(config.GRAPH_BUILD_MODE),
        "graph_extraction_backend": _normalize_graph_backend(config.GRAPH_EXTRACTION_BACKEND),
        "claude_code_model": _normalize_claude_model(config.CLAUDE_CODE_MODEL),
        "chunk_size": int(config.CHUNK_SIZE),
        "chunk_overlap": int(config.CHUNK_OVERLAP),
    }


def _apply_settings(data: dict) -> dict:
    settings = {
        "llm_backend": _normalize_backend(data.get("llm_backend")),
        "graph_build_mode": _normalize_graph_build_mode(data.get("graph_build_mode")),
        "graph_extraction_backend": _normalize_graph_backend(data.get("graph_extraction_backend")),
        "claude_code_model": _normalize_claude_model(data.get("claude_code_model")),
        "chunk_size": _normalize_positive_int(data.get("chunk_size"), config.CHUNK_SIZE),
        "chunk_overlap": _normalize_positive_int(data.get("chunk_overlap"), config.CHUNK_OVERLAP),
    }
    if settings["chunk_overlap"] >= settings["chunk_size"]:
        settings["chunk_overlap"] = max(0, settings["chunk_size"] // 10)

    config.LLM_BACKEND = settings["llm_backend"]
    config.GRAPH_BUILD_MODE = settings["graph_build_mode"]
    config.GRAPH_EXTRACTION_BACKEND = settings["graph_extraction_backend"]
    config.CLAUDE_CODE_MODEL = settings["claude_code_model"]
    config.CHUNK_SIZE = settings["chunk_size"]
    config.CHUNK_OVERLAP = settings["chunk_overlap"]
    return settings


def _settings_path() -> Path:
    return Path(config.SETTINGS_PATH)


def _load_settings() -> dict:
    path = _settings_path()
    if not path.exists():
        return _current_settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Settings file is corrupted")
    return _apply_settings({**_current_settings(), **data})


@router.get("")
async def get_settings():
    return _load_settings()


@router.post("")
async def set_settings(body: dict):
    settings = _apply_settings({**_current_settings(), **body})
    if settings["llm_backend"] not in _VALID_BACKENDS:
        raise HTTPException(status_code=400, detail="Invalid LLM backend")
    if settings["graph_extraction_backend"] not in _VALID_BACKENDS:
        raise HTTPException(status_code=400, detail="Invalid graph extraction backend")
    if settings["graph_build_mode"] not in _VALID_GRAPH_BUILD_MODES:
        raise HTTPException(status_code=400, detail="Invalid graph build mode")

    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    return settings
