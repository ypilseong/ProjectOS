import json
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

from app.config import config

_REQUIRED_FIELDS = ("capture_reason", "current_focus", "reflection_intent")


def _captures_path(project_id: str) -> Path:
    return Path(config.PROJECTS_DIR) / project_id / "captures.json"


def is_complete_context(context: dict | None) -> bool:
    if not isinstance(context, dict):
        return False
    return all(str(context.get(field) or "").strip() for field in _REQUIRED_FIELDS)


def load_captures(project_id: str) -> dict[str, dict]:
    path = _captures_path(project_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_capture(project_id: str, source_file: str, context: dict) -> dict:
    if not is_complete_context(context):
        raise ValueError("capture context is incomplete")
    captures = load_captures(project_id)
    entry = {
        "capture_reason": str(context.get("capture_reason") or "").strip(),
        "current_focus": str(context.get("current_focus") or "").strip(),
        "reflection_intent": str(context.get("reflection_intent") or "").strip(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    captures[source_file] = entry
    path = _captures_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(captures, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry


def attach_capture_nodes(graph: nx.DiGraph, captures: dict[str, dict]) -> int:
    """Add one Capture meta node per source_file with DERIVED_FROM edges to its entities."""
    added = 0
    for source_file, ctx in captures.items():
        node_id = f"capture::{source_file}"
        focus = str(ctx.get("current_focus") or "").strip()
        if node_id not in graph:
            added += 1
        graph.add_node(
            node_id,
            type="Capture",
            meta=True,
            name=(focus[:60] or source_file),
            capture_reason=str(ctx.get("capture_reason") or ""),
            current_focus=focus,
            reflection_intent=str(ctx.get("reflection_intent") or ""),
            captured_at=str(ctx.get("captured_at") or ""),
            source_files=[source_file],
        )
        for nid, data in list(graph.nodes(data=True)):
            if nid == node_id or data.get("meta"):
                continue
            if source_file in (data.get("source_files") or []):
                graph.add_edge(node_id, nid, relation="DERIVED_FROM", meta=True)
    return added
