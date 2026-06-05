import networkx as nx
import pytest

from app.agents.query_agent import QueryAgent
from app.models.graph import TextChunk


def _graph():
    g = nx.DiGraph()
    g.add_node("Skill:python", type="Skill", name="Python", description="language")
    g.add_node("Skill:fastapi", type="Skill", name="FastAPI", description="web framework")
    g.add_edge("Skill:python", "Skill:fastapi", relation="USES_SKILL")
    return g


@pytest.mark.asyncio
async def test_search_graph_is_async_and_ranks_by_keyword():
    agent = QueryAgent()
    result = await agent._search_graph(_graph(), "python", project_id=None)
    names = [n["name"] for n in result["nodes"]]
    assert "Python" in names


@pytest.mark.asyncio
async def test_find_relevant_chunks_is_async():
    agent = QueryAgent()
    chunks = [
        TextChunk(chunk_id="c1", text="Python is great", source_file="f",
                  file_type="note", page_num=None, char_offset=0),
        TextChunk(chunk_id="c2", text="unrelated", source_file="f",
                  file_type="note", page_num=None, char_offset=0),
    ]
    out = await agent._find_relevant_chunks(chunks, "python", project_id=None)
    assert any("Python" in t for t in out)


@pytest.mark.asyncio
async def test_stream_awaits_hybrid_path(monkeypatch):
    agent = QueryAgent()

    async def fake_stream(messages):
        yield "answer"

    monkeypatch.setattr(agent._llm, "stream", fake_stream)
    chunks = [TextChunk(chunk_id="c1", text="Python", source_file="f",
                        file_type="note", page_num=None, char_offset=0)]
    tokens = [t async for t in agent.stream("python", _graph(), chunks)]
    assert "".join(tokens) == "answer"
