import json
from pathlib import Path
from typing import Any

import networkx as nx

from app.config import config
from app.models.graph import TextChunk


def load_simulation_result(project_id: str, run_id: str | None = None) -> dict[str, Any]:
    """Load the latest simulation result, or a specific archived run."""
    project_dir = Path(config.PROJECTS_DIR) / project_id
    latest_path = project_dir / "simulation.json"

    if run_id:
        _validate_run_id(run_id)
        if latest_path.exists():
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            if str(latest.get("run_id") or "") == run_id:
                return latest
        archived_path = project_dir / "simulations" / f"{run_id}.json"
        if not archived_path.exists():
            raise ValueError("Simulation run not found")
        return json.loads(archived_path.read_text(encoding="utf-8"))

    if not latest_path.exists():
        raise ValueError("Simulation not run yet")
    return json.loads(latest_path.read_text(encoding="utf-8"))


def adapt_simulation_summary(
    simulation: dict[str, Any],
    project_id: str | None = None,
    *,
    include_workflow: bool = True,
    max_steps: int = 12,
) -> dict[str, Any]:
    schema_version = _schema_version(simulation)
    workflow_steps = _workflow_steps(simulation, schema_version) if include_workflow else []
    workflow_steps = workflow_steps[:max(0, max_steps)]
    counts = _counts(simulation, schema_version)
    payload = {
        "kind": "simulation_summary",
        "read_only": True,
        "project_id": project_id or simulation.get("project_id") or "",
        "run_id": simulation.get("run_id"),
        "schema_version": schema_version,
        "status": simulation.get("status") or ("completed" if schema_version == "legacy" else ""),
        "query": simulation.get("query") or "",
        "started_at": simulation.get("started_at") or simulation.get("generated_at"),
        "completed_at": simulation.get("completed_at") or simulation.get("generated_at"),
        "summary": _summary(simulation, schema_version),
        "workflow_steps": workflow_steps,
        "counts": counts,
        "available_views": ["graph_delta", "report_sections", "event_log", "evidence"],
    }
    return payload


def adapt_simulation_graph_delta(
    simulation: dict[str, Any],
    *,
    project_id: str | None = None,
    status: str | None = None,
    item_type: str = "all",
    max_items: int = 20,
    sort: str = "confidence_asc",
) -> dict[str, Any]:
    schema_version = _schema_version(simulation)
    all_items = _delta_items(simulation, schema_version)
    item_filter = _item_type_filter(item_type)
    filtered = [
        item for item in all_items
        if (not status or item.get("status") == status)
        and (item_filter == "all" or item.get("item_type") == item_filter)
    ]
    filtered = _sort_delta_items(filtered, sort)
    max_items = max(0, max_items)
    returned = filtered[:max_items]
    payload = {
        "kind": "simulation_graph_delta",
        "read_only": True,
        "project_id": project_id or simulation.get("project_id") or "",
        "run_id": simulation.get("run_id"),
        "schema_version": schema_version,
        "filters": {
            "status": status,
            "item_type": item_type,
            "max_items": max_items,
            "sort": sort,
        },
        "summary": _delta_summary(all_items, returned),
        "items": returned,
        "truncated": len(filtered) > len(returned),
    }
    return payload


def adapt_simulation_report_section(
    simulation: dict[str, Any],
    *,
    project_id: str | None = None,
    section_id: str | None = None,
    kind: str | None = "executive_summary",
    include_body: bool = True,
) -> dict[str, Any]:
    schema_version = _schema_version(simulation)
    sections = _report_sections(simulation, schema_version)
    selected = _select_section(sections, section_id, kind)
    if not selected:
        raise ValueError("Simulation report section not found")
    selected = dict(selected)
    if not include_body:
        selected.pop("body", None)
    payload = {
        "kind": "simulation_report_section",
        "read_only": True,
        "project_id": project_id or simulation.get("project_id") or "",
        "run_id": simulation.get("run_id"),
        "schema_version": schema_version,
        "selected": selected,
        "available_sections": [
            {
                "section_id": str(section.get("section_id") or ""),
                "title": str(section.get("title") or ""),
                "kind": str(section.get("kind") or ""),
                "summary": str(section.get("summary") or ""),
            }
            for section in sections
        ],
    }
    return payload


