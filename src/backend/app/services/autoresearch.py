from __future__ import annotations

from collections.abc import Iterable
from difflib import SequenceMatcher
from typing import Any

import networkx as nx


DEFAULT_ALLOWED_TYPES = {
    "Achievement",
    "Organization",
    "Person",
    "Project",
    "Publication",
    "Skill",
    "Technology",
}


def generate_autoresearch_candidates(
    graph: nx.Graph,
    chunks: Iterable[Any] | None = None,
    health: dict[str, Any] | None = None,
    *,
    allowed_types: set[str] | None = None,
    min_degree: int = 1,
    component_size_threshold: int = 3,
    duplicate_threshold: float = 0.85,
    max_candidates: int = 20,
) -> list[dict[str, Any]]:
    """Return deterministic research/review candidates for graph weak spots.

    This is intentionally a candidate generator, not a live web research runner.
    Optional health reports are accepted to reuse already computed diagnostics.
    """
    if graph.number_of_nodes() == 0 or max_candidates <= 0:
        return []

    allowed = allowed_types or DEFAULT_ALLOWED_TYPES
    chunk_index = _chunk_evidence_index(chunks)
    candidates: list[dict[str, Any]] = []

    candidates.extend(_duplicate_candidates(graph, health, duplicate_threshold))
    candidates.extend(_isolated_node_candidates(graph, allowed, chunk_index))
    candidates.extend(_missing_source_candidates(graph, allowed, health, chunk_index))
    candidates.extend(_sparse_node_candidates(graph, allowed, min_degree, chunk_index))
    candidates.extend(_small_component_candidates(
        graph,
        allowed,
        component_size_threshold,
        chunk_index,
    ))

    deduped = {candidate["id"]: candidate for candidate in candidates}
    ordered = sorted(
        deduped.values(),
        key=lambda c: (-int(c["priority"]), c["id"]),
    )
    return ordered[:max_candidates]


def _duplicate_candidates(
    graph: nx.Graph,
    health: dict[str, Any] | None,
    threshold: float,
) -> list[dict[str, Any]]:
    pairs = []
    if health:
        pairs = list(health.get("duplicate_candidates") or [])
    if not pairs:
        pairs = _find_duplicate_pairs(graph, threshold)

    candidates = []
    for pair in pairs:
        node_a = pair.get("node_id_a")
        node_b = pair.get("node_id_b")
        if not node_a or not node_b or node_a not in graph or node_b not in graph:
            continue
        data_a = graph.nodes[node_a]
        data_b = graph.nodes[node_b]
        if _is_category(data_a) or _is_category(data_b):
            continue
        ordered_pair = sorted(
            [
                (str(node_a), data_a.get("name") or str(node_a), data_a.get("type")),
                (str(node_b), data_b.get("name") or str(node_b), data_b.get("type")),
            ],
            key=lambda item: item[0],
        )
        node_ids = [item[0] for item in ordered_pair]
        names = [item[1] for item in ordered_pair]
        ntypes = [item[2] for item in ordered_pair]
        source_files = _sorted_unique(_source_files(data_a) + _source_files(data_b))
        candidates.append({
            "id": f"duplicate:{node_ids[0]}|{node_ids[1]}",
            "kind": "review_needed",
            "priority": 100,
            "node_ids": node_ids,
            "names": names,
            "types": ntypes,
            "reason": "Possible duplicate nodes should be reviewed before adding new research.",
            "suggested_query": (
                f"Review whether {names[0]} and {names[1]} are the same "
                f"{ntypes[0] or 'entity'}."
            ),
            "evidence": {
                "similarity": pair.get("similarity"),
                "source_files": source_files,
            },
            "source_files": source_files,
        })
    return candidates


def _isolated_node_candidates(
    graph: nx.Graph,
    allowed_types: set[str],
    chunk_index: dict[str, list[str]],
) -> list[dict[str, Any]]:
    candidates = []
    for node_id, data in graph.nodes(data=True):
        if not _eligible(data, allowed_types):
            continue
        if _non_category_degree(graph, node_id) == 0:
            candidates.append(_node_candidate(
                "isolated",
                90,
                graph,
                node_id,
                "Node has no non-category graph connections.",
                chunk_index,
            ))
    return candidates


def _missing_source_candidates(
    graph: nx.Graph,
    allowed_types: set[str],
    health: dict[str, Any] | None,
    chunk_index: dict[str, list[str]],
) -> list[dict[str, Any]]:
    node_ids: set[str] = set()
    for node_id, data in graph.nodes(data=True):
        if _eligible(data, allowed_types) and not _source_files(data):
            node_ids.add(str(node_id))

    if health:
        lint = health.get("wiki_graph_lint") or {}
        for item in lint.get("missing_source_nodes") or []:
            node_id = item.get("node_id")
            if node_id in graph and _eligible(graph.nodes[node_id], allowed_types):
                node_ids.add(str(node_id))

    return [
        _node_candidate(
            "missing_source",
            80,
            graph,
            node_id,
            "Node has no source_files evidence.",
            chunk_index,
        )
        for node_id in node_ids
    ]


def _sparse_node_candidates(
    graph: nx.Graph,
    allowed_types: set[str],
    min_degree: int,
    chunk_index: dict[str, list[str]],
) -> list[dict[str, Any]]:
    candidates = []
    for node_id, data in graph.nodes(data=True):
        if not _eligible(data, allowed_types):
            continue
        degree = _non_category_degree(graph, node_id)
        if 0 < degree <= min_degree:
            candidate = _node_candidate(
                "sparse_node",
                70,
                graph,
                node_id,
                f"Important node has only {degree} non-category connection(s).",
                chunk_index,
            )
            candidate["evidence"]["degree"] = degree
            candidates.append(candidate)
    return candidates


