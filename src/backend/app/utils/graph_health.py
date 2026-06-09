from difflib import SequenceMatcher
from pathlib import Path

import networkx as nx

from app.agents.obsidian_writer_agent import TYPE_TO_FOLDER, _safe_filename
from app.utils.graph_restructure import is_meta_node


def check_isolated_nodes(graph: nx.DiGraph) -> list[dict]:
    """Return nodes with no edges (degree == 0)."""
    result = []
    for node_id in graph.nodes:
        if is_meta_node(graph.nodes[node_id]):
            continue
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
            if is_meta_node(graph.nodes[nid]):
                continue
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
        if is_meta_node(data):
            continue
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
        if is_meta_node(graph.nodes[node_id]):
            continue
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


def check_wiki_graph_consistency(graph: nx.DiGraph, vault_path: str | None) -> dict:
    """Return wiki/graph consistency issues for an Obsidian vault."""
    if not vault_path:
        return {
            "graph_nodes_without_pages": [],
            "vault_pages_without_nodes": [],
            "orphan_pages": [],
            "duplicate_pages": [],
            "missing_source_nodes": [],
        }

    vault = Path(vault_path)
    node_pages: dict[str, str] = {}
    page_names: dict[str, list[str]] = {}
    for node_id, data in graph.nodes(data=True):
        if is_meta_node(data):
            continue
        ntype = data.get("type", "")
        name = data.get("name", "")
        if not ntype or not name:
            continue
        folder = TYPE_TO_FOLDER.get(ntype, "Misc")
        rel = f"{folder}/{_safe_filename(name)}.md"
        node_pages[rel] = node_id
        page_names.setdefault(name.lower(), []).append(rel)

    existing_pages = {
        str(page.relative_to(vault))
        for page in vault.glob("*/*.md")
        if page.is_file()
    } if vault.exists() else set()

    graph_nodes_without_pages = [
        {
            "node_id": node_id,
            "expected_page": rel,
            "name": graph.nodes[node_id].get("name"),
            "type": graph.nodes[node_id].get("type"),
        }
        for rel, node_id in sorted(node_pages.items())
        if rel not in existing_pages
    ]
    vault_pages_without_nodes = [
        {"page": page}
        for page in sorted(existing_pages - set(node_pages))
    ]
    orphan_pages = [
        {"page": page}
        for page in sorted(existing_pages)
        if _wikilink_count(vault / page) == 0
    ]
    duplicate_pages = [
        {"name": name, "pages": pages}
        for name, pages in sorted(page_names.items())
        if len(pages) > 1
    ]
    missing_source_nodes = [
        {
            "node_id": node_id,
            "name": data.get("name"),
            "type": data.get("type"),
        }
        for node_id, data in graph.nodes(data=True)
        if not is_meta_node(data) and not data.get("source_files")
    ]

    return {
        "graph_nodes_without_pages": graph_nodes_without_pages,
        "vault_pages_without_nodes": vault_pages_without_nodes,
        "orphan_pages": orphan_pages,
        "duplicate_pages": duplicate_pages,
        "missing_source_nodes": missing_source_nodes,
    }


def _wikilink_count(path: Path) -> int:
    if not path.exists():
        return 0
    return path.read_text(encoding="utf-8").count("[[")


def run_health_check(
    graph: nx.DiGraph,
    max_degree: int = 20,
    dup_threshold: float = 0.85,
    vault_path: str | None = None,
) -> dict:
    isolated = check_isolated_nodes(graph)
    components = check_weak_components(graph)
    duplicates = check_duplicate_candidates(graph, threshold=dup_threshold)
    hubs = check_hub_nodes(graph, max_degree=max_degree)
    wiki = check_wiki_graph_consistency(graph, vault_path)
    return {
        "isolated_nodes": isolated,
        "weak_components": components,
        "duplicate_candidates": duplicates,
        "hub_nodes": hubs,
        "wiki_graph_lint": wiki,
        "summary": {
            "total_nodes": graph.number_of_nodes(),
            "total_edges": graph.number_of_edges(),
            "isolated_count": len(isolated),
            "component_count": len(components),
            "duplicate_pair_count": len(duplicates),
            "hub_count": len(hubs),
            "graph_nodes_without_pages_count": len(wiki["graph_nodes_without_pages"]),
            "vault_pages_without_nodes_count": len(wiki["vault_pages_without_nodes"]),
            "orphan_page_count": len(wiki["orphan_pages"]),
            "duplicate_page_count": len(wiki["duplicate_pages"]),
            "missing_source_node_count": len(wiki["missing_source_nodes"]),
        },
    }
