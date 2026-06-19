import networkx as nx

from app.utils.graph_promotion import (
    CAREER_LAYER,
    KNOWLEDGE_LAYER,
    PUBLICATION_LAYER,
    classify_node_layers,
)


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

    # Ownership (DEVELOPED) promotes the project, which in turn promotes its skill.
    assert graph.nodes["Project:ProjectOS"]["layer"] == CAREER_LAYER
    assert graph.nodes["Skill:NetworkX"]["layer"] == CAREER_LAYER


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
