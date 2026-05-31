from __future__ import annotations

import json
import re
from typing import Any

import networkx as nx

from app.utils.logger import get_logger
from app.utils.semantic_dedup import _merge_node

logger = get_logger(__name__)

_BATCH_SIZE = 20
_REVIEW_TYPES = {"Skill", "Project", "Role", "Institution"}


async def canonicalize_entity_names(graph: nx.DiGraph, llm_client=None) -> tuple[nx.DiGraph, int]:
    """Ask the configured LLM to normalize non-proper entity names.

    The LLM keeps proper nouns and official names as-is, but converts general
    concepts to stable English canonical labels. Original labels are preserved
    in node aliases.
    """
    items = [
        _node_payload(graph, node_id)
        for node_id, data in graph.nodes(data=True)
        if _should_review_node(data)
    ]
    if not items:
        return graph, 0

    if llm_client is None:
        from app.utils.llm_client import LLMClient
        llm_client = LLMClient()

    changed = 0
    for start in range(0, len(items), _BATCH_SIZE):
        batch = items[start : start + _BATCH_SIZE]
        decisions = await _ask_canonicalization_batch(llm_client, batch)
        for decision in decisions:
            idx = decision.get("id")
            if not isinstance(idx, int) or idx < 0 or idx >= len(batch):
                continue
            node_id = batch[idx]["node_id"]
            if node_id not in graph:
                continue
            canonical_name = str(decision.get("canonical_name") or "").strip()
            confidence = float(decision.get("confidence") or 0)
            if not canonical_name or confidence < 0.75:
                continue
            changed += _apply_canonical_name(
                graph,
                node_id,
                canonical_name,
                decision.get("aliases") or [],
                bool(decision.get("is_proper_noun", False)),
            )

    return graph, changed


def _node_payload(graph: nx.DiGraph, node_id: str) -> dict[str, Any]:
    data = graph.nodes[node_id]
    neighbors = []
    for pred in graph.predecessors(node_id):
        neighbors.append({
            "direction": "in",
            "relation": graph.edges[pred, node_id].get("relation", ""),
            "type": graph.nodes[pred].get("type", ""),
            "name": graph.nodes[pred].get("name", pred),
        })
    for succ in graph.successors(node_id):
        neighbors.append({
            "direction": "out",
            "relation": graph.edges[node_id, succ].get("relation", ""),
            "type": graph.nodes[succ].get("type", ""),
            "name": graph.nodes[succ].get("name", succ),
        })
    return {
        "node_id": node_id,
        "type": data.get("type", ""),
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "sources": data.get("source_files", []),
        "neighbors": neighbors[:8],
    }


async def _ask_canonicalization_batch(llm_client, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = "\n".join(
        f"{idx}. {json.dumps(item, ensure_ascii=False)}"
        for idx, item in enumerate(batch)
    )
    messages = [{
        "role": "user",
        "content": (
            "You are normalizing entity names in a profile knowledge graph.\n"
            "Goal: use stable English canonical labels for general concepts, while preserving "
            "proper nouns, official names, and source-specific titles.\n\n"
            "Rules:\n"
            "- Keep proper nouns unchanged: people, institutions, companies, official awards, "
            "official competition names, product/project titles, and certificates.\n"
            "- Rename general concepts, methods, skills, research areas, and generic roles to English.\n"
            "- Do not invent an official English name for a Korean proper noun. If unsure, keep it.\n"
            "- Preserve the original name as an alias when renaming.\n"
            "- Prefer concise noun phrases, e.g. '자연어처리' -> 'Natural Language Processing'.\n"
            "- Use confidence below 0.75 when unsure.\n\n"
            f"Items:\n{rows}\n\n"
            "Respond with JSON only:\n"
            '{"decisions":[{"id":0,"canonical_name":"Natural Language Processing",'
            '"is_proper_noun":false,"aliases":["자연어처리"],"confidence":0.95}]}'
        ),
    }]
    try:
        result = await llm_client.chat_json(messages)
        decisions = result.get("decisions", [])
        return decisions if isinstance(decisions, list) else []
    except Exception as e:
        logger.warning(f"Entity canonicalization failed: {e}")
        return []


def _should_review_node(data: dict) -> bool:
    ntype = data.get("type", "")
    name = str(data.get("name", "") or "").strip()
    if ntype not in _REVIEW_TYPES or not name:
        return False
    if re.search(r"[가-힣]", name):
        return True
    if ntype == "Skill" and re.fullmatch(r"[A-Z]{2,6}", name):
        return True
    # Review generic lowercase English labels like "text data processing", but
    # skip likely proper nouns/product names such as KAIST, TOEIC, ChatGPT.
    alpha = re.sub(r"[^A-Za-z ]+", "", name).strip()
    return bool(alpha and alpha == alpha.lower() and " " in alpha)


def _apply_canonical_name(
    graph: nx.DiGraph,
    node_id: str,
    canonical_name: str,
    aliases: list,
    is_proper_noun: bool,
) -> int:
    data = graph.nodes[node_id]
    current_name = data.get("name", "")
    ntype = data.get("type", "")
    clean_aliases = {
        str(alias).strip()
        for alias in aliases
        if str(alias).strip() and str(alias).strip() != canonical_name
    }
    if current_name and current_name != canonical_name:
        clean_aliases.add(current_name)
    existing_aliases = set(data.get("aliases", []) or [])
    data["aliases"] = sorted(existing_aliases | clean_aliases)
    data["is_proper_noun"] = is_proper_noun

    if is_proper_noun:
        return 0
    if not canonical_name or canonical_name == current_name:
        return 0

    new_id = f"{ntype}:{canonical_name}"
    if new_id in graph:
        graph.nodes[node_id]["name"] = canonical_name
        _merge_node(graph, new_id, node_id)
    else:
        nx.relabel_nodes(graph, {node_id: new_id}, copy=False)
        graph.nodes[new_id]["name"] = canonical_name
    logger.info(f"Entity canonicalization: '{current_name}' -> '{canonical_name}' ({ntype})")
    return 1
