from __future__ import annotations

from difflib import SequenceMatcher
import re

import networkx as nx

from app.config import config
from app.utils.entity_normalization import are_acronym_variants
from app.utils.logger import get_logger
from app.utils.routing import Role
from app.utils.semantic_dedup import _merge_node

logger = get_logger(__name__)

_SKIP_TYPES = {"Category"}
_LOW = 0.60
_BATCH_SIZE = 20


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _find_candidate_pairs(
    graph: nx.DiGraph, low: float, high: float
) -> list[tuple[str, str, str, str, str]]:
    """Return (id_a, id_b, name_a, name_b, type) for same-type pairs with similarity in [low, high)."""
    type_groups: dict[str, list[tuple[str, str, str]]] = {}
    for node_id, data in graph.nodes(data=True):
        ntype = data.get("type", "")
        if ntype in _SKIP_TYPES or not ntype:
            continue
        name = data.get("name", "").strip()
        if not name:
            continue
        desc = (data.get("description") or "").strip()
        type_groups.setdefault(ntype, []).append((node_id, name, desc))

    pairs: list[tuple[str, str, str, str, str]] = []
    for ntype, nodes in type_groups.items():
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                id_a, name_a, _ = nodes[i]
                id_b, name_b, _ = nodes[j]
                desc_a = nodes[i][2]
                desc_b = nodes[j][2]
                sim = _similarity(name_a, name_b)
                if (
                    low <= sim < high
                    or are_acronym_variants(name_a, name_b)
                    or _contextual_match(name_a, desc_a, name_b, desc_b)
                ):
                    pairs.append((id_a, id_b, name_a, name_b, ntype))
    return pairs


def _contextual_match(name_a: str, desc_a: str, name_b: str, desc_b: str) -> bool:
    """Catch cross-language/equivalent labels surfaced in descriptions without a fixed alias table."""
    norm_name_a = _normalize_text(name_a)
    norm_name_b = _normalize_text(name_b)
    norm_desc_a = _normalize_text(desc_a)
    norm_desc_b = _normalize_text(desc_b)
    if len(norm_name_a) >= 8 and norm_name_a in norm_desc_b:
        return True
    if len(norm_name_b) >= 8 and norm_name_b in norm_desc_a:
        return True

    tokens_a = _content_tokens(f"{name_a} {desc_a}")
    tokens_b = _content_tokens(f"{name_b} {desc_b}")
    if not tokens_a or not tokens_b:
        return False
    overlap = tokens_a & tokens_b
    return len(overlap) >= 2 and len(overlap) / min(len(tokens_a), len(tokens_b)) >= 0.5


def _normalize_text(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", " ", (value or "").lower()).strip()


def _content_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[0-9a-z가-힣]{3,}", (value or "").lower())
        if token not in {"the", "and", "with", "using", "based", "for"}
    }


async def llm_dedup(graph: nx.DiGraph, llm_client=None) -> tuple[nx.DiGraph, int]:
    """Use LLM to confirm and merge near-duplicate nodes missed by fuzzy/embedding dedup.

    Targets same-type pairs with name similarity in [0.60, FUZZY_MATCH_THRESHOLD).
    Person nodes are included so cross-lingual variants like '인소영' / '인소영 교수님' can be merged.
    """
    if llm_client is None:
        from app.utils.llm_client import LLMClient
        # Graph extraction stays local, but graph maintenance follows the
        # configured backend so higher-quality models can judge merge decisions.
        llm_client = LLMClient.for_role(Role.DEDUP)

    candidates = _find_candidate_pairs(graph, _LOW, config.FUZZY_MATCH_THRESHOLD)
    if not candidates:
        return graph, 0

    logger.info(f"LLM dedup: evaluating {len(candidates)} candidate pair(s)")

    merge_pairs: list[tuple[str, str]] = []
    for start in range(0, len(candidates), _BATCH_SIZE):
        batch = candidates[start : start + _BATCH_SIZE]
        decisions = await _ask_llm_batch(llm_client, batch)
        for idx, (id_a, id_b, *_) in enumerate(batch):
            if decisions.get(idx, False):
                merge_pairs.append((id_a, id_b))

    merged = 0
    for id_a, id_b in merge_pairs:
        if id_a not in graph or id_b not in graph:
            continue
        if graph.degree(id_a) >= graph.degree(id_b):
            canonical, dup = id_a, id_b
        else:
            canonical, dup = id_b, id_a
        dup_name = graph.nodes[dup].get("name", dup)
        _merge_node(graph, canonical, dup)
        merged += 1
        logger.info(
            f"LLM dedup: merged '{graph.nodes[canonical].get('name')}'"
            f" ← '{dup_name}' ({graph.nodes[canonical].get('type')})"
        )

    if merged:
        logger.info(f"LLM deduplication: merged {merged} node(s)")
    return graph, merged


async def _ask_llm_batch(
    llm_client, batch: list[tuple[str, str, str, str, str]]
) -> dict[int, bool]:
    """Ask LLM whether each pair represents the same entity. Returns {index: merge_bool}."""
    pairs_text = "\n".join(
        f'{i}. [{ntype}] "{name_a}" vs "{name_b}"'
        for i, (_, _, name_a, name_b, ntype) in enumerate(batch)
    )
    messages = [
        {
            "role": "user",
            "content": (
                "You are reviewing a knowledge graph for duplicate nodes.\n"
                "For each pair, decide if they refer to the SAME concept/entity and should be merged.\n\n"
                f"Pairs:\n{pairs_text}\n\n"
                "Respond with JSON only:\n"
                '{"decisions": [{"id": 0, "merge": true}, {"id": 1, "merge": false}, ...]}\n\n'
                "Rules:\n"
                "- merge=true if clearly the same thing (Korean/English equivalents count as same)\n"
                "- For Person type: merge=true only if they are the same individual "
                "(e.g. '인소영' and '인소영 교수님' are the same person)\n"
                "- merge=false if unsure or they are distinct concepts\n"
            ),
        }
    ]
    try:
        result = await llm_client.chat_json(messages)
        return {
            d["id"]: bool(d.get("merge", False))
            for d in result.get("decisions", [])
            if "id" in d
        }
    except Exception as e:
        logger.warning(f"LLM dedup batch failed: {e}")
        return {}
