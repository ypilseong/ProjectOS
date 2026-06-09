import networkx as nx

from app.services.autoresearch import generate_autoresearch_candidates


def _candidate(candidates: list[dict], candidate_id: str) -> dict:
    return next(item for item in candidates if item["id"] == candidate_id)


def test_priority_ordering_is_deterministic():
    graph = nx.DiGraph()
    graph.add_node("Skill:딥러닝", type="Skill", name="딥러닝", source_files=["a.pdf"])
    graph.add_node("Skill:딥 러닝", type="Skill", name="딥 러닝", source_files=["b.pdf"])
    graph.add_node("Project:Missing", type="Project", name="Missing", source_files=[])
    graph.add_node("Skill:Rust", type="Skill", name="Rust", source_files=["cv.pdf"])
    graph.add_node("Project:Solo", type="Project", name="Solo", source_files=["p.pdf"])
    graph.add_node("Skill:Python", type="Skill", name="Python", source_files=["cv.pdf"])
    graph.add_edge("Project:Solo", "Skill:Python", relation="USES_SKILL")

    candidates = generate_autoresearch_candidates(graph, min_degree=1)

    priorities = [item["priority"] for item in candidates]
    assert priorities == sorted(priorities, reverse=True)
    assert [item["id"] for item in candidates] == sorted(
        [item["id"] for item in candidates],
        key=lambda cid: (-_candidate(candidates, cid)["priority"], cid),
    )
    assert candidates[0]["kind"] == "review_needed"
    assert candidates[0]["id"].startswith("duplicate:")


def test_isolated_missing_source_sparse_component_and_duplicate_categories():
    graph = nx.DiGraph()
    graph.add_node("Person:Alice", type="Person", name="Alice", source_files=[])
    graph.add_node("Project:ProjectOS", type="Project", name="ProjectOS", source_files=["readme.md"])
    graph.add_node("Skill:Python", type="Skill", name="Python", source_files=["cv.pdf"])
    graph.add_node("Skill:딥러닝", type="Skill", name="딥러닝", source_files=["a.pdf"])
    graph.add_node("Skill:딥 러닝", type="Skill", name="딥 러닝", source_files=["b.pdf"])
    graph.add_edge("Project:ProjectOS", "Skill:Python", relation="USES_SKILL")

    candidates = generate_autoresearch_candidates(
        graph,
        allowed_types={"Person", "Project", "Skill"},
        min_degree=1,
        component_size_threshold=3,
    )
    by_id = {item["id"]: item for item in candidates}

    assert by_id["isolated:Person:Alice"]["kind"] == "research"
    assert by_id["isolated:Person:Alice"]["node_id"] == "Person:Alice"
    assert by_id["missing_source:Person:Alice"]["reason"] == "Node has no source_files evidence."
    assert by_id["sparse_node:Project:ProjectOS"]["evidence"]["degree"] == 1
    assert by_id["weak_component:Project:ProjectOS|Skill:Python"]["node_ids"] == [
        "Project:ProjectOS",
        "Skill:Python",
    ]

    duplicate = next(item for item in candidates if item["id"].startswith("duplicate:"))
    assert duplicate["kind"] == "review_needed"
    assert duplicate["node_ids"] == ["Skill:딥 러닝", "Skill:딥러닝"]
    assert set(duplicate["source_files"]) == {"a.pdf", "b.pdf"}


def test_category_nodes_are_excluded_from_candidates():
    graph = nx.DiGraph()
    graph.add_node("Category:Skills", type="Category", name="Skills", source_files=[])
    graph.add_node("Skill:Rust", type="Skill", name="Rust", source_files=["cv.pdf"])
    graph.add_node("Project:OnlyCategoryLinked", type="Project", name="OnlyCategoryLinked", source_files=["p.pdf"])
    graph.add_edge("Category:Skills", "Project:OnlyCategoryLinked", relation="HAS_MEMBER")

    candidates = generate_autoresearch_candidates(graph, component_size_threshold=2)
    ids = [item["id"] for item in candidates]

    assert all("Category:Skills" not in candidate_id for candidate_id in ids)
    assert "isolated:Project:OnlyCategoryLinked" in ids
    assert "isolated:Skill:Rust" in ids


def test_max_candidates_limit_applies_after_priority_sorting():
    graph = nx.DiGraph()
    graph.add_node("Skill:딥러닝", type="Skill", name="딥러닝", source_files=["a.pdf"])
    graph.add_node("Skill:딥 러닝", type="Skill", name="딥 러닝", source_files=["b.pdf"])
    graph.add_node("Person:Alice", type="Person", name="Alice", source_files=[])
    graph.add_node("Skill:Rust", type="Skill", name="Rust", source_files=["cv.pdf"])

    candidates = generate_autoresearch_candidates(graph, max_candidates=2)

    assert len(candidates) == 2
    assert candidates[0]["id"].startswith("duplicate:")
    assert candidates[1]["id"] == "isolated:Person:Alice"


def test_empty_graph_returns_no_candidates():
    assert generate_autoresearch_candidates(nx.DiGraph()) == []


def test_health_and_chunks_can_supply_evidence():
    graph = nx.DiGraph()
    graph.add_node("Project:ProjectOS", type="Project", name="ProjectOS", source_files=[])
    health = {
        "wiki_graph_lint": {
            "missing_source_nodes": [
                {"node_id": "Project:ProjectOS", "name": "ProjectOS", "type": "Project"}
            ]
        }
    }

    class Chunk:
        text = "ProjectOS builds a graph workspace"
        source_file = "notes.md"

    candidates = generate_autoresearch_candidates(graph, chunks=[Chunk()], health=health)

    candidate = _candidate(candidates, "missing_source:Project:ProjectOS")
    assert candidate["source_files"] == ["notes.md"]
