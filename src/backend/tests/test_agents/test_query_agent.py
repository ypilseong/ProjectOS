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


@pytest.mark.asyncio
async def test_search_graph_finds_matching_nodes(sample_graph):
    from app.agents.query_agent import QueryAgent
    agent = QueryAgent()
    context = await agent._search_graph(sample_graph, "Python 기술")
    node_names = [n["name"] for n in context["nodes"]]
    assert "Python" in node_names


@pytest.mark.asyncio
async def test_search_graph_finds_connected_edges(sample_graph):
    from app.agents.query_agent import QueryAgent
    agent = QueryAgent()
    context = await agent._search_graph(sample_graph, "Yang Pilseong")
    assert len(context["edges"]) > 0


@pytest.mark.asyncio
async def test_search_graph_empty_query(sample_graph):
    from app.agents.query_agent import QueryAgent
    agent = QueryAgent()
    context = await agent._search_graph(sample_graph, "")
    assert isinstance(context["nodes"], list)
    assert isinstance(context["edges"], list)


@pytest.mark.asyncio
async def test_find_relevant_chunks(sample_chunks):
    from app.agents.query_agent import QueryAgent
    agent = QueryAgent()
    relevant = await agent._find_relevant_chunks(sample_chunks, "Python 사용")
    assert len(relevant) > 0
    assert any("Python" in c for c in relevant)


@pytest.mark.asyncio
async def test_find_relevant_chunks_returns_at_most_3(sample_chunks):
    from app.agents.query_agent import QueryAgent
    many_chunks = [
        TextChunk(f"id{i}", f"Python content {i}", "cv.pdf", "cv", i, i)
        for i in range(10)
    ]
    agent = QueryAgent()
    relevant = await agent._find_relevant_chunks(many_chunks, "Python")
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


@pytest.mark.asyncio
async def test_search_graph_finds_english_node_by_english_token():
    import networkx as nx
    from app.agents.query_agent import QueryAgent
    g = nx.DiGraph()
    g.add_node("Skill:Python", type="Skill", name="Python", description="Programming language")
    agent = QueryAgent()
    result = await agent._search_graph(g, "Python 프로젝트")
    assert any(n["name"] == "Python" for n in result["nodes"])


@pytest.mark.asyncio
async def test_search_graph_name_match_scores_higher_than_description_match():
    import networkx as nx
    from app.agents.query_agent import QueryAgent
    g = nx.DiGraph()
    g.add_node("Project:NLP", type="Project", name="NLP 프로젝트", description="builds models")
    g.add_node("Skill:Models", type="Skill", name="Models", description="NLP based models")
    agent = QueryAgent()
    result = await agent._search_graph(g, "NLP")
    assert result["nodes"][0]["name"] == "NLP 프로젝트"


@pytest.mark.asyncio
async def test_search_graph_respects_max_node_limit():
    import networkx as nx
    from app.agents.query_agent import QueryAgent
    g = nx.DiGraph()
    for i in range(20):
        g.add_node(f"Skill:s{i}", type="Skill", name=f"skill_{i}", description="test query")
    agent = QueryAgent()
    result = await agent._search_graph(g, "query")
    assert len(result["nodes"]) <= 10


@pytest.mark.asyncio
async def test_load_wiki_context_reads_index_and_matching_node_page(tmp_path, sample_graph):
    from app.agents.query_agent import QueryAgent

    (tmp_path / "_index.md").write_text("# Graph Index\n\n## Skill\n- Python", encoding="utf-8")
    (tmp_path / "_index.md").write_text("# Graph Index\n\n## Skill\n- Python", encoding="utf-8")
    (tmp_path / "log.md").write_text("# ProjectOS Log\n\n## today graph build", encoding="utf-8")
    skill_dir = tmp_path / "Skills"
    skill_dir.mkdir()
    (skill_dir / "Python.md").write_text("# Python\n\nUsed for ProjectOS.", encoding="utf-8")

    agent = QueryAgent()
    context = await agent._search_graph(sample_graph, "Python")
    wiki = agent._load_wiki_context(str(tmp_path), "Python", context)

    assert "Graph Index" in wiki["index"]
    assert "graph build" in wiki["log"]
    assert wiki["pages"][0]["path"] == "Skills/Python.md"
    assert "Used for ProjectOS" in wiki["pages"][0]["content"]


@pytest.mark.asyncio
async def test_build_prompt_includes_wiki_context(sample_graph):
    from app.agents.query_agent import QueryAgent

    agent = QueryAgent()
    context = await agent._search_graph(sample_graph, "Python")
    prompt = agent._build_prompt(
        "Python?",
        context,
        ["source chunk"],
        {
            "index": "# Graph Index\n- Python",
            "log": "## today graph build",
            "pages": [{"path": "Skills/Python.md", "content": "# Python\npage body"}],
        },
    )

    assert "## Wiki Index" in prompt
    assert "## 최근 Wiki Log" in prompt
    assert "graph build" in prompt
    assert "Skills/Python.md" in prompt
    assert "page body" in prompt
    assert "출처 파일/청크" in prompt
