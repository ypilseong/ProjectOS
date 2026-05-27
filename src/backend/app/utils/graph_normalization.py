import networkx as nx

from app.models.graph import EdgeTypeDef, EntityTypeDef, Ontology
from app.utils.entity_validation import normalize_entity_type
from app.utils.semantic_dedup import _merge_node


def normalize_ontology_types(ontology: Ontology) -> Ontology:
    """Apply entity type aliases to an ontology loaded from older project files."""
    entity_names: list[str] = []
    entity_defs: list[EntityTypeDef] = []
    for entity in ontology.entity_types:
        name = normalize_entity_type(entity.name)
        if name in entity_names:
            continue
        entity_names.append(name)
        entity_defs.append(
            EntityTypeDef(
                name=name,
                description=entity.description,
                examples=entity.examples,
            )
        )

    edge_defs: list[EdgeTypeDef] = []
    seen_edges: set[str] = set()
    for edge in ontology.edge_types:
        if edge.name in seen_edges:
            continue
        seen_edges.add(edge.name)
        edge_defs.append(
            EdgeTypeDef(
                name=edge.name,
                description=edge.description,
                source_types=_normalize_type_list(edge.source_types),
                target_types=_normalize_type_list(edge.target_types),
            )
        )

    return Ontology(
        entity_types=entity_defs,
        edge_types=edge_defs,
        analysis_summary=ontology.analysis_summary,
    )


def normalize_graph_entity_types(graph: nx.DiGraph) -> tuple[nx.DiGraph, int]:
    """Rename legacy aliased node types in-place, merging collisions."""
    changed = 0
    for node_id, data in list(graph.nodes(data=True)):
        current_type = data.get("type", "")
        normalized_type = normalize_entity_type(current_type)
        if normalized_type == current_type:
            continue

        name = data.get("name", "")
        new_id = f"{normalized_type}:{name}"
        if new_id in graph:
            _merge_node(graph, new_id, node_id)
        else:
            nx.relabel_nodes(graph, {node_id: new_id}, copy=False)
            graph.nodes[new_id]["type"] = normalized_type
        changed += 1

    return graph, changed


def _normalize_type_list(types: list) -> list[str]:
    normalized: list[str] = []
    for item in types or []:
        name = normalize_entity_type(str(item))
        if name not in normalized:
            normalized.append(name)
    return normalized
