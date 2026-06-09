from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

import networkx as nx

from app.services.autoresearch import generate_autoresearch_candidates


DEFAULT_MAX_REVIEW_CANDIDATES = 8


def build_graph_review_workflow(
    graph: nx.Graph,
    chunks: Iterable[Any] | None = None,
    health: dict[str, Any] | None = None,
    autoresearch_candidates: Iterable[dict[str, Any]] | None = None,
    *,
    project_id: str | None = None,
    max_candidates: int = DEFAULT_MAX_REVIEW_CANDIDATES,
) -> dict[str, Any]:
    """Build a deterministic read-only graph review workflow payload.

    The returned payload is intentionally small and structured for Claude Desktop:
    ProjectOS performs deterministic pre-filtering, then Claude reviews only the
    highest-value weak spots. This function does not call LLMs, search the web, or
    modify the graph.
    """
    chunk_list = list(chunks or [])
    candidate_list = (
        list(autoresearch_candidates)
        if autoresearch_candidates is not None
        else generate_autoresearch_candidates(
            graph,
            chunk_list,
            health,
            max_candidates=max(max_candidates, DEFAULT_MAX_REVIEW_CANDIDATES),
        )
    )
    ordered_candidates = _ordered_candidates(candidate_list)
    targeted_candidates = [
        _summarize_candidate(candidate)
        for candidate in ordered_candidates[:max(0, max_candidates)]
    ]
    metrics = _evaluation_metrics(graph, chunk_list, health, ordered_candidates)

    return {
        "macro": "projectos-review-graph",
        "project_id": project_id,
        "read_only": True,
        "description": (
            "Prepare a deterministic graph quality review plan for Claude Desktop "
            "without changing ProjectOS state."
        ),
        "inputs": {
            "graph": {
                "node_count": graph.number_of_nodes(),
                "edge_count": graph.number_of_edges(),
                "type_counts": _type_counts(graph),
            },
            "chunk_count": len(chunk_list),
            "health_supplied": health is not None,
            "autoresearch_candidate_count": len(ordered_candidates),
        },
        "mode_comparison": {
            "A_full_claude_review": {
                "label": "Full Claude review",
                "scope": "Ask Claude to inspect the full graph and source context.",
                "strength": "Broad coverage when token budget is not a constraint.",
                "risk": "High token use and less reproducible candidate selection.",
                "recommended": False,
            },
            "B_deterministic_prefilter_targeted_claude_review": {
                "label": "Deterministic pre-filter + targeted Claude review",
                "scope": "Review only ranked duplicates, missing evidence, sparse nodes, and weak components.",
                "strength": "Stable, lower-token review queue with explicit evidence gaps.",
                "risk": "May miss issues outside the deterministic health and candidate signals.",
                "recommended": True,
            },
        },
        "evaluation_metrics": metrics,
        "targeted_review_candidates": targeted_candidates,
        "recommended_checklist": _recommended_checklist(metrics),
        "next_steps": _next_steps(targeted_candidates),
        "token_saving_guidance": _token_saving_guidance(
            metrics,
            len(targeted_candidates),
            len(ordered_candidates),
        ),
    }


def _ordered_candidates(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda candidate: (
            -int(candidate.get("priority") or 0),
            str(candidate.get("id") or ""),
        ),
    )


def _summarize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    node_ids = _string_list(candidate.get("node_ids"))
    if not node_ids and candidate.get("node_id"):
        node_ids = [str(candidate["node_id"])]

    names = _string_list(candidate.get("names"))
    if not names and candidate.get("name"):
        names = [str(candidate["name"])]

    evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
    source_files = _sorted_unique(
        candidate.get("source_files") or evidence.get("source_files") or []
    )

    return {
        "id": str(candidate.get("id") or ""),
        "kind": str(candidate.get("kind") or "review"),
        "priority": int(candidate.get("priority") or 0),
        "node_ids": node_ids,
        "names": names,
        "types": _string_list(candidate.get("types") or candidate.get("type")),
        "reason": str(candidate.get("reason") or ""),
        "suggested_query": str(candidate.get("suggested_query") or ""),
        "source_files": source_files[:5],
        "review_focus": _review_focus(candidate),
    }