def _small_component_candidates(
    graph: nx.Graph,
    allowed_types: set[str],
    threshold: int,
    chunk_index: dict[str, list[str]],
) -> list[dict[str, Any]]:
    if threshold <= 1:
        return []
    subgraph = graph.subgraph([
        node_id
        for node_id, data in graph.nodes(data=True)
        if _eligible(data, allowed_types)
    ])
    components = (
        nx.weakly_connected_components(subgraph)
        if subgraph.is_directed()
        else nx.connected_components(subgraph)
    )
    candidates = []
    for component in components:
        ordered_nodes = sorted(str(node_id) for node_id in component)
        if not ordered_nodes or len(ordered_nodes) >= threshold:
            continue
        names = [_node_name(graph, node_id) for node_id in ordered_nodes]
        types = [graph.nodes[node_id].get("type") for node_id in ordered_nodes]
        source_files = _sorted_unique(
            source
            for node_id in ordered_nodes
            for source in _candidate_sources(graph.nodes[node_id], chunk_index)
        )
        candidates.append({
            "id": f"weak_component:{'|'.join(ordered_nodes)}",
            "kind": "research",
            "priority": 60,
            "node_ids": ordered_nodes,
            "names": names,
            "types": types,
            "reason": f"Weak component has only {len(ordered_nodes)} node(s).",
            "suggested_query": f"Find evidence and relationships for {' '.join(names)}.",
            "evidence": {
                "component_size": len(ordered_nodes),
                "source_files": source_files,
            },
            "source_files": source_files,
        })
    return candidates


def _node_candidate(
    kind: str,
    priority: int,
    graph: nx.Graph,
    node_id: str,
    reason: str,
    chunk_index: dict[str, list[str]],
) -> dict[str, Any]:
    data = graph.nodes[node_id]
    name = _node_name(graph, node_id)
    ntype = data.get("type")
    source_files = _candidate_sources(data, chunk_index)
    return {
        "id": f"{kind}:{node_id}",
        "kind": "research",
        "priority": priority,
        "node_id": str(node_id),
        "name": name,
        "type": ntype,
        "reason": reason,
        "suggested_query": f"Find source evidence and graph relationships for {name} {ntype or ''}.".strip(),
        "evidence": {"source_files": source_files},
        "source_files": source_files,
    }


def _find_duplicate_pairs(graph: nx.Graph, threshold: float) -> list[dict[str, Any]]:
    by_type: dict[str, list[tuple[str, str]]] = {}
    for node_id, data in graph.nodes(data=True):
        if _is_category(data) or data.get("meta"):
            continue
        ntype = data.get("type")
        name = data.get("name")
        if ntype and name:
            by_type.setdefault(str(ntype), []).append((str(node_id), str(name)))

    pairs = []
    for ntype, nodes in by_type.items():
        nodes.sort(key=lambda item: item[0])
        for index, (id_a, name_a) in enumerate(nodes):
            for id_b, name_b in nodes[index + 1:]:
                if name_a == name_b:
                    continue
                similarity = SequenceMatcher(None, name_a.lower(), name_b.lower()).ratio()
                if similarity >= threshold:
                    pairs.append({
                        "type": ntype,
                        "node_id_a": id_a,
                        "name_a": name_a,
                        "node_id_b": id_b,
                        "name_b": name_b,
                        "similarity": round(similarity, 3),
                    })
    return sorted(pairs, key=lambda pair: (-pair["similarity"], pair["node_id_a"], pair["node_id_b"]))


def _chunk_evidence_index(chunks: Iterable[Any] | None) -> dict[str, list[str]]:
    index: dict[str, set[str]] = {}
    if not chunks:
        return {}
    for chunk in chunks:
        text = str(getattr(chunk, "text", "") or "")
        source_file = getattr(chunk, "source_file", None)
        if not text or not source_file:
            continue
        for token in set(text.lower().split()):
            index.setdefault(token, set()).add(str(source_file))
    return {token: sorted(sources) for token, sources in index.items()}


def _candidate_sources(data: dict[str, Any], chunk_index: dict[str, list[str]]) -> list[str]:
    sources = _source_files(data)
    name = str(data.get("name") or "")
    for token in name.lower().split():
        sources.extend(chunk_index.get(token, []))
    return _sorted_unique(sources)


def _non_category_degree(graph: nx.Graph, node_id: str) -> int:
    if graph.is_directed():
        neighbors = set(graph.predecessors(node_id)) | set(graph.successors(node_id))
    else:
        neighbors = set(graph.neighbors(node_id))
    return sum(1 for neighbor in neighbors if not _is_category(graph.nodes[neighbor]))


def _eligible(data: dict[str, Any], allowed_types: set[str]) -> bool:
    ntype = data.get("type")
    return bool(data.get("name")) and ntype in allowed_types and not _is_category(data)


def _is_category(data: dict[str, Any]) -> bool:
    return data.get("type") == "Category"


def _node_name(graph: nx.Graph, node_id: str) -> str:
    return str(graph.nodes[node_id].get("name") or node_id)


def _source_files(data: dict[str, Any]) -> list[str]:
    value = data.get("source_files") or []
    if isinstance(value, str):
        return [value]
    return [str(source) for source in value if source]


def _sorted_unique(values: Iterable[Any]) -> list[str]:
    return sorted({str(value) for value in values if value})
