from __future__ import annotations

from difflib import SequenceMatcher

import networkx as nx

from app.config import config
from app.utils.entity_normalization import are_acronym_variants
from app.utils.graph_restructure import is_meta_node
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _node_aliases(data: dict) -> set[str]:
    aliases = {str(a).strip() for a in (data.get("aliases") or []) if str(a).strip()}
    name = str(data.get("name", "")).strip()
    if name:
        aliases.add(name)
    return aliases


def collect_merge_candidates(
    graph: nx.DiGraph, threshold: float | None = None
) -> list[dict]:
    """Generate reviewable merge candidates without mutating the graph.

    Same-type node pairs whose names are highly similar (string ratio) or are
    acronym/full-form variants are surfaced as candidates with a confidence
    score and the union of both nodes' surface forms. These are suggestions for
    human review — deliberately NOT auto-merged — so borderline duplicates stay
    visible instead of being silently collapsed.
    """
    if threshold is None:
        threshold = config.MERGE_REVIEW_THRESHOLD

    by_type: dict[str, list[str]] = {}
    for node_id, data in graph.nodes(data=True):
        if is_meta_node(data):
            continue
        ntype = data.get("type", "")
        name = str(data.get("name", "")).strip()
        if not ntype or not name:
            continue
        by_type.setdefault(ntype, []).append(node_id)

    candidates: list[dict] = []
    for ntype, node_ids in by_type.items():
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                id_a, id_b = node_ids[i], node_ids[j]
                data_a, data_b = graph.nodes[id_a], graph.nodes[id_b]
                name_a = str(data_a.get("name", "")).strip()
                name_b = str(data_b.get("name", "")).strip()

                acronym = are_acronym_variants(name_a, name_b)
                sim = _similarity(name_a, name_b)
                if not acronym and sim < threshold:
                    continue
                confidence = 1.0 if acronym else round(sim, 4)

                # Keep = higher degree (more connected node wins canonical role).
                if graph.degree(id_a) >= graph.degree(id_b):
                    keep_id, cand_id = id_a, id_b
                else:
                    keep_id, cand_id = id_b, id_a

                aliases = _node_aliases(graph.nodes[keep_id]) | _node_aliases(
                    graph.nodes[cand_id]
                )
                candidates.append(
                    {
                        "type": ntype,
                        "keep_id": keep_id,
                        "keep_name": graph.nodes[keep_id].get("name", ""),
                        "candidate_id": cand_id,
                        "candidate_name": graph.nodes[cand_id].get("name", ""),
                        "confidence": confidence,
                        "aliases": sorted(aliases),
                    }
                )

    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    if candidates:
        logger.info(f"Merge review: {len(candidates)} candidate pair(s) collected")
    return candidates
