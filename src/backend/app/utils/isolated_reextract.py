from __future__ import annotations

import networkx as nx

from app.utils.logger import get_logger

logger = get_logger(__name__)

_HEADER_CHUNKS = 2   # document header size (first N chunks of each file)
_NEIGHBOR_WINDOW = 2  # ± chunks around the mention


def _find_mention_indices(
    node_name: str,
    chunks: list,
    file_chunk_indices: list[int],
) -> list[int]:
    """Return indices (into chunks) from file_chunk_indices whose text mentions node_name."""
    # Build search terms: full name prefix + individual long words
    prefix = node_name[:20].strip().lower()
    words = [w.lower() for w in node_name.split() if len(w) >= 4]
    terms = list(dict.fromkeys([prefix] + words[:3]))  # dedup, keep order

    return [
        idx for idx in file_chunk_indices
        if any(t in chunks[idx].text.lower() for t in terms)
    ]


def _build_window(
    mention_indices: list[int],
    file_chunk_indices: list[int],
    window: int,
) -> list[int]:
    """Return mention indices ± window positions within file_chunk_indices (sorted)."""
    sorted_file = sorted(file_chunk_indices)
    pos_map = {abs_idx: pos for pos, abs_idx in enumerate(sorted_file)}
    result: set[int] = set()
    for abs_idx in mention_indices:
        pos = pos_map.get(abs_idx)
        if pos is None:
            continue
        for p in range(max(0, pos - window), min(len(sorted_file), pos + window + 1)):
            result.add(sorted_file[p])
    return sorted(result)


def _join_chunks(chunks: list, indices: list[int]) -> str:
    return "\n\n".join(chunks[i].text for i in indices)


async def reextract_isolated_nodes(
    graph: nx.DiGraph,
    chunks: list,
    graph_agent,
    ontology,
    progress_callback=None,
) -> tuple[nx.DiGraph, int]:
    """Cascade re-extraction for isolated (degree-0) nodes.

    Pass 2: For each isolated node, find chunks from its source file that
            mention the node name and re-extract with ±NEIGHBOR_WINDOW context.
    Pass 3: Still isolated → prepend document header (first HEADER_CHUNKS of file)
            and retry.

    Returns (graph, number_of_newly_connected_nodes).
    """
    isolated = [
        (nid, data) for nid, data in graph.nodes(data=True)
        if graph.degree(nid) == 0 and data.get("type") not in ("Category",)
    ]

    if not isolated:
        return graph, 0

    entity_types = [e.name for e in ontology.entity_types]
    edge_types = [e.name for e in ontology.edge_types]

    # Build file → chunk index list
    file_chunks: dict[str, list[int]] = {}
    for i, c in enumerate(chunks):
        file_chunks.setdefault(c.source_file, []).append(i)

    # Deduplicate context windows across nodes: cache (file, context_key) → already run
    seen_contexts: set[str] = set()

    connected = 0
    total = len(isolated)

    for step, (node_id, node_data) in enumerate(isolated, 1):
        node_name = node_data.get("name", "")
        source_files = node_data.get("source_files", [])
        if progress_callback:
            progress_callback(step, total, node_name)

        for source_file in source_files:
            chunk_indices = sorted(file_chunks.get(source_file, []))
            if not chunk_indices:
                continue

            # ── Pass 2: neighbor window around mention ──────────────────────
            mention_indices = _find_mention_indices(node_name, chunks, chunk_indices)
            pass2_indices = _build_window(mention_indices, chunk_indices, _NEIGHBOR_WINDOW)

            if pass2_indices:
                ctx_key = f"{source_file}|{','.join(map(str, pass2_indices))}"
                if ctx_key not in seen_contexts:
                    seen_contexts.add(ctx_key)
                    new_edges = await graph_agent.reextract_with_context(
                        _join_chunks(chunks, pass2_indices),
                        source_file,
                        graph,
                        entity_types,
                        edge_types,
                    )
                    logger.debug(f"Pass2 [{node_name}] +{new_edges} edges")

            if graph.degree(node_id) > 0:
                connected += 1
                break

            # ── Pass 3: prepend document header ────────────────────────────
            header_indices = chunk_indices[:_HEADER_CHUNKS]
            pass3_indices = sorted(set(header_indices + pass2_indices))

            # fallback: if no mention found, use header alone
            if not pass3_indices:
                pass3_indices = header_indices

            if pass3_indices:
                ctx_key = f"{source_file}|{','.join(map(str, pass3_indices))}"
                if ctx_key not in seen_contexts:
                    seen_contexts.add(ctx_key)
                    new_edges = await graph_agent.reextract_with_context(
                        _join_chunks(chunks, pass3_indices),
                        source_file,
                        graph,
                        entity_types,
                        edge_types,
                    )
                    logger.debug(f"Pass3 [{node_name}] +{new_edges} edges")

            if graph.degree(node_id) > 0:
                connected += 1
                break

    if connected:
        logger.info(f"Isolated re-extraction: connected {connected}/{total} nodes")
    return graph, connected
