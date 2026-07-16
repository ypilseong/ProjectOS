from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import config
from app.utils.logger import project_log_dir


_TEXT_LIMIT = 1200
_MAX_DEPTH = 6
_LARGE_PAYLOAD_KEYS = {"content_base64", "content_text", "body", "raw", "bytes"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _full_payloads_enabled() -> bool:
    return os.environ.get("PROJECTOS_MCP_LOG_FULL_PAYLOADS", "").lower() in {"1", "true", "yes", "on"}


def _compact(value: Any, *, depth: int = 0) -> Any:
    if _full_payloads_enabled():
        return value
    if depth > _MAX_DEPTH:
        return "<max depth reached>"
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for key, item in value.items():
            if key in _LARGE_PAYLOAD_KEYS and isinstance(item, str):
                compacted[key] = {
                    "omitted": True,
                    "chars": len(item),
                    "preview": item[:160],
                }
            else:
                compacted[key] = _compact(item, depth=depth + 1)
        return compacted
    if isinstance(value, list):
        return [_compact(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str) and len(value) > _TEXT_LIMIT:
        return {
            "truncated": True,
            "chars": len(value),
            "preview": value[:_TEXT_LIMIT],
        }
    return value


def _extract_project_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None

    params = payload.get("params")
    if isinstance(params, dict):
        arguments = params.get("arguments")
        if isinstance(arguments, dict) and arguments.get("project_id"):
            return str(arguments["project_id"])
        if params.get("project_id"):
            return str(params["project_id"])

    result = payload.get("result")
    if isinstance(result, dict):
        structured = result.get("structuredContent")
        if isinstance(structured, dict) and structured.get("project_id"):
            return str(structured["project_id"])
        if result.get("project_id"):
            return str(result["project_id"])

    structured = payload.get("structuredContent")
    if isinstance(structured, dict) and structured.get("project_id"):
        return str(structured["project_id"])
    if payload.get("project_id"):
        return str(payload["project_id"])
    return None


def _tool_name(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    params = payload.get("params")
    if isinstance(params, dict) and params.get("name"):
        return str(params["name"])
    return None


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def record_mcp_exchange(
    *,
    source: str,
    direction: str,
    payload: dict[str, Any] | None,
    error: str | None = None,
) -> None:
    """Persist compact MCP JSON-RPC traffic for backend/Claude Desktop debugging."""

    try:
        record: dict[str, Any] = {
            "timestamp": _now_iso(),
            "source": source,
            "direction": direction,
            "project_id": _extract_project_id(payload),
            "request_id": payload.get("id") if isinstance(payload, dict) else None,
            "method": payload.get("method") if isinstance(payload, dict) else None,
            "tool": _tool_name(payload),
            "payload": _compact(payload),
        }
        if error:
            record["error"] = error

        log_dir = Path(config.LOG_DIR)
        _append_jsonl(log_dir / "mcp.jsonl", record)

        project_id = record.get("project_id")
        if project_id:
            _append_jsonl(project_log_dir(str(project_id)) / "mcp.jsonl", record)
    except Exception:
        return