def adapt_simulation_event_log(
    simulation: dict[str, Any],
    *,
    project_id: str | None = None,
    step_id: str | None = None,
    event_type: str | None = None,
    max_events: int = 50,
) -> dict[str, Any]:
    schema_version = _schema_version(simulation)
    events = _event_log(simulation, schema_version)
    filtered = [
        event for event in events
        if (not step_id or event.get("step_id") == step_id)
        and (not event_type or event.get("type") == event_type)
    ]
    max_events = max(0, max_events)
    returned = filtered[:max_events]
    return {
        "kind": "simulation_event_log",
        "read_only": True,
        "project_id": project_id or simulation.get("project_id") or "",
        "run_id": simulation.get("run_id"),
        "schema_version": schema_version,
        "filters": {
            "step_id": step_id,
            "event_type": event_type,
            "max_events": max_events,
        },
        "events": returned,
        "truncated": len(filtered) > len(returned),
    }


def resolve_simulation_evidence(
    project_id: str,
    simulation: dict[str, Any],
    evidence_refs: list[str],
    *,
    max_chars_per_ref: int = 1200,
) -> dict[str, Any]:
    chunks = _load_chunks(project_id)
    graph = _load_graph(project_id)
    events = {event.get("event_id"): event for event in _event_log(simulation, _schema_version(simulation))}
    sections = {
        section.get("section_id"): section
        for section in _report_sections(simulation, _schema_version(simulation))
    }

    refs = []
    unresolved = []
    for ref in evidence_refs:
        item = _resolve_ref(
            str(ref),
            chunks=chunks,
            graph=graph,
            events=events,
            sections=sections,
            max_chars=max(0, max_chars_per_ref),
        )
        refs.append(item)
        if not item.get("resolved"):
            unresolved.append(str(ref))

    return {
        "kind": "simulation_evidence",
        "read_only": True,
        "project_id": project_id,
        "run_id": simulation.get("run_id"),
        "schema_version": _schema_version(simulation),
        "refs": refs,
        "unresolved_refs": unresolved,
    }


def _schema_version(simulation: dict[str, Any]) -> str:
    return "2.0" if simulation.get("schema_version") == "2.0" else "legacy"


def _validate_run_id(run_id: str) -> None:
    if Path(run_id).name != run_id or "/" in run_id or "\\" in run_id:
        raise ValueError("Simulation run not found")


def _item_type_filter(item_type: str) -> str:
    if item_type == "nodes":
        return "node"
    if item_type == "edges":
        return "edge"
    if item_type in {"node", "edge"}:
        return item_type
    return "all"


def _summary(simulation: dict[str, Any], schema_version: str) -> dict[str, Any]:
    if schema_version == "2.0":
        return dict(simulation.get("summary") or {})
    report = simulation.get("report") or {}
    graph_delta = _delta_items(simulation, schema_version)
    return {
        "title": str(report.get("title") or "Simulation Report"),
        "answer": str(report.get("answer") or ""),
        "graph_delta_count": len(graph_delta),
        "report_section_count": len(_report_sections(simulation, schema_version)),
        "low_confidence_count": sum(
            1 for item in graph_delta
            if item.get("confidence") is not None and item["confidence"] < 0.6
        ),
    }


def _workflow_steps(simulation: dict[str, Any], schema_version: str) -> list[dict[str, Any]]:
    if schema_version == "2.0":
        return [
            {
                "id": step.get("id"),
                "label": step.get("label"),
                "status": step.get("status"),
                "summary": step.get("summary"),
            }
            for step in simulation.get("workflow_steps", []) or []
        ]
    return [{
        "id": "legacy_result_loaded",
        "label": "Legacy Result Loaded",
        "status": "completed",
        "summary": "Loaded a legacy simulation result.",
    }]


