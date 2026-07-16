from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph

from app.config import config


class SimulationDeltaError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _project_dir(project_id: str) -> Path:
    return Path(config.PROJECTS_DIR) / project_id


def _load_json(path: Path, missing_detail: str) -> dict[str, Any]:
    if not path.exists():
        raise SimulationDeltaError(404, missing_detail)
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_graph(proj_dir: Path) -> nx.DiGraph:
    data = _load_json(proj_dir / "graph.json", "Graph not built yet")
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    return nx.node_link_graph(data)


def _save_graph(proj_dir: Path, graph: nx.DiGraph) -> None:
    out = json_graph.node_link_data(graph)
    if "edges" in out and "links" not in out:
        out["links"] = out.pop("edges")
    _save_json(proj_dir / "graph.json", out)


def _find_delta(simulation: dict[str, Any], delta_id: str) -> tuple[str, dict[str, Any]]:
    graph_delta = simulation.get("graph_delta") or {}
    for kind in ("nodes", "edges"):
        for item in graph_delta.get(kind, []) or []:
            if item.get("delta_id") == delta_id:
                return kind, item
    raise SimulationDeltaError(404, f"Delta {delta_id} not found")


def _refresh_summary(simulation: dict[str, Any]) -> None:
    graph_delta = simulation.get("graph_delta") or {}
    nodes = graph_delta.get("nodes", []) or []
    edges = graph_delta.get("edges", []) or []
    graph_delta["summary"] = {
        "proposed_nodes": len(nodes),
        "proposed_edges": len(edges),
        "applied_nodes": sum(1 for i in nodes if i.get("status") == "applied"),
        "applied_edges": sum(1 for i in edges if i.get("status") == "applied"),
        "skipped": sum(1 for i in [*nodes, *edges] if i.get("status") == "skipped"),
    }


def _persist_simulation(proj_dir: Path, simulation: dict[str, Any]) -> None:
    _save_json(proj_dir / "simulation.json", simulation)
    run_id = simulation.get("run_id")
    if run_id:
        archive = proj_dir / "simulations" / f"{run_id}.json"
        if archive.parent.exists():
            _save_json(archive, simulation)


def _delta_to_enhancements(kind: str, item: dict[str, Any]) -> dict[str, Any]:
    evidence = " / ".join(item.get("evidence_refs") or [])
    if kind == "nodes":
        return {
            "nodes": [{
                "type": item.get("type"),
                "name": item.get("name"),
                "description": item.get("description"),
                "confidence": item.get("confidence"),
                "evidence": evidence,
                "duplicate_of": item.get("duplicate_of") or "",
            }],
            "edges": [],
        }
    return {
        "nodes": [],
        "edges": [{
            "source_type": item.get("source_type"),
            "source_name": item.get("source_name"),
            "target_type": item.get("target_type"),
            "target_name": item.get("target_name"),
            "relation": item.get("relation"),
            "confidence": item.get("confidence"),
            "evidence": evidence,
        }],
    }


def apply_simulation_delta(project_id: str, delta_id: str) -> dict[str, Any]:
    # Reuses the same apply/status logic as the in-run apply path so a
    # reviewed delta behaves identically to apply_graph=True.
    from app.agents.simulation_agent import _apply_graph_enhancements_with_status
    from app.models.graph import TextChunk
    from app.utils.graph_promotion import classify_node_layers

    proj_dir = _project_dir(project_id)
    simulation = _load_json(proj_dir / "simulation.json", "Simulation not run yet")
    kind, item = _find_delta(simulation, delta_id)
    if item.get("status") != "proposed":
        raise SimulationDeltaError(409, f"Delta {delta_id} is already {item.get('status')}")

    from app.utils.graph_delta_validation import validate_graph_enhancements

    graph = _load_graph(proj_dir)
    enhancements = validate_graph_enhancements(graph, _delta_to_enhancements(kind, item))

    # Write validation outcomes back to the stored delta item for transparency.
    if kind == "nodes" and enhancements["nodes"]:
        validated_node = enhancements["nodes"][0]
        dup = validated_node.get("duplicate_of") or ""
        if dup:
            item["duplicate_of"] = dup
    elif kind == "edges" and enhancements["edges"]:
        validated_edge = enhancements["edges"][0]
        if "relation_raw" in validated_edge:
            item["relation_raw"] = validated_edge["relation_raw"]
            item["relation"] = validated_edge["relation"]

    applied, statuses = _apply_graph_enhancements_with_status(graph, enhancements)
    status = (statuses["nodes"] or statuses["edges"])[0]
    item["status"] = status["status"]
    item["status_reason"] = status.get("status_reason", "")

    if applied["nodes_added"] or applied["edges_added"]:
        source_file_types: dict[str, str] = {}
        chunks_path = proj_dir / "chunks.json"
        if chunks_path.exists():
            chunks = [
                TextChunk(**c)
                for c in json.loads(chunks_path.read_text(encoding="utf-8"))
            ]
            source_file_types = {c.source_file: c.file_type for c in chunks}
        classify_node_layers(graph, source_file_types)
        _save_graph(proj_dir, graph)

    _refresh_summary(simulation)
    _persist_simulation(proj_dir, simulation)
    return {
        "delta": item,
        "applied": applied,
        "summary": simulation["graph_delta"]["summary"],
    }


def reject_simulation_delta(project_id: str, delta_id: str, reason: str = "") -> dict[str, Any]:
    proj_dir = _project_dir(project_id)
    simulation = _load_json(proj_dir / "simulation.json", "Simulation not run yet")
    _, item = _find_delta(simulation, delta_id)
    if item.get("status") not in ("proposed", "skipped"):
        raise SimulationDeltaError(409, f"Delta {delta_id} is already {item.get('status')}")

    item["status"] = "rejected"
    item["status_reason"] = reason or "Rejected by user review."
    _refresh_summary(simulation)
    _persist_simulation(proj_dir, simulation)
    return {"delta": item, "summary": simulation["graph_delta"]["summary"]}
