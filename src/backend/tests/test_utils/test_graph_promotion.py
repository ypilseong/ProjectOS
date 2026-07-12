from unittest.mock import patch

import networkx as nx

from app.utils.graph_promotion import (
    CAREER_LAYER,
    KNOWLEDGE_LAYER,
    PUBLICATION_LAYER,
    classify_node_layers,
)

# ---------------------------------------------------------------------------
# Helpers for user-Person–aware tests
# ---------------------------------------------------------------------------
USER_PERSON_ID = "Person:Yang"
USER_PERSON_NAME = "Yang"
_USER_CONFIG_STUB = {"name": USER_PERSON_NAME}


def _graph_with_user_person() -> nx.DiGraph:
    """Return a graph containing the user's own Person node.

    The node has no source_files so it is only recognised as career via
    _load_user_person_ids (backed by load_user_config).  Tests that call
    this helper must patch load_user_config to return _USER_CONFIG_STUB.
    """
    graph = nx.DiGraph()
    graph.add_node(USER_PERSON_ID, type="Person", name=USER_PERSON_NAME)
    return graph


def test_profile_sourced_skill_is_career():
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang", source_files=["cv.pdf"])
    graph.add_node("Skill:Python", type="Skill", name="Python", source_files=["cv.pdf"])
    graph.add_edge("Person:Yang", "Skill:Python", relation="USES_SKILL")

    graph, _ = classify_node_layers(graph, {"cv.pdf": "cv"})

    assert graph.nodes["Person:Yang"]["layer"] == CAREER_LAYER
    assert graph.nodes["Skill:Python"]["layer"] == CAREER_LAYER


def test_paper_topic_skill_stays_knowledge():
    graph = nx.DiGraph()
    graph.add_node("Publication:Paper1", type="Publication", name="Paper1", source_files=["paper.pdf"])
    graph.add_node("Skill:LLM", type="Skill", name="LLM", source_files=["paper.pdf"])
    graph.add_edge("Publication:Paper1", "Skill:LLM", relation="USES_SKILL")

    graph, _ = classify_node_layers(graph, {"paper.pdf": "paper"})

    assert graph.nodes["Publication:Paper1"]["layer"] == PUBLICATION_LAYER
    # A paper-only topic must not be promoted into the career layer.
    assert graph.nodes["Skill:LLM"]["layer"] == KNOWLEDGE_LAYER


def test_user_owned_project_promotes_its_skill():
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang", source_files=["cv.pdf"])
    graph.add_node("Project:ProjectOS", type="Project", name="ProjectOS", source_files=["report.pdf"])
    graph.add_node("Skill:NetworkX", type="Skill", name="NetworkX", source_files=["report.pdf"])
    graph.add_edge("Person:Yang", "Project:ProjectOS", relation="DEVELOPED")
    graph.add_edge("Project:ProjectOS", "Skill:NetworkX", relation="USES_SKILL")

    graph, _ = classify_node_layers(graph, {"cv.pdf": "cv", "report.pdf": "report"})

    # DEVELOPED promotes the project to career.
    assert graph.nodes["Project:ProjectOS"]["layer"] == CAREER_LAYER
    # USES_SKILL from a career Project no longer propagates to career (Task 9):
    # only the user's own Person node may propagate USES_SKILL → career.
    # Person:Yang in this test has no user.json backing (no mock), so
    # Skill:NetworkX remains in the knowledge layer.
    assert graph.nodes["Skill:NetworkX"]["layer"] == KNOWLEDGE_LAYER


def test_unconnected_paper_project_is_not_career():
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang", source_files=["cv.pdf"])
    graph.add_node("Project:SpeculativeIdea", type="Project", name="SpeculativeIdea", source_files=["paper.pdf"])

    graph, _ = classify_node_layers(graph, {"cv.pdf": "cv", "paper.pdf": "paper"})

    # No ownership edge from the user → stays out of the career layer.
    assert graph.nodes["Project:SpeculativeIdea"]["layer"] == KNOWLEDGE_LAYER


def test_meta_nodes_get_no_layer():
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang", source_files=["cv.pdf"])
    graph.add_node("Category:Skills", type="Category", name="Skills")
    graph.add_edge("Person:Yang", "Category:Skills", relation="HAS")

    graph, _ = classify_node_layers(graph, {"cv.pdf": "cv"})

    assert "layer" not in graph.nodes["Category:Skills"]


def test_returns_layer_counts():
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang", source_files=["cv.pdf"])
    graph.add_node("Skill:LLM", type="Skill", name="LLM", source_files=["paper.pdf"])
    graph.add_node("Category:Skills", type="Category", name="Skills")

    graph, counts = classify_node_layers(graph, {"cv.pdf": "cv", "paper.pdf": "paper"})

    assert counts.get(CAREER_LAYER) == 1
    assert counts.get(KNOWLEDGE_LAYER) == 1
    # Meta nodes are excluded from layer counts.
    assert sum(counts.values()) == 2


# ---------------------------------------------------------------------------
# Tests for the restricted USES_SKILL → career propagation policy
# (Task 9: only the user's own Person node may propagate USES_SKILL to career)
# ---------------------------------------------------------------------------

def test_uses_skill_from_user_person_promotes_to_career():
    """USES_SKILL from the user's own Person node must still reach career."""
    graph = _graph_with_user_person()
    graph.add_node("Skill:Python", type="Skill", name="Python")
    graph.add_edge(USER_PERSON_ID, "Skill:Python", relation="USES_SKILL")

    with patch("app.utils.graph_restructure.load_user_config", return_value=_USER_CONFIG_STUB):
        classify_node_layers(graph, {})

    assert graph.nodes["Skill:Python"]["layer"] == "career"


def test_uses_skill_from_career_project_stays_knowledge():
    """USES_SKILL from a career *Project* must NOT promote a Skill to career.

    In the 2026-06-28 production build, 108 of 168 Skills were incorrectly
    promoted via this path.  The new policy allows USES_SKILL career
    propagation only when the source node is the user's own Person node.
    """
    graph = _graph_with_user_person()
    # user owns the project via DEVELOPED (→ career)
    graph.add_node("Project:MyProj", type="Project", name="MyProj")
    graph.add_edge(USER_PERSON_ID, "Project:MyProj", relation="DEVELOPED")
    # that project uses a skill mentioned only in a paper
    graph.add_node("Skill:CIB", type="Skill", name="CIB")
    graph.add_edge("Project:MyProj", "Skill:CIB", relation="USES_SKILL")

    with patch("app.utils.graph_restructure.load_user_config", return_value=_USER_CONFIG_STUB):
        classify_node_layers(graph, {})

    assert graph.nodes["Project:MyProj"]["layer"] == "career"
    assert graph.nodes["Skill:CIB"]["layer"] == "knowledge"
