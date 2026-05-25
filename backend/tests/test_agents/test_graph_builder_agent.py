import pytest
from unittest.mock import AsyncMock, patch
import networkx as nx
from app.models.graph import TextChunk, Ontology, EntityTypeDef, EdgeTypeDef


MOCK_EXTRACT = {
    "entities": [
        {"type": "Person", "name": "Yang Pilseong", "description": "ML 연구자"},
        {"type": "Skill", "name": "Python", "description": "프로그래밍 언어"},
    ],
    "relations": [
        {
            "source": "Yang Pilseong",
            "source_type": "Person",
            "target": "Python",
            "target_type": "Skill",
            "relation": "USES_SKILL",
            "confidence": 0.95,
        }
    ],
}


@pytest.fixture
def sample_ontology():
    return Ontology(
        entity_types=[
            EntityTypeDef("Person", "사람", []),
            EntityTypeDef("Skill", "기술", []),
        ],
        edge_types=[EdgeTypeDef("USES_SKILL", "기술 사용", ["Person"], ["Skill"])],
        analysis_summary="test",
    )


@pytest.mark.asyncio
async def test_graph_builder_creates_nodes(sample_ontology):
    from app.agents.graph_builder_agent import GraphBuilderAgent

    agent = GraphBuilderAgent()
    chunks = [TextChunk("id1", "Yang Pilseong은 Python 전문가", "cv.pdf", "cv", 1, 0)]

    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_EXTRACT)):
        graph = await agent.run(chunks, sample_ontology)

    assert "Person:Yang Pilseong" in graph.nodes
    assert "Skill:Python" in graph.nodes
    assert graph.number_of_edges() >= 1


@pytest.mark.asyncio
async def test_graph_edge_has_relation(sample_ontology):
    from app.agents.graph_builder_agent import GraphBuilderAgent

    agent = GraphBuilderAgent()
    chunks = [TextChunk("id1", "test", "cv.pdf", "cv", 1, 0)]

    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_EXTRACT)):
        graph = await agent.run(chunks, sample_ontology)

    edges = list(graph.edges(data=True))
    assert len(edges) >= 1
    assert edges[0][2]["relation"] == "USES_SKILL"
    assert edges[0][2]["confidence"] == 0.95


def test_fuzzy_match_finds_similar():
    from app.agents.graph_builder_agent import GraphBuilderAgent
    import networkx as nx

    agent = GraphBuilderAgent()
    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong")

    # Exact match (different case)
    existing = agent._find_existing_node(g, "Person", "yang pilseong")
    assert existing == "Person:Yang Pilseong"


def test_fuzzy_match_no_match():
    from app.agents.graph_builder_agent import GraphBuilderAgent
    import networkx as nx

    agent = GraphBuilderAgent()
    g = nx.DiGraph()
    g.add_node("Person:Kim Chulsoo", type="Person", name="Kim Chulsoo")

    existing = agent._find_existing_node(g, "Person", "Lee Younghee")
    assert existing is None


def test_fuzzy_match_wrong_type():
    from app.agents.graph_builder_agent import GraphBuilderAgent
    import networkx as nx

    agent = GraphBuilderAgent()
    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong")

    # Same name but wrong type — should not match
    existing = agent._find_existing_node(g, "Skill", "Yang Pilseong")
    assert existing is None


def test_graph_stats():
    from app.agents.graph_builder_agent import GraphBuilderAgent
    import networkx as nx

    agent = GraphBuilderAgent()
    g = nx.DiGraph()
    g.add_node("Person:A", type="Person", name="A")
    g.add_node("Skill:B", type="Skill", name="B")
    g.add_edge("Person:A", "Skill:B", relation="USES_SKILL")

    stats = agent.get_stats(g)
    assert stats.total_nodes == 2
    assert stats.total_edges == 1
    assert stats.nodes_by_type["Person"] == 1
    assert stats.edges_by_type["USES_SKILL"] == 1


def test_save_and_load_graph(tmp_path):
    from app.agents.graph_builder_agent import GraphBuilderAgent
    import networkx as nx
    import json

    agent = GraphBuilderAgent()
    g = nx.DiGraph()
    g.add_node("Person:A", type="Person", name="A", description="test",
               source_files=["cv.pdf"], attributes={})
    path = str(tmp_path / "graph.json")
    agent.save(g, path)

    assert (tmp_path / "graph.json").exists()
    data = json.loads((tmp_path / "graph.json").read_text())
    assert "nodes" in data
