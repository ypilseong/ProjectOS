import networkx as nx

from app.utils.graph_restructure import (
    _has_paper_source,
    _has_profile_source,
    _load_user_person_ids,
    is_meta_node,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

CAREER_LAYER = "career"
PUBLICATION_LAYER = "publication"
KNOWLEDGE_LAYER = "knowledge"

# Relations that, when they originate from a career-layer Person or Project,
# justify promoting the connected entity into the career layer. These encode
# direct user ownership/use rather than incidental co-mention.
_OWNERSHIP_RELATIONS = {
    "DEVELOPED",
    "LED_BY",
    "WORKED_AT",
    "HAS_ROLE",
    "ACHIEVED",
    "PARTICIPATED_IN",
    "USES_SKILL",
    "COLLABORATED_WITH",
    "MENTORED_BY",
}


def _edge_relation(graph: nx.DiGraph, a: str, b: str) -> str:
    if graph.has_edge(a, b):
        return str(graph.edges[a, b].get("relation", "")).upper()
    if graph.has_edge(b, a):
        return str(graph.edges[b, a].get("relation", "")).upper()
    return ""


def classify_node_layers(
    graph: nx.DiGraph,
    source_file_types: dict[str, str] | None = None,
) -> tuple[nx.DiGraph, dict[str, int]]:
    """Assign every analytical node a source-aware ``layer`` attribute.

    Promotion into the career layer requires direct evidence: profile (CV/resume)
    sourcing, being the user, or an ownership/use relation from a career Person or
    Project. Paper/report-only entities stay in the publication or knowledge layer
    so they are not silently treated as user career facts. Meta/navigation nodes
    (categories, captures) receive no layer.
    """
    user_ids = _load_user_person_ids(graph)
    layers: dict[str, str | None] = {}

    for node_id, data in graph.nodes(data=True):
        if is_meta_node(data):
            continue
        ntype = data.get("type")
        if node_id in user_ids or _has_profile_source(data, source_file_types):
            layers[node_id] = CAREER_LAYER
        elif ntype == "Publication":
            layers[node_id] = PUBLICATION_LAYER
        elif ntype == "Person":
            layers[node_id] = (
                PUBLICATION_LAYER
                if _has_paper_source(data, source_file_types)
                else KNOWLEDGE_LAYER
            )
        else:
            layers[node_id] = None

    changed = True
    while changed:
        changed = False
        for node_id in layers:
            if layers[node_id] is not None:
                continue
            neighbors = set(graph.predecessors(node_id)) | set(graph.successors(node_id))
            for neighbor in neighbors:
                if layers.get(neighbor) != CAREER_LAYER:
                    continue
                if _edge_relation(graph, neighbor, node_id) in _OWNERSHIP_RELATIONS:
                    layers[node_id] = CAREER_LAYER
                    changed = True
                    break

    for node_id, data in graph.nodes(data=True):
        if is_meta_node(data) or layers.get(node_id) is not None:
            continue
        # Remaining entities are paper/report topics, methods, or speculative
        # concepts with no user ownership — they belong to the knowledge layer.
        layers[node_id] = KNOWLEDGE_LAYER

    counts: dict[str, int] = {}
    for node_id, layer in layers.items():
        graph.nodes[node_id]["layer"] = layer
        counts[layer] = counts.get(layer, 0) + 1

    if counts:
        logger.info(f"Layer classification: {counts}")
    return graph, counts
