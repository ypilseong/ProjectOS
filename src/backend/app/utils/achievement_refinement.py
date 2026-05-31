from __future__ import annotations

import json
from typing import Any

import networkx as nx

from app.utils.entity_validation import normalize_entity_type
from app.utils.logger import get_logger
from app.utils.semantic_dedup import _merge_node

logger = get_logger(__name__)

_BATCH_SIZE = 20
_RETYPABLE = {"Project", "Skill", "Event", "Publication"}


async def refine_achievement_nodes(graph: nx.DiGraph, llm_client=None) -> tuple[nx.DiGraph, int]:
    """Use the LLM as a schema judge for Achievement nodes.

    Achievement should represent record-like accomplishments in a profile graph
    such as grades, honors, awards, scholarships, competition placements, or
    accepted papers. Certificates and exam names should be retyped as Skill when
    useful. Other extracted accomplishments are retyped or dropped based on
    model judgment.
    """
    items = [
        _node_payload(graph, node_id)
        for node_id, data in graph.nodes(data=True)
        if data.get("type") == "Achievement"
    ]
    if not items:
        return graph, 0

    if llm_client is None:
        from app.utils.llm_client import LLMClient
        # This is a small graph-maintenance pass, so use the configured backend
        # instead of the local-only bulk extraction backend.
        llm_client = LLMClient()

    changed = 0
    for start in range(0, len(items), _BATCH_SIZE):
        batch = items[start : start + _BATCH_SIZE]
        decisions = await _ask_refinement_batch(llm_client, batch)
        for decision in decisions:
            idx = decision.get("id")
            if not isinstance(idx, int) or idx < 0 or idx >= len(batch):
                continue
            node_id = batch[idx]["node_id"]
            if node_id not in graph:
                continue
            action = (decision.get("action") or "keep").strip().lower()
            if action != "keep" and _looks_formal_achievement(batch[idx]):
                logger.info(f"Achievement refinement: kept formal achievement '{batch[idx]['name']}'")
                continue
            if action == "drop":
                graph.remove_node(node_id)
                changed += 1
                logger.info(f"Achievement refinement: dropped '{batch[idx]['name']}'")
            elif action == "retype":
                target_type = normalize_entity_type(decision.get("target_type", ""))
                if target_type in _RETYPABLE:
                    changed += _retype_node(graph, node_id, target_type)

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
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "sources": data.get("source_files", []),
        "neighbors": neighbors[:8],
    }


async def _ask_refinement_batch(llm_client, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = "\n".join(
        f"{idx}. {json.dumps(item, ensure_ascii=False)}"
        for idx, item in enumerate(batch)
    )
    messages = [{
        "role": "user",
        "content": (
            "You are cleaning a profile knowledge graph schema.\n"
            "Review only Achievement nodes. In this graph, Achievement means "
            "record-like accomplishments: GPA/grades, honors, awards, scholarships, "
            "competition placements, accepted publications, or similarly formal "
            "measurable achievements.\n"
            "Certificates and exam names/scores such as TOEIC are NOT Achievement; "
            "retype them as Skill when useful. Motivations, interests, lessons learned, "
            "responsibilities, project participation, ordinary project outputs, goals, "
            "and broad experiences are NOT Achievement.\n\n"
            "For each item choose:\n"
            "- keep: it should remain Achievement\n"
            "- retype: it is a concrete Project, Skill, Event, or Publication instead\n"
            "- drop: it is too vague or not useful as a graph node\n\n"
            f"Items:\n{rows}\n\n"
            "Respond with JSON only:\n"
            '{"decisions":[{"id":0,"action":"keep"},'
            '{"id":1,"action":"retype","target_type":"Project"},'
            '{"id":2,"action":"drop"}]}'
        ),
    }]
    try:
        result = await llm_client.chat_json(messages)
        decisions = result.get("decisions", [])
        return decisions if isinstance(decisions, list) else []
    except Exception as e:
        logger.warning(f"Achievement refinement failed: {e}")
        return []


def _looks_formal_achievement(item: dict[str, Any]) -> bool:
    name = str(item.get("name", "") or "").lower()
    description = str(item.get("description", "") or "").lower()
    text = f"{name} {description}"
    formal_terms = (
        "gpa",
        "grade",
        "honor",
        "award",
        "scholarship",
        "recipient",
        "1st place",
        "2nd place",
        "3rd place",
        "winner",
        "장학",
        "수상",
        "상장",
        "최우수",
        "우수상",
        "장려상",
        "학점",
        "성적",
    )
    exam_terms = ("toeic", "toefl", "ielts", "certificate", "certification", "자격증")
    return any(term in text for term in formal_terms) and not any(
        term in text for term in exam_terms
    )


def _retype_node(graph: nx.DiGraph, node_id: str, target_type: str) -> int:
    data = graph.nodes[node_id]
    name = data.get("name", "")
    new_id = f"{target_type}:{name}"
    if new_id in graph:
        _merge_node(graph, new_id, node_id)
    else:
        nx.relabel_nodes(graph, {node_id: new_id}, copy=False)
        graph.nodes[new_id]["type"] = target_type
    logger.info(f"Achievement refinement: retyped '{name}' as {target_type}")
    return 1
