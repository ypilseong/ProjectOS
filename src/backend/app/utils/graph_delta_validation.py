from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

import networkx as nx

from app.config import config
from app.utils.entity_normalization import are_acronym_variants
from app.utils.logger import get_logger

logger = get_logger(__name__)

# CLAUDE.md 고정 관계 10종 + 그래프 빌더가 실제 사용하는 구조 관계.
ALLOWED_RELATIONS = {
    "WORKED_AT", "DEVELOPED", "USES_SKILL", "AUTHORED", "COLLABORATED_WITH",
    "ACHIEVED", "PARTICIPATED_IN", "PUBLISHED_AT", "MENTORED_BY", "LED_BY",
    "HAS_ROLE", "INCLUDES", "HAS", "RELATED_TO",
}


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _find_existing_duplicate(graph: nx.DiGraph, ntype: str, name: str) -> str | None:
    threshold = config.FUZZY_MATCH_THRESHOLD
    exact_id = f"{ntype}:{name}"
    for node_id, data in graph.nodes(data=True):
        if node_id == exact_id or data.get("type") != ntype:
            continue
        existing = str(data.get("name", "")).strip()
        if not existing:
            continue
        if (
            existing.lower() == name.lower()
            or are_acronym_variants(existing, name)
            or _similarity(existing, name) >= threshold
        ):
            return node_id
    return None


def validate_graph_enhancements(
    graph: nx.DiGraph,
    enhancements: dict[str, Any],
) -> dict[str, Any]:
    """Annotate LLM-drafted graph enhancements against the real graph.

    Node drafts that fuzzy-match an existing same-type node get ``duplicate_of``
    so the review/apply path proposes a merge instead of a blind add; edge
    endpoints pointing at a duplicate draft are remapped to the existing node;
    relations outside ALLOWED_RELATIONS become RELATED_TO with the original kept
    in ``relation_raw``.
    """
    nodes = list(enhancements.get("nodes", []) or [])
    edges = list(enhancements.get("edges", []) or [])
    remap: dict[tuple[str, str], str] = {}

    for node in nodes:
        ntype = str(node.get("type") or "").strip()
        name = str(node.get("name") or "").strip()
        if not ntype or not name:
            continue
        existing = _find_existing_duplicate(graph, ntype, name)
        if existing:
            node["duplicate_of"] = existing
            remap[(ntype, name)] = existing
            logger.info(f"Delta validation: '{ntype}:{name}' duplicates '{existing}'")

    for edge in edges:
        for side in ("source", "target"):
            key = (
                str(edge.get(f"{side}_type") or "").strip(),
                str(edge.get(f"{side}_name") or "").strip(),
            )
            if key in remap:
                existing_type, _, existing_name = remap[key].partition(":")
                edge[f"{side}_type"] = existing_type
                edge[f"{side}_name"] = existing_name
        relation = str(edge.get("relation") or "").strip().upper()
        if relation not in ALLOWED_RELATIONS:
            edge["relation_raw"] = edge.get("relation")
            edge["relation"] = "RELATED_TO"

    return {"nodes": nodes, "edges": edges}
