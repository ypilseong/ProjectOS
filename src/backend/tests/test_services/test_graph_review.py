import copy

import networkx as nx
from networkx.readwrite import json_graph

from app.services.graph_review import build_graph_review_workflow
from app.utils.graph_health import run_health_check


class Chunk:
    def __init__(self, text: str, source_file: str):
        self.text = text
        self.source_file = source_file


def _graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("Skill:딥러닝", type="Skill", name="딥러닝", source_files=["deep.pdf"])
    graph.add_node("Skill:딥 러닝", type="Skill", name="딥 러닝", source_files=["deep-alt.pdf"])
    graph.add_node("Project:ProjectOS", type="Project", name="ProjectOS", source_files=["project.md"])
    graph.add_node("Skill:Python", type="Skill", name="Python", source_files=["cv.pdf"])
    graph.add_node("Person:Alice", type="Person", name="Alice", source_files=[])
    graph.add_node("Category:Skills", type="Category", name="Skills", source_files=[])
    graph.add_edge("Project:ProjectOS", "Skill:Python", relation="USES_SKILL")
    graph.add_edge("Category:Skills", "Skill:Python", relation="HAS_MEMBER")
    return graph


def _chunks() -> list[Chunk]:
    return [
        Chunk("Alice contributed to ProjectOS graph review", "notes/alice.md"),
        Chunk("ProjectOS uses Python for graph services", "notes/projectos.md"),
    ]


def test_build_graph_review_workflow_is_deterministic():
    graph = _graph()
    health = run_health_check(graph)

    first = build_graph_review_workflow(graph, _chunks(), health, max_candidates=4)
    second = build_graph_review_workflow(graph, _chunks(), health, max_candidates=4)

    assert first == second
    assert first["macro"] == "projectos-review-graph"
    assert first["read_only"] is True


def test_build_graph_review_workflow_does_not_mutate_inputs():
    graph = _graph()
    chunks = _chunks()
    health = run_health_check(graph)
    before_graph = copy.deepcopy(json_graph.node_link_data(graph))
    before_chunks = [(chunk.text, chunk.source_file) for chunk in chunks]
    before_health = copy.deepcopy(health)

    build_graph_review_workflow(graph, chunks, health)

    assert json_graph.node_link_data(graph) == before_graph
    assert [(chunk.text, chunk.source_file) for chunk in chunks] == before_chunks
    assert health == before_health


def test_payload_contains_candidate_summary_metrics_checklist_and_token_guidance():
    graph = _graph()
    health = run_health_check(graph)

    payload = build_graph_review_workflow(graph, _chunks(), health, max_candidates=3)

    assert set(payload["mode_comparison"]) == {
        "A_full_claude_review",
        "B_deterministic_prefilter_targeted_claude_review",
    }
    assert payload["mode_comparison"]["B_deterministic_prefilter_targeted_claude_review"]["recommended"] is True
    assert payload["evaluation_metrics"]["candidate_count"] >= 1
    assert payload["evaluation_metrics"]["duplicate_pair_count"] >= 1
    assert payload["evaluation_metrics"]["missing_source_node_count"] >= 1
    assert payload["evaluation_metrics"]["coverage_ratio"] < 1
    assert 1 <= len(payload["targeted_review_candidates"]) <= 3
    assert all("review_focus" in item for item in payload["targeted_review_candidates"])
    assert all("source_files" in item for item in payload["targeted_review_candidates"])
    assert {item["id"] for item in payload["recommended_checklist"]} >= {
        "confirm-duplicates",
        "verify-source-evidence",
        "inspect-weak-links",
        "record-decisions",
    }
    assert payload["next_steps"]
    assert payload["token_saving_guidance"]["preferred_mode"] == (
        "B_deterministic_prefilter_targeted_claude_review"
    )
    assert payload["token_saving_guidance"]["candidate_window"]["targeted_count"] == len(
        payload["targeted_review_candidates"]
    )


def test_explicit_autoresearch_candidates_are_ranked_and_limited():
    graph = _graph()
    candidates = [
        {
            "id": "missing_source:Person:Alice",
            "kind": "research",
            "priority": 80,
            "node_id": "Person:Alice",
            "name": "Alice",
            "type": "Person",
            "reason": "Node has no source_files evidence.",
            "source_files": ["notes/alice.md"],
        },
        {
            "id": "duplicate:Skill:A|Skill:B",
            "kind": "review_needed",
            "priority": 100,
            "node_ids": ["Skill:A", "Skill:B"],
            "names": ["A", "B"],
            "types": ["Skill", "Skill"],
            "reason": "Possible duplicate nodes should be reviewed.",
            "source_files": ["b.md", "a.md"],
        },
    ]

    payload = build_graph_review_workflow(
        graph,
        chunks=[],
        health=None,
        autoresearch_candidates=candidates,
        max_candidates=1,
    )

    targeted = payload["targeted_review_candidates"]
    assert [item["id"] for item in targeted] == ["duplicate:Skill:A|Skill:B"]
    assert targeted[0]["source_files"] == ["a.md", "b.md"]
    assert payload["evaluation_metrics"]["candidate_signal_counts"]["duplicate"] == 1
    assert payload["token_saving_guidance"]["candidate_window"]["skipped_low_priority_count"] == 1