def _counts(simulation: dict[str, Any], schema_version: str) -> dict[str, int]:
    graph_delta = simulation.get("graph_delta") if schema_version == "2.0" else {}
    return {
        "personas": len(simulation.get("personas", []) or []),
        "debate_turns": len((simulation.get("debate") or {}).get("turns", []) or [])
        if schema_version == "2.0" else len(simulation.get("timeline", []) or []),
        "report_sections": len(_report_sections(simulation, schema_version)),
        "graph_delta_nodes": len((graph_delta or {}).get("nodes", []) or [])
        if schema_version == "2.0" else len((simulation.get("graph_enhancements") or {}).get("nodes", []) or []),
        "graph_delta_edges": len((graph_delta or {}).get("edges", []) or [])
        if schema_version == "2.0" else len((simulation.get("graph_enhancements") or {}).get("edges", []) or []),
        "events": len(_event_log(simulation, schema_version)),
    }


def _delta_items(simulation: dict[str, Any], schema_version: str) -> list[dict[str, Any]]:
    if schema_version == "2.0":
        delta = simulation.get("graph_delta") or {}
        nodes = [_normalize_node_delta(item) for item in delta.get("nodes", []) or []]
        edges = [_normalize_edge_delta(item) for item in delta.get("edges", []) or []]
        return nodes + edges

    enhancements = simulation.get("graph_enhancements") or {}
    nodes = []
    for idx, node in enumerate(enhancements.get("nodes", []) or []):
        ntype = str(node.get("type") or "")
        name = str(node.get("name") or "")
        nodes.append(_normalize_node_delta({
            "delta_id": f"legacy_node_{idx + 1:03d}",
            "operation": "add",
            "node_id": f"{ntype}:{name}" if ntype and name else "",
            "type": ntype,
            "name": name,
            "description": str(node.get("description") or ""),
            "confidence": _numeric_or_none(node.get("confidence")),
            "evidence_refs": _evidence_refs(node.get("evidence_refs") or node.get("evidence")),
            "status": "proposed",
        }))
    edges = []
    for idx, edge in enumerate(enhancements.get("edges", []) or []):
        source_type = str(edge.get("source_type") or "")
        source_name = str(edge.get("source_name") or "")
        target_type = str(edge.get("target_type") or "")
        target_name = str(edge.get("target_name") or "")
        edges.append(_normalize_edge_delta({
            "delta_id": f"legacy_edge_{idx + 1:03d}",
            "operation": "add",
            "source": {
                "type": source_type,
                "name": source_name,
                "node_id": f"{source_type}:{source_name}" if source_type and source_name else "",
            },
            "target": {
                "type": target_type,
                "name": target_name,
                "node_id": f"{target_type}:{target_name}" if target_type and target_name else "",
            },
            "relation": str(edge.get("relation") or "RELATED_TO"),
            "confidence": _numeric_or_none(edge.get("confidence")),
            "evidence_refs": _evidence_refs(edge.get("evidence_refs") or edge.get("evidence")),
            "status": "proposed",
        }))
    return nodes + edges


def _normalize_node_delta(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "delta_id": str(item.get("delta_id") or ""),
        "item_type": "node",
        "operation": str(item.get("operation") or ""),
        "label": str(item.get("name") or item.get("node_id") or ""),
        "node_id": str(item.get("node_id") or ""),
        "type": str(item.get("type") or ""),
        "name": str(item.get("name") or ""),
        "description": str(item.get("description") or ""),
        "confidence": _numeric_or_none(item.get("confidence")),
        "status": str(item.get("status") or "proposed"),
        "status_reason": str(item.get("status_reason") or ""),
        "evidence_refs": _evidence_refs(item.get("evidence_refs")),
        "source_event_ids": list(item.get("source_event_ids") or []),
        "source_report_section_ids": list(item.get("source_report_section_ids") or []),
    }


