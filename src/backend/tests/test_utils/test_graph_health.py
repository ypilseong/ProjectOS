import networkx as nx
import pytest

from app.utils.graph_health import (
    check_duplicate_candidates,
    check_hub_nodes,
    check_isolated_nodes,
    check_wiki_graph_consistency,
    check_weak_components,
    run_health_check,
)


def _chain_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("A:a", type="Skill", name="a")
    g.add_node("A:b", type="Skill", name="b")
    g.add_node("A:c", type="Skill", name="c")
    g.add_edge("A:a", "A:b", relation="R")
    g.add_edge("A:b", "A:c", relation="R")
    return g


def test_check_isolated_nodes_finds_disconnected():
    g = _chain_graph()
    g.add_node("A:lone", type="Skill", name="lone")
    result = check_isolated_nodes(g)
    assert len(result) == 1
    assert result[0]["node_id"] == "A:lone"


def test_check_isolated_nodes_empty_when_all_connected():
    g = _chain_graph()
    assert check_isolated_nodes(g) == []


def test_check_weak_components_detects_disconnected_subgraph():
    g = _chain_graph()
    g.add_node("B:x", type="Project", name="x")
    g.add_node("B:y", type="Project", name="y")
    g.add_edge("B:x", "B:y", relation="R")
    result = check_weak_components(g)
    assert len(result) == 2


def test_check_weak_components_single_component():
    g = _chain_graph()
    result = check_weak_components(g)
    assert len(result) == 1


def test_check_duplicate_candidates_finds_similar_names():
    g = nx.DiGraph()
    g.add_node("Skill:NLP", type="Skill", name="NLP")
    g.add_node("Skill:자연어처리", type="Skill", name="자연어처리")
    g.add_node("Skill:Python", type="Skill", name="Python")
    result = check_duplicate_candidates(g, threshold=0.9)
    assert all(
        not (p["name_a"] in {"NLP", "Python"} and p["name_b"] in {"NLP", "Python"})
        for p in result
    )


def test_check_duplicate_candidates_finds_near_identical():
    g = nx.DiGraph()
    g.add_node("Skill:딥러닝", type="Skill", name="딥러닝")
    g.add_node("Skill:딥 러닝", type="Skill", name="딥 러닝")
    result = check_duplicate_candidates(g, threshold=0.85)
    assert len(result) >= 1
    pair = result[0]
    assert "name_a" in pair


def test_check_hub_nodes_flags_high_degree():
    g = nx.DiGraph()
    g.add_node("Person:hub", type="Person", name="hub")
    for i in range(25):
        g.add_node(f"Skill:s{i}", type="Skill", name=f"s{i}")
        g.add_edge("Person:hub", f"Skill:s{i}", relation="USES_SKILL")
    result = check_hub_nodes(g, max_degree=20)
    assert any(n["node_id"] == "Person:hub" for n in result)


def test_run_health_check_returns_all_sections():
    g = _chain_graph()
    report = run_health_check(g)
    assert "isolated_nodes" in report
    assert "weak_components" in report
    assert "duplicate_candidates" in report
    assert "hub_nodes" in report
    assert "wiki_graph_lint" in report
    assert "summary" in report


def test_check_wiki_graph_consistency_finds_missing_and_extra_pages(tmp_path):
    g = nx.DiGraph()
    g.add_node("Skill:Python", type="Skill", name="Python", source_files=["cv.pdf"])
    g.add_node("Project:Missing", type="Project", name="Missing", source_files=[])
    g.add_edge("Project:Missing", "Skill:Python", relation="USES_SKILL")

    skills = tmp_path / "Skills"
    skills.mkdir()
    (skills / "Python.md").write_text("# Python\n\n[[Missing]]", encoding="utf-8")
    misc = tmp_path / "Misc"
    misc.mkdir()
    (misc / "Extra.md").write_text("# Extra", encoding="utf-8")

    result = check_wiki_graph_consistency(g, str(tmp_path))

    assert any(item["node_id"] == "Project:Missing" for item in result["graph_nodes_without_pages"])
    assert any(item["page"] == "Misc/Extra.md" for item in result["vault_pages_without_nodes"])
    assert any(item["page"] == "Misc/Extra.md" for item in result["orphan_pages"])
    assert any(item["node_id"] == "Project:Missing" for item in result["missing_source_nodes"])


def test_run_health_check_counts_wiki_lint_issues(tmp_path):
    g = nx.DiGraph()
    g.add_node("Skill:Python", type="Skill", name="Python", source_files=[])

    report = run_health_check(g, vault_path=str(tmp_path))

    assert report["summary"]["graph_nodes_without_pages_count"] == 1
    assert report["summary"]["missing_source_node_count"] == 1
