from pathlib import Path

import numpy as np
import networkx as nx

from app.config import config
from app.utils.embedding_client import EmbeddingClient
from app.utils.entity_normalization import are_acronym_variants
from app.utils.logger import get_logger
from app.utils.user_config import get_user_name_variants, load_user_config

logger = get_logger(__name__)

# Person nodes represent distinct individuals — never merge them automatically.
_SKIP_TYPES = {"Person"}


async def semantic_dedup(graph: nx.DiGraph) -> tuple[nx.DiGraph, int]:
    """Merge semantically equivalent nodes of the same type using BGE-M3 embeddings.

    Returns the modified graph and the number of nodes merged.
    Skips silently if EMBEDDING_BASE_URL is not configured.
    """
    graph, alias_merged = deterministic_acronym_dedup(graph)
    if not config.EMBEDDING_BASE_URL:
        return graph, alias_merged

    client = EmbeddingClient()

    # Group nodes by type, skipping Person
    type_groups: dict[str, list[tuple[str, str]]] = {}
    for node_id, data in graph.nodes(data=True):
        ntype = data.get("type", "")
        if ntype in _SKIP_TYPES or not ntype:
            continue
        name = data.get("name", "").strip()
        if not name:
            continue
        type_groups.setdefault(ntype, []).append((node_id, name))

    merge_pairs: list[tuple[str, str]] = []  # (keep, remove)

    for ntype, nodes in type_groups.items():
        if len(nodes) < 2:
            continue

        node_ids = [n[0] for n in nodes]
        names = [n[1] for n in nodes]

        try:
            embeddings = await client.embed(names)
        except Exception as e:
            logger.warning(f"Embedding failed for type {ntype}: {e}")
            continue

        arr = np.array(embeddings, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        arr /= np.maximum(norms, 1e-9)
        sim = arr @ arr.T  # cosine similarity matrix

        # Union-Find for transitive grouping
        parent = list(range(len(nodes)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if float(sim[i, j]) >= config.SEMANTIC_DEDUP_THRESHOLD:
                    pi, pj = find(i), find(j)
                    if pi != pj:
                        parent[pj] = pi

        groups: dict[int, list[int]] = {}
        for idx in range(len(nodes)):
            groups.setdefault(find(idx), []).append(idx)

        for group_indices in groups.values():
            if len(group_indices) < 2:
                continue
            # Canonical = highest degree; ties broken by name length (shorter wins)
            canonical_idx = max(
                group_indices,
                key=lambda i: (graph.degree(node_ids[i]), -len(names[i])),
            )
            for dup_idx in group_indices:
                if dup_idx != canonical_idx:
                    merge_pairs.append((node_ids[canonical_idx], node_ids[dup_idx]))

    merged = 0
    for canonical_id, dup_id in merge_pairs:
        if dup_id not in graph or canonical_id not in graph:
            continue
        _merge_node(graph, canonical_id, dup_id)
        merged += 1
        logger.info(
            f"Dedup: merged '{graph.nodes[canonical_id].get('name')}'"
            f" ← '{dup_id.split(':', 1)[-1]}' ({graph.nodes[canonical_id].get('type')})"
        )

    if merged:
        logger.info(f"Semantic deduplication: merged {merged} node(s)")
    return graph, alias_merged + merged


def deterministic_acronym_dedup(graph: nx.DiGraph) -> tuple[nx.DiGraph, int]:
    """Merge generic acronym/full-form variants before embedding/LLM dedup."""
    merge_pairs: list[tuple[str, str]] = []
    by_type: dict[str, list[str]] = {}
    for node_id, data in graph.nodes(data=True):
        ntype = data.get("type", "")
        if ntype in _SKIP_TYPES or not ntype:
            continue
        by_type.setdefault(ntype, []).append(node_id)

    for node_ids in by_type.values():
        for i, id_a in enumerate(node_ids):
            for id_b in node_ids[i + 1:]:
                name_a = graph.nodes[id_a].get("name", "")
                name_b = graph.nodes[id_b].get("name", "")
                if not are_acronym_variants(name_a, name_b):
                    continue
                canonical, dup = max(
                    (id_a, id_b),
                    key=lambda nid: (
                        " " in graph.nodes[nid].get("name", ""),
                        graph.degree(nid),
                        len(graph.nodes[nid].get("name", "")),
                    ),
                ), min(
                    (id_a, id_b),
                    key=lambda nid: (
                        " " in graph.nodes[nid].get("name", ""),
                        graph.degree(nid),
                        len(graph.nodes[nid].get("name", "")),
                    ),
                )
                merge_pairs.append((canonical, dup))

    merged = 0
    for canonical_id, dup_id in merge_pairs:
        if canonical_id not in graph or dup_id not in graph:
            continue
        dup_name = graph.nodes[dup_id].get("name", dup_id)
        _merge_node(graph, canonical_id, dup_id)
        merged += 1
        logger.info(
            f"Acronym dedup: merged '{graph.nodes[canonical_id].get('name')}'"
            f" ← '{dup_name}' ({graph.nodes[canonical_id].get('type')})"
        )

    return graph, merged


def merge_user_persons(graph: nx.DiGraph) -> tuple[nx.DiGraph, int]:
    """Merge Person nodes that refer to the same user based on user.json.

    Reads name variants (name + display_name) from USER_CONFIG_PATH and
    merges all matching Person nodes into one canonical node.
    """
    user_config_path = Path(config.USER_CONFIG_PATH)
    if not user_config_path.exists():
        return graph, 0

    user_data = load_user_config()
    if not user_data:
        return graph, 0

    name_variants = get_user_name_variants(user_data)

    if len(name_variants) < 2:
        return graph, 0

    matched: list[str] = []
    for node_id, data in graph.nodes(data=True):
        if data.get("type") != "Person":
            continue
        if data.get("name", "").strip().lower() in name_variants:
            matched.append(node_id)

    if len(matched) < 2:
        return graph, 0

    primary_name = (user_data.get("name") or "").strip()
    display_name = (user_data.get("display_name") or "").strip()
    canonical_id = max(
        matched,
        key=lambda nid: (
            1 if graph.nodes[nid].get("name") == primary_name else 0,
            1 if graph.nodes[nid].get("name") == display_name else 0,
            graph.degree(nid),
        ),
    )

    merged = 0
    for dup_id in matched:
        if dup_id == canonical_id:
            continue
        dup_name = graph.nodes[dup_id].get("name")
        _merge_node(graph, canonical_id, dup_id)
        merged += 1
        logger.info(
            f"User person merge: '{graph.nodes[canonical_id].get('name')}'"
            f" ← '{dup_name}'"
        )

    return graph, merged


def _merge_node(graph: nx.DiGraph, canonical_id: str, dup_id: str):
    """Redirect all edges from dup_id to canonical_id, then remove dup_id."""
    for pred in list(graph.predecessors(dup_id)):
        if pred != canonical_id and not graph.has_edge(pred, canonical_id):
            graph.add_edge(pred, canonical_id, **graph.edges[pred, dup_id])

    for succ in list(graph.successors(dup_id)):
        if succ != canonical_id and not graph.has_edge(canonical_id, succ):
            graph.add_edge(canonical_id, succ, **graph.edges[dup_id, succ])

    dup_sources = set(graph.nodes[dup_id].get("source_files", []))
    can_sources = set(graph.nodes[canonical_id].get("source_files", []))
    graph.nodes[canonical_id]["source_files"] = list(can_sources | dup_sources)

    dup_chunks = set(graph.nodes[dup_id].get("source_chunk_ids", []))
    can_chunks = set(graph.nodes[canonical_id].get("source_chunk_ids", []))
    graph.nodes[canonical_id]["source_chunk_ids"] = list(can_chunks | dup_chunks)

    graph.remove_node(dup_id)