def _normalize_edge_delta(item: dict[str, Any]) -> dict[str, Any]:
    source = dict(item.get("source") or {})
    target = dict(item.get("target") or {})
    relation = str(item.get("relation") or "RELATED_TO")
    label = (
        f"{source.get('name') or item.get('source_name') or source.get('node_id') or item.get('source_id') or ''} "
        f"-{relation}-> "
        f"{target.get('name') or item.get('target_name') or target.get('node_id') or item.get('target_id') or ''}"
    ).strip()
    return {
        "delta_id": str(item.get("delta_id") or ""),
        "item_type": "edge",
        "operation": str(item.get("operation") or ""),
        "label": label,
        "source": source,
        "target": target,
        "source_id": str(item.get("source_id") or source.get("node_id") or ""),
        "target_id": str(item.get("target_id") or target.get("node_id") or ""),
        "source_type": str(item.get("source_type") or source.get("type") or ""),
        "source_name": str(item.get("source_name") or source.get("name") or ""),
        "target_type": str(item.get("target_type") or target.get("type") or ""),
        "target_name": str(item.get("target_name") or target.get("name") or ""),
        "relation": relation,
        "confidence": _numeric_or_none(item.get("confidence")),
        "status": str(item.get("status") or "proposed"),
        "status_reason": str(item.get("status_reason") or ""),
        "evidence_refs": _evidence_refs(item.get("evidence_refs")),
        "source_event_ids": list(item.get("source_event_ids") or []),
        "source_report_section_ids": list(item.get("source_report_section_ids") or []),
    }


