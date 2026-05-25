import pytest
from unittest.mock import patch
import networkx as nx
from app.models.graph import TextChunk


@pytest.fixture
def sample_graph():
    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong",
               description="ML 연구자")
    g.add_node("Skill:Python", type="Skill", name="Python",
               description="프로그래밍 언어")
    g.add_node("Project:ProjectOS", type="Project", name="ProjectOS",
               description="지식 그래프 빌더")
    g.add_edge("Person:Yang Pilseong", "Skill:Python", relation="USES_SKILL")
    g.add_edge("Person:Yang Pilseong", "Project:ProjectOS", relation="DEVELOPED")
    return g


@pytest.fixture
def sample_chunks():
    return [
        TextChunk("id1", "Yang Pilseong은 Python을 주로 사용합니다.", "cv.pdf", "cv", 1, 0),
        TextChunk("id2", "ProjectOS는 지식 그래프 시스템입니다.", "readme.md", "note", None, 0),
    ]


def test_search_graph_finds_matching_nodes(sample_graph):
    from app.agents.query_agent import QueryAgent
    agent = QueryAgent()
    context = agent._search_graph(sample_graph, "Python 기술")
    node_names = [n["name"] for n in context["nodes"]]
    assert "Python" in node_names


def test_search_graph_finds_connected_edges(sample_graph):
    from app.agents.query_agent import QueryAgent
    agent = QueryAgent()
    context = agent._search_graph(sample_graph, "Yang Pilseong")
    assert len(context["edges"]) > 0


def test_search_graph_empty_query(sample_graph):
    from app.agents.query_agent import QueryAgent
    agent = QueryAgent()
    context = agent._search_graph(sample_graph, "")
    assert isinstance(context["nodes"], list)
    assert isinstance(context["edges"], list)


def test_find_relevant_chunks(sample_chunks):
    from app.agents.query_agent import QueryAgent
    agent = QueryAgent()
    relevant = agent._find_relevant_chunks(sample_chunks, "Python 사용")
    assert len(relevant) > 0
    assert any("Python" in c for c in relevant)


def test_find_relevant_chunks_returns_at_most_3(sample_chunks):
    from app.agents.query_agent import QueryAgent
    many_chunks = [
        TextChunk(f"id{i}", f"Python content {i}", "cv.pdf", "cv", i, i)
        for i in range(10)
    ]
    agent = QueryAgent()
    relevant = agent._find_relevant_chunks(many_chunks, "Python")
    assert len(relevant) <= 3


@pytest.mark.asyncio
async def test_stream_yields_tokens(sample_graph, sample_chunks):
    from app.agents.query_agent import QueryAgent

    agent = QueryAgent()

    async def mock_stream(*args, **kwargs):
        for token in ["답변", " 내용", " 입니다."]:
            yield token

    with patch.object(agent._llm, "stream", side_effect=mock_stream):
        tokens = []
        async for token in agent.stream("Python 기술?", sample_graph, sample_chunks):
            tokens.append(token)

    assert len(tokens) == 3
    assert "".join(tokens) == "답변 내용 입니다."
