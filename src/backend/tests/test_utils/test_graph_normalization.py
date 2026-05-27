import networkx as nx

from app.models.graph import EdgeTypeDef, EntityTypeDef, Ontology
from app.utils.graph_normalization import normalize_graph_entity_types, normalize_ontology_types


def test_normalize_ontology_maps_technology_to_skill():
    ontology = Ontology(
        entity_types=[
            EntityTypeDef("Skill", "skills", []),
            EntityTypeDef("Technology", "legacy tech", ["LLM"]),
        ],
        edge_types=[
            EdgeTypeDef("USES_SKILL", "uses", ["Person", "Project"], ["Skill", "Technology"])
        ],
        analysis_summary="summary",
    )

    normalized = normalize_ontology_types(ontology)

    assert [e.name for e in normalized.entity_types] == ["Skill"]
    assert normalized.edge_types[0].target_types == ["Skill"]


def test_normalize_graph_renames_legacy_technology_nodes():
    graph = nx.DiGraph()
    graph.add_node("Technology:LLM", type="Technology", name="LLM", source_files=["a"])
    graph.add_node("Person:A", type="Person", name="A", source_files=[])
    graph.add_edge("Person:A", "Technology:LLM", relation="USES_SKILL")

    graph, changed = normalize_graph_entity_types(graph)

    assert changed == 1
    assert "Technology:LLM" not in graph
    assert graph.nodes["Skill:LLM"]["type"] == "Skill"
    assert graph.has_edge("Person:A", "Skill:LLM")


def test_normalize_graph_merges_technology_into_existing_skill():
    graph = nx.DiGraph()
    graph.add_node("Skill:NLP", type="Skill", name="NLP", source_files=["skill.pdf"])
    graph.add_node("Technology:NLP", type="Technology", name="NLP", source_files=["tech.pdf"])
    graph.add_node("Project:P", type="Project", name="P", source_files=[])
    graph.add_edge("Project:P", "Technology:NLP", relation="USES_SKILL")

    graph, changed = normalize_graph_entity_types(graph)

    assert changed == 1
    assert "Technology:NLP" not in graph
    assert graph.has_edge("Project:P", "Skill:NLP")
    assert set(graph.nodes["Skill:NLP"]["source_files"]) == {"skill.pdf", "tech.pdf"}
