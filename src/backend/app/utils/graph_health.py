from difflib import SequenceMatcher

import networkx as nx


def check_isolated_nodes(graph: nx.DiGraph) -> list[dict]:
    """Return nodes with no edges (degree == 0)."""
    result = []
    for node_id in graph.nodes:
        if graph.degree(node_id) == 0:
            data = graph.nodes[node_id]
            result.append({
                "node_id": node_id,
                "type": data.get("type"),
                "name": data.get("name"),
            })
    return result


def check_weak_components(graph: nx.DiGraph) -> list[dict]:
    """Return info about each weakly connected component."""
    undirected = graph.to_undirected()
    components = list(nx.connected_components(undirected))
    result = []
    for comp in components:
        types: dict[str, int] = {}
        for nid in comp:
            t = graph.nodes[nid].get("type", "unknown")
            types[t] = types.get(t, 0) + 1
        result.append({
            "size": len(comp),
            "node_types": types,
            "sample_nodes": [graph.nodes[n].get("name", n) for n in list(comp)[:3]],
        })
    result.sort(key=lambda x: -x["size"])
    return result


def check_duplicate_candidates(
    graph: nx.DiGraph, threshold: float = 0.85
) -> list[dict]:
    """Return pairs of same-type nodes whose names are similar but not identical."""
    by_type: dict[str, list[tuple[str, str]]] = {}
    for node_id, data in graph.nodes(data=True):
        ntype = data.get("type", "")
        name = data.get("name", "")
        if ntype and name:
            by_type.setdefault(ntype, []).append((node_id, name))

    pairs = []
    for ntype, nodes in by_type.items():
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                id_a, name_a = nodes[i]
                id_b, name_b = nodes[j]
                if name_a == name_b:
                    continue
                ratio = SequenceMatcher(None, name_a.lower(), name_b.lower()).ratio()
                if ratio >= threshold:
                    pairs.append({
                        "type": ntype,
                        "node_id_a": id_a,
                        "name_a": name_a,
                        "node_id_b": id_b,
                        "name_b": name_b,
                        "similarity": round(ratio, 3),
                    })
    pairs.sort(key=lambda x: -x["similarity"])
    return pairs


def check_hub_nodes(graph: nx.DiGraph, max_degree: int = 20) -> list[dict]:
    """Return nodes with total degree above max_degree."""
    result = []
    for node_id in graph.nodes:
        deg = graph.degree(node_id)
        if deg > max_degree:
            data = graph.nodes[node_id]
            result.append({
                "node_id": node_id,
                "type": data.get("type"),
                "name": data.get("name"),
                "degree": deg,
            })
    result.sort(key=lambda x: -x["degree"])
    return result


def run_health_check(graph: nx.DiGraph, max_degree: int = 20, dup_threshold: float = 0.85) -> dict:
    isolated = check_isolated_nodes(graph)
    components = check_weak_components(graph)
    duplicates = check_duplicate_candidates(graph, threshold=dup_threshold)
    hubs = check_hub_nodes(graph, max_degree=max_degree)
    return {
        "isolated_nodes": isolated,
        "weak_components": components,
        "duplicate_candidates": duplicates,
        "hub_nodes": hubs,
        "summary": {
            "total_nodes": graph.number_of_nodes(),
            "total_edges": graph.number_of_edges(),
            "isolated_count": len(isolated),
            "component_count": len(components),
            "duplicate_pair_count": len(duplicates),
            "hub_count": len(hubs),
        },
    }