def _evaluation_metrics(
    graph: nx.Graph,
    chunks: list[Any],
    health: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = health.get("summary", {}) if health else {}
    by_kind = Counter(str(candidate.get("kind") or "unknown") for candidate in candidates)
    by_reason = Counter(_candidate_category(candidate) for candidate in candidates)
    graph_missing_source_count = sum(
        1
        for _node_id, data in graph.nodes(data=True)
        if data.get("type") != "Category" and not data.get("source_files")
    )
    missing_source_count = max(
        int(summary.get("missing_source_node_count", 0)),
        graph_missing_source_count,
    )

    return {
        "node_count": int(summary.get("total_nodes", graph.number_of_nodes())),
        "edge_count": int(summary.get("total_edges", graph.number_of_edges())),
        "chunk_count": len(chunks),
        "candidate_count": len(candidates),
        "candidate_kind_counts": dict(sorted(by_kind.items())),
        "candidate_signal_counts": dict(sorted(by_reason.items())),
        "isolated_count": int(summary.get("isolated_count", 0)),
        "component_count": int(summary.get("component_count", 0)),
        "duplicate_pair_count": int(summary.get("duplicate_pair_count", 0)),
        "hub_count": int(summary.get("hub_count", 0)),
        "missing_source_node_count": int(missing_source_count),
        "coverage_ratio": _coverage_ratio(graph),
    }


def _recommended_checklist(metrics: dict[str, Any]) -> list[dict[str, str]]:
    checklist = [
        {
            "id": "confirm-duplicates",
            "item": "Confirm duplicate candidates before merging or deleting nodes.",
        },
        {
            "id": "verify-source-evidence",
            "item": "Check every targeted candidate has enough source_files or chunk evidence.",
        },
        {
            "id": "inspect-weak-links",
            "item": "Inspect isolated, sparse, and weak-component nodes for missing relationships.",
        },
        {
            "id": "record-decisions",
            "item": "Write review decisions as a proposed patch or note; do not mutate the graph in this macro.",
        },
    ]
    if metrics["candidate_count"] == 0:
        checklist.insert(0, {
            "id": "sample-graph",
            "item": "No candidates were produced; spot-check representative high-degree nodes manually.",
        })
    return checklist


def _next_steps(candidates: list[dict[str, Any]]) -> list[str]:
    if not candidates:
        return [
            "Run a small manual Claude review on graph summary metrics.",
            "Re-run health and autoresearch candidate generation after new graph changes.",
        ]
    return [
        "Send only targeted_review_candidates plus source snippets to Claude Desktop.",
        "Ask Claude to classify each candidate as keep, merge, enrich, or ignore.",
        "Convert accepted decisions into a separate explicit graph patch after review.",
    ]


def _token_saving_guidance(
    metrics: dict[str, Any],
    targeted_count: int,
    total_candidate_count: int,
) -> dict[str, Any]:
    skipped_count = max(0, total_candidate_count - targeted_count)
    return {
        "preferred_mode": "B_deterministic_prefilter_targeted_claude_review",
        "send_to_claude": [
            "mode_comparison",
            "evaluation_metrics",
            "targeted_review_candidates",
            "recommended_checklist",
        ],
        "omit_from_claude": [
            "full graph JSON unless a candidate requires local neighborhood inspection",
            "raw chunks unrelated to targeted candidates",
            "low-priority candidates beyond max_candidates",
        ],
        "candidate_window": {
            "targeted_count": targeted_count,
            "skipped_low_priority_count": skipped_count,
        },
        "estimated_focus_ratio": (
            round(targeted_count / metrics["node_count"], 3)
            if metrics["node_count"] else 0.0
        ),
    }


def _review_focus(candidate: dict[str, Any]) -> str:
    category = _candidate_category(candidate)
    if category == "duplicate":
        return "Decide whether similarly named nodes represent the same entity."
    if category == "missing_source":
        return "Find or request source evidence before trusting this node."
    if category == "isolated":
        return "Look for missing graph relationships or confirm this is intentionally standalone."
    if category in {"sparse_node", "weak_component"}:
        return "Check whether the entity has missing relationships to better connected nodes."
    return "Review the candidate reason and evidence for graph quality impact."


def _candidate_category(candidate: dict[str, Any]) -> str:
    cid = str(candidate.get("id") or "")
    if ":" in cid:
        return cid.split(":", 1)[0]
    return str(candidate.get("kind") or "unknown")


def _coverage_ratio(graph: nx.Graph) -> float:
    non_category = [
        data for _node_id, data in graph.nodes(data=True)
        if data.get("type") != "Category"
    ]
    if not non_category:
        return 0.0
    sourced = sum(1 for data in non_category if data.get("source_files"))
    return round(sourced / len(non_category), 3)


def _type_counts(graph: nx.Graph) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for _node_id, data in graph.nodes(data=True):
        if data.get("type") == "Category":
            continue
        counts[str(data.get("type") or "unknown")] += 1
    return dict(sorted(counts.items()))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _sorted_unique(values: Iterable[Any]) -> list[str]:
    return sorted({str(value) for value in values if value})
