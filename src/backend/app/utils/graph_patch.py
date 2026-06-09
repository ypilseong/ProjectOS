import json
from pathlib import Path
from typing import Any

import networkx as nx

from app.agents.obsidian_writer_agent import ObsidianWriterAgent
from app.config import config
from app.utils.entity_normalization import clean_entity_name
from app.utils.entity_validation import is_valid_entity, normalize_entity_type


PATCH_SOURCE = "manual_review"


def apply_project_graph_patch(project_id: str, patch: dict[str, Any]) -> dict:
    project_dir = Path(config.PROJECTS_DIR) / project_id
    graph_path = project_dir / "graph.json"
    if not graph_path.exists():
        raise ValueError("Graph not built yet")

    graph = _load_graph(graph_path)
    before = {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges()}
    changes = {
        "nodes_added": 0,
        "nodes_updated": 0,
        "nodes_deleted": 0,
        "edges_added": 0,
        "edges_deleted": 0,
    }

    for item in patch.get("nodes_add", []) or []:
        if _add_node(graph, item):
            changes["nodes_added"] += 1

    for item in patch.get("nodes_update", []) or []:
        if _update_node(graph, item):
            changes["nodes_updated"] += 1

    for item in patch.get("edges_add", []) or []:
        if _add_edge(graph, item):
            changes["edges_added"] += 1

    for item in patch.get("edges_delete", []) or []:
        if _delete_edge(graph, item):
            changes["edges_deleted"] += 1

    for item in patch.get("nodes_delete", []) or []:
        if _delete_node(graph, item):
            changes["nodes_deleted"] += 1

    _save_graph(graph, graph_path)
    ObsidianWriterAgent().run(
        graph,
        vault_path=str(Path(config.VAULT_DIR) / project_id),
        delta=False,
        project_id=project_id,
    )

    after = {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges()}
    return {"project_id": project_id, "before": before, "after": after, "changes": changes}


def _load_graph(path: Path) -> nx.DiGraph:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    return nx.node_link_graph(data)


def _save_graph(graph: nx.DiGraph, path: Path) -> None:
    data = nx.node_link_data(graph)
    if "edges" in data and "links" not in data:
        data["links"] = data.pop("edges")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _node_id(entity_type: str, name: str) -> str:
    return f"{entity_type}:{name}"


def _normalized_node_parts(item: dict[str, Any]) -> tuple[str, str]:
    entity_type = normalize_entity_type(str(item.get("type") or ""))
    name = clean_entity_name(str(item.get("name") or ""))
    if not is_valid_entity(entity_type, name):
        raise ValueError(f"Invalid entity: {entity_type}:{name}")
    return entity_type, name


def _resolve_node(graph: nx.DiGraph, item: dict[str, Any], prefix: str = "") -> str | None:
    direct_id = str(item.get(f"{prefix}id") or item.get(f"{prefix}node_id") or "").strip()
    if not direct_id and prefix == "source_":
        direct_id = str(item.get("source") or "").strip()
    if not direct_id and prefix == "target_":
        direct_id = str(item.get("target") or "").strip()
    if not direct_id and not prefix:
        direct_id = str(item.get("id") or item.get("node_id") or "").strip()
    if direct_id:
        if direct_id in graph:
            return direct_id
        by_name = _resolve_unique_name(graph, direct_id)
        if by_name:
            return by_name

    entity_type = normalize_entity_type(str(item.get(f"{prefix}type") or ""))
    name = clean_entity_name(str(item.get(f"{prefix}name") or ""))
    if not name and prefix == "source_":
        name = clean_entity_name(str(item.get("source") or ""))
    if not name and prefix == "target_":
        name = clean_entity_name(str(item.get("target") or ""))
    if entity_type and name:
        candidate = _node_id(entity_type, name)
        if candidate in graph:
            return candidate
        lowered = name.lower()
        for node_id, data in graph.nodes(data=True):
            if data.get("type") == entity_type and str(data.get("name", "")).lower() == lowered:
                return node_id
    if name:
        return _resolve_unique_name(graph, name)
    return None


