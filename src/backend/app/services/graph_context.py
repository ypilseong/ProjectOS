from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable
from typing import Any

import networkx as nx


def summarize_graph_context(graph: nx.DiGraph, *, max_hubs: int = 10) -> dict[str, Any]:
    """Return a compact, deterministic read-only graph summary."""
    limit = max(0, max_hubs)
    hubs = sorted(
        (
            _node_summary(graph, node_id)
            | {
                "in_degree": graph.in_degree(node_id),
                "out_degree": graph.out_degree(node_id),
                "degree": graph.degree(node_id),
            }
            for node_id in graph.nodes
        ),
        key=lambda item: (
            -item["degree"],
            not item["source_files"],
            item["type"],
            item["name"],
            item["id"],
        ),
    )

    sourced_node_count = sum(
        1 for _node_id, data in graph.nodes(data=True) if _source_files(data)
    )

    return {
        "kind": "graph_summary",
        "read_only": True,
        "counts": {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "types": _type_counts(graph),
            "relations": _relation_counts(graph),
            "nodes_with_source_files": sourced_node_count,
        },
        "limits": {"max_hubs": limit},
        "hubs": hubs[:limit],
    }


def get_node_context(
    graph: nx.DiGraph,
    node_name: str,
    node_type: str | None = None,
    max_neighbors: int = 20,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return compact one-hop context for the first deterministic node match.

    ``evidence`` is an optional list of pre-fetched source excerpts (e.g.
    ``{"label": "[cv.pdf#c1 p.1 char:0]", "text": "..."}``). When provided it is
    attached as a top-level ``evidence`` key, never inside ``counts``.
    """
    limit = max(0, max_neighbors)
    matches = _find_node_matches(graph, node_name, node_type)
    selected = matches[0] if matches else None
    metadata = _match_metadata(matches, selected)
    if selected is None:
        result = {
            "kind": "node_context",
            "read_only": True,
            "query": {"name": node_name, "type": node_type},
            "match": metadata,
            "counts": {"in_edges": 0, "out_edges": 0, "neighbors": 0},
            "limits": {"max_neighbors": limit},
            "node": None,
            "edges": {"in": [], "out": []},
        }
        if evidence is not None:
            result["evidence"] = list(evidence)
        return result

    incoming = [
        _edge_context(graph, source, selected, "in")
        for source in graph.predecessors(selected)
    ]
    outgoing = [
        _edge_context(graph, selected, target, "out")
        for target in graph.successors(selected)
    ]
    selected_edges = sorted(
        incoming + outgoing,
        key=lambda item: (
            item["direction"],
            item["relation"],
            item.get("from") or item.get("to") or "",
        ),
    )[:limit]

    result = {
        "kind": "node_context",
        "read_only": True,
        "query": {"name": node_name, "type": node_type},
        "match": metadata,
        "counts": {
            "in_edges": len(incoming),
            "out_edges": len(outgoing),
            "neighbors": len({item.get("from") or item.get("to") for item in incoming + outgoing}),
        },
        "limits": {"max_neighbors": limit},
        "node": _node_summary(graph, selected),
        "edges": {
            "in": [item for item in selected_edges if item["direction"] == "in"],
            "out": [item for item in selected_edges if item["direction"] == "out"],
        },
    }
    if evidence is not None:
        result["evidence"] = list(evidence)
    return result


def get_subgraph_context(
    graph: nx.DiGraph,
    node_name: str,
    node_type: str | None = None,
    depth: int = 1,
    max_nodes: int = 25,
) -> dict[str, Any]:
    """Return a compact directed subgraph around the first deterministic match."""
    depth_limit = max(0, depth)
    node_limit = max(0, max_nodes)
    matches = _find_node_matches(graph, node_name, node_type)
    selected = matches[0] if matches else None
    metadata = _match_metadata(matches, selected)
    if selected is None or node_limit == 0:
        return {
            "kind": "subgraph_context",
            "read_only": True,
            "query": {"name": node_name, "type": node_type},
            "match": metadata,
            "counts": {"nodes": 0, "edges": 0, "reachable_nodes": 0},
            "limits": {"depth": depth_limit, "max_nodes": node_limit},
            "nodes": [],
            "edges": [],
        }

    distances = _bounded_neighborhood(graph, selected, depth_limit, node_limit)
    included = set(distances)
    edges = sorted(
        (
            {
                "source": str(source),
                "target": str(target),
                "relation": _relation(graph, source, target),
            }
            for source, target in graph.edges
            if source in included and target in included
        ),
        key=lambda item: (item["source"], item["relation"], item["target"]),
    )
    nodes = [
        _node_summary(graph, node_id) | {"distance": distances[node_id]}
        for node_id in sorted(
            included,
            key=lambda item: (distances[item], _node_sort_key(graph, item)),
        )
    ]

    reachable_count = len(_bounded_neighborhood(graph, selected, depth_limit, graph.number_of_nodes()))

    return {
        "kind": "subgraph_context",
        "read_only": True,
        "query": {"name": node_name, "type": node_type},
        "match": metadata,
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "reachable_nodes": reachable_count,
        },
        "limits": {"depth": depth_limit, "max_nodes": node_limit},
        "nodes": nodes,
        "edges": edges,
    }


def _bounded_neighborhood(
    graph: nx.DiGraph,
    start: Any,
    depth: int,
    max_nodes: int,
) -> dict[Any, int]:
    distances: dict[Any, int] = {start: 0}
    queue: deque[Any] = deque([start])

    while queue and len(distances) < max_nodes:
        current = queue.popleft()
        next_depth = distances[current] + 1
        if next_depth > depth:
            continue

        neighbors = sorted(
            set(graph.predecessors(current)) | set(graph.successors(current)),
            key=lambda item: _node_sort_key(graph, item),
        )
        for neighbor in neighbors:
            if neighbor in distances:
                continue
            distances[neighbor] = next_depth
            queue.append(neighbor)
            if len(distances) >= max_nodes:
                break

    return distances


def _find_node_matches(
    graph: nx.DiGraph,
    node_name: str,
    node_type: str | None,
) -> list[Any]:
    query = str(node_name)
    matches = []
    for node_id, data in graph.nodes(data=True):
        if node_type is not None and str(data.get("type") or "") != str(node_type):
            continue
        if str(node_id) == query or str(data.get("name") or "") == query:
            matches.append(node_id)
    return sorted(matches, key=lambda item: _node_sort_key(graph, item))


def _match_metadata(matches: list[Any], selected: Any | None) -> dict[str, Any]:
    return {
        "count": len(matches),
        "selected_id": str(selected) if selected is not None else None,
        "ambiguous": len(matches) > 1,
        "ids": [str(match) for match in matches],
    }


def _edge_context(
    graph: nx.DiGraph,
    source: Any,
    target: Any,
    direction: str,
) -> dict[str, Any]:
    neighbor_id = source if direction == "in" else target
    key = "from" if direction == "in" else "to"
    return {
        "direction": direction,
        key: str(neighbor_id),
        "relation": _relation(graph, source, target),
        "node": _node_summary(graph, neighbor_id),
    }


def _node_summary(graph: nx.DiGraph, node_id: Any) -> dict[str, Any]:
    data = graph.nodes[node_id]
    return {
        "id": str(node_id),
        "type": str(data.get("type") or ""),
        "name": str(data.get("name") or node_id),
        "source_files": _source_files(data),
    }


def _node_sort_key(graph: nx.DiGraph, node_id: Any) -> tuple[str, str, str]:
    data = graph.nodes[node_id]
    return (
        str(data.get("type") or ""),
        str(data.get("name") or node_id),
        str(node_id),
    )


def _source_files(data: dict[str, Any]) -> list[str]:
    return _sorted_unique(data.get("source_files") or [])


def _type_counts(graph: nx.DiGraph) -> dict[str, int]:
    counts = Counter(str(data.get("type") or "unknown") for _node_id, data in graph.nodes(data=True))
    return dict(sorted(counts.items()))


def _relation_counts(graph: nx.DiGraph) -> dict[str, int]:
    counts = Counter(_relation(graph, source, target) for source, target in graph.edges)
    return dict(sorted(counts.items()))


def _relation(graph: nx.DiGraph, source: Any, target: Any) -> str:
    return str(graph.edges[source, target].get("relation") or "")


def _sorted_unique(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values] if values else []
    if not isinstance(values, Iterable):
        return [str(values)]
    return sorted({str(value) for value in values if value})