def _sort_delta_items(items: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    if sort == "confidence_desc":
        return sorted(items, key=lambda item: (_confidence_sort(item, reverse=True), item["delta_id"]))
    if sort == "status":
        return sorted(items, key=lambda item: (item.get("status", ""), item["delta_id"]))
    if sort == "operation":
        return sorted(items, key=lambda item: (item.get("operation", ""), item["delta_id"]))
    return sorted(items, key=lambda item: (_confidence_sort(item), item["delta_id"]))


def _confidence_sort(item: dict[str, Any], reverse: bool = False) -> float:
    confidence = item.get("confidence")
    if confidence is None:
        return float("-inf") if reverse else float("inf")
    return -confidence if reverse else confidence


def _delta_summary(all_items: list[dict[str, Any]], returned: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(all_items),
        "returned": len(returned),
        "proposed": sum(1 for item in returned if item.get("status") == "proposed"),
        "applied": sum(1 for item in returned if item.get("status") == "applied"),
        "skipped": sum(1 for item in returned if item.get("status") == "skipped"),
        "rejected": sum(1 for item in returned if item.get("status") == "rejected"),
        "low_confidence": sum(
            1 for item in returned
            if item.get("confidence") is not None and item["confidence"] < 0.6
        ),
    }


def _report_sections(simulation: dict[str, Any], schema_version: str) -> list[dict[str, Any]]:
    if schema_version == "2.0":
        return list(simulation.get("report_sections", []) or [])

    sections = []
    report = simulation.get("report") or {}
    if report.get("answer") or report.get("title"):
        sections.append({
            "section_id": "legacy_report_answer",
            "title": str(report.get("title") or "Simulation Report"),
            "kind": "executive_summary",
            "summary": str(report.get("answer") or ""),
            "body": str(report.get("answer") or ""),
            "evidence_refs": _evidence_refs(report.get("evidence")),
            "uncertainty": [],
            "related_delta_ids": [],
            "source_persona_ids": [],
        })
    recommendations = [str(value) for value in report.get("recommendations", []) or [] if value]
    if recommendations:
        sections.append({
            "section_id": "legacy_recommendations",
            "title": "Recommendations",
            "kind": "recommendations",
            "summary": recommendations[0],
            "body": "\n".join(f"- {item}" for item in recommendations),
            "items": recommendations,
            "evidence_refs": _evidence_refs(report.get("evidence")),
            "uncertainty": [],
            "related_delta_ids": [],
            "source_persona_ids": [],
        })
    cv = simulation.get("cv_improvements") or {}
    if cv:
        sections.append({
            "section_id": "legacy_cv_improvements",
            "title": "CV Improvements",
            "kind": "cv_improvements",
            "summary": str(cv.get("summary") or ""),
            "body": str(cv.get("improved_draft") or ""),
            "items": [str(value) for value in cv.get("bullets", []) or [] if value],
            "evidence_refs": [],
            "uncertainty": [],
            "related_delta_ids": [],
            "source_persona_ids": [],
        })
    return sections


def _select_section(
    sections: list[dict[str, Any]],
    section_id: str | None,
    kind: str | None,
) -> dict[str, Any] | None:
    if section_id:
        return next((section for section in sections if section.get("section_id") == section_id), None)
    if kind:
        return next((section for section in sections if section.get("kind") == kind), None)
    return next((section for section in sections if section.get("kind") == "executive_summary"), None)


def _event_log(simulation: dict[str, Any], schema_version: str) -> list[dict[str, Any]]:
    if schema_version == "2.0" and simulation.get("event_log"):
        return list(simulation.get("event_log") or [])
    timeline = simulation.get("timeline") or (simulation.get("legacy") or {}).get("timeline") or []
    return [
        {
            "event_id": f"legacy_turn_{idx + 1:03d}",
            "step_id": "debate",
            "type": "debate_turn",
            "timestamp": simulation.get("generated_at") or simulation.get("completed_at"),
            "summary": str(item.get("observation") or item.get("claim") or item.get("proposal") or ""),
            "payload_ref": {"kind": "timeline", "ids": [f"legacy_turn_{idx + 1:03d}"]},
        }
        for idx, item in enumerate(timeline)
    ]


def _load_chunks(project_id: str) -> list[TextChunk]:
    path = Path(config.PROJECTS_DIR) / project_id / "chunks.json"
    if not path.exists():
        return []
    return [TextChunk(**item) for item in json.loads(path.read_text(encoding="utf-8"))]


def _load_graph(project_id: str) -> nx.DiGraph:
    path = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    if not path.exists():
        return nx.DiGraph()
    data = json.loads(path.read_text(encoding="utf-8"))
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    return nx.node_link_graph(data)


def _resolve_ref(
    ref: str,
    *,
    chunks: list[TextChunk],
    graph: nx.DiGraph,
    events: dict[str, dict[str, Any]],
    sections: dict[str, dict[str, Any]],
    max_chars: int,
) -> dict[str, Any]:
    if ref.startswith("chunk:"):
        body = ref[len("chunk:"):]
        source_file, sep, chunk_id = body.partition("#")
        if sep:
            for chunk in chunks:
                if chunk.source_file == source_file and chunk.chunk_id == chunk_id:
                    text, truncated = _truncate(chunk.text, max_chars)
                    return {
                        "ref": ref,
                        "resolved": True,
                        "kind": "chunk",
                        "source_file": chunk.source_file,
                        "chunk_id": chunk.chunk_id,
                        "page_num": chunk.page_num,
                        "char_offset": chunk.char_offset,
                        "text": text,
                        "truncated": truncated,
                    }
    elif ref.startswith("node:"):
        node_id = ref[len("node:"):]
        if node_id in graph:
            data = graph.nodes[node_id]
            return {
                "ref": ref,
                "resolved": True,
                "kind": "node",
                "node_id": node_id,
                "type": data.get("type"),
                "name": data.get("name"),
                "description": data.get("description", ""),
                "source_files": list(data.get("source_files") or []),
                "evidence": list(data.get("evidence") or []),
            }
    elif ref.startswith("edge:"):
        parsed = _parse_edge_ref(ref)
        if parsed:
            source_id, target_id, relation = parsed
            if graph.has_edge(source_id, target_id):
                data = graph.edges[source_id, target_id]
                if not relation or str(data.get("relation") or "") == relation:
                    return {
                        "ref": ref,
                        "resolved": True,
                        "kind": "edge",
                        "source_id": source_id,
                        "target_id": target_id,
                        "relation": data.get("relation"),
                        "confidence": data.get("confidence"),
                        "evidence": data.get("evidence"),
                    }
    elif ref.startswith("event:"):
        event_id = ref[len("event:"):]
        if event_id in events:
            return {"ref": ref, "resolved": True, "kind": "event", "event": events[event_id]}
    elif ref.startswith("report:"):
        section_id = ref[len("report:"):]
        if section_id in sections:
            section = dict(sections[section_id])
            if "body" in section:
                section["body"], section["truncated"] = _truncate(str(section["body"]), max_chars)
            return {"ref": ref, "resolved": True, "kind": "report", "section": section}

    return {"ref": ref, "resolved": False, "kind": "unknown"}


def _parse_edge_ref(ref: str) -> tuple[str, str, str] | None:
    body = ref[len("edge:"):]
    source_id, sep, tail = body.partition("->")
    if not sep:
        return None
    target_id, sep, relation = tail.rpartition(":")
    if not sep:
        target_id, relation = tail, ""
    return source_id, target_id, relation


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _evidence_refs(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _numeric_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