def _resolve_unique_name(graph: nx.DiGraph, name_or_id: str) -> str | None:
    cleaned = clean_entity_name(name_or_id)
    if not cleaned:
        return None
    lowered = cleaned.lower()
    matches = [
        node_id
        for node_id, data in graph.nodes(data=True)
        if str(data.get("name", "")).lower() == lowered
    ]
    return matches[0] if len(matches) == 1 else None


def _add_node(graph: nx.DiGraph, item: dict[str, Any]) -> bool:
    entity_type, name = _normalized_node_parts(item)
    node_id = str(item.get("id") or _node_id(entity_type, name))
    if node_id in graph:
        return False
    graph.add_node(
        node_id,
        type=entity_type,
        name=name,
        description=str(item.get("description") or ""),
        source_files=list(item.get("source_files") or [PATCH_SOURCE]),
        source_chunk_ids=list(item.get("source_chunk_ids") or []),
        attributes=dict(item.get("attributes") or {}),
    )
    return True


def _update_node(graph: nx.DiGraph, item: dict[str, Any]) -> bool:
    node_id = _resolve_node(graph, item)
    if not node_id:
        raise ValueError("Node to update was not found")

    data = graph.nodes[node_id]
    updates = dict(item.get("set") or {})
    for key in ("type", "name", "description", "source_files", "source_chunk_ids", "attributes"):
        if key in item:
            updates[key] = item[key]

    new_type = normalize_entity_type(str(updates.get("type", data.get("type", ""))))
    new_name = clean_entity_name(str(updates.get("name", data.get("name", ""))))
    if "type" in updates or "name" in updates:
        if not is_valid_entity(new_type, new_name):
            raise ValueError(f"Invalid entity: {new_type}:{new_name}")

    for key, value in updates.items():
        if key in {"id", "node_id"}:
            continue
        if key == "type":
            data[key] = new_type
        elif key == "name":
            data[key] = new_name
        elif key == "attributes":
            merged = dict(data.get("attributes") or {})
            merged.update(dict(value or {}))
            data[key] = merged
        elif key in {"source_files", "source_chunk_ids"}:
            data[key] = list(value or [])
        else:
            data[key] = value

    desired_id = _node_id(str(data.get("type")), str(data.get("name")))
    if desired_id != node_id:
        if desired_id in graph:
            raise ValueError(f"Cannot rename node to existing id: {desired_id}")
        nx.relabel_nodes(graph, {node_id: desired_id}, copy=False)
    return True


def _delete_node(graph: nx.DiGraph, item: dict[str, Any]) -> bool:
    node_id = _resolve_node(graph, item)
    if not node_id:
        return False
    graph.remove_node(node_id)
    return True


def _add_edge(graph: nx.DiGraph, item: dict[str, Any]) -> bool:
    source_id = _resolve_node(graph, item, "source_")
    target_id = _resolve_node(graph, item, "target_")
    if not source_id or not target_id:
        raise ValueError("Edge endpoint was not found")
    relation = str(item.get("relation") or "").strip().upper()
    if not relation:
        raise ValueError("relation is required")
    if graph.has_edge(source_id, target_id):
        graph.edges[source_id, target_id].update({
            "relation": relation,
            "confidence": float(item.get("confidence") or graph.edges[source_id, target_id].get("confidence", 1.0)),
        })
        if item.get("evidence"):
            graph.edges[source_id, target_id]["evidence"] = str(item["evidence"])
        return False
    graph.add_edge(
        source_id,
        target_id,
        relation=relation,
        confidence=float(item.get("confidence") or 1.0),
        source_chunk_id=str(item.get("source_chunk_id") or PATCH_SOURCE),
        evidence=str(item.get("evidence") or ""),
    )
    return True


def _delete_edge(graph: nx.DiGraph, item: dict[str, Any]) -> bool:
    source_id = _resolve_node(graph, item, "source_")
    target_id = _resolve_node(graph, item, "target_")
    if not source_id or not target_id or not graph.has_edge(source_id, target_id):
        return False
    relation = str(item.get("relation") or "").strip().upper()
    if relation and graph.edges[source_id, target_id].get("relation") != relation:
        return False
    graph.remove_edge(source_id, target_id)
    return True
