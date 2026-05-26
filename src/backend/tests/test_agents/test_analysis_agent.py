import pytest
from unittest.mock import AsyncMock, patch
import networkx as nx
from app.models.graph import TextChunk

MOCK_ISSUES = {
    "summary": "전반적으로 기술 역량은 좋으나 성과 수치가 부족합니다.",
    "issues": [
        {
            "category": "성과 수치",
            "severity": "high",
            "description": "정량적 성과가 없습니다.",
            "suggestion": "수치 기반 성과를 추가하세요.",
        },
        {
            "category": "기술 스택",
            "severity": "medium",
            "description": "최신 기술이 부족합니다.",
            "suggestion": "최신 프레임워크 경험을 추가하세요.",
        },
    ],
}
MOCK_DRAFT = "# 개선된 이력서\n\n## 경력\n수치 기반 성과를 포함한 내용..."


@pytest.fixture
def sample_chunks():
    return [
        TextChunk(
            chunk_id="c1",
            text="Python 개발자입니다. 다수의 프로젝트를 진행했습니다.",
            source_file="cv.pdf",
            file_type="note",
            page_num=1,
            char_offset=0,
        )
    ]


@pytest.fixture
def sample_graph():
    g = nx.DiGraph()
    g.add_node("Person:A", type="Person", name="홍길동")
    g.add_node("Skill:Python", type="Skill", name="Python")
    g.add_edge("Person:A", "Skill:Python", relation="USES_SKILL")
    return g


@pytest.mark.asyncio
async def test_analysis_agent_returns_required_fields(sample_chunks, sample_graph):
    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_ISSUES)), \
         patch.object(agent._llm, "chat", new=AsyncMock(return_value=MOCK_DRAFT)):
        result = await agent.run(sample_chunks, sample_graph)

    assert "summary" in result
    assert "issues" in result
    assert "improved_draft" in result
    assert "generated_at" in result


@pytest.mark.asyncio
async def test_analysis_agent_issues_structure(sample_chunks, sample_graph):
    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_ISSUES)), \
         patch.object(agent._llm, "chat", new=AsyncMock(return_value=MOCK_DRAFT)):
        result = await agent.run(sample_chunks, sample_graph)

    assert len(result["issues"]) == 2
    issue = result["issues"][0]
    assert issue["severity"] in ("high", "medium", "low")
    assert "category" in issue
    assert "description" in issue
    assert "suggestion" in issue


@pytest.mark.asyncio
async def test_analysis_agent_works_without_graph(sample_chunks):
    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_ISSUES)), \
         patch.object(agent._llm, "chat", new=AsyncMock(return_value=MOCK_DRAFT)):
        result = await agent.run(sample_chunks, None)

    assert result["summary"] == MOCK_ISSUES["summary"]
    assert result["improved_draft"] == MOCK_DRAFT


def test_graph_summary_counts_by_type(sample_graph):
    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    summary = agent._graph_summary(sample_graph)
    assert "2" in summary
    assert "Person" in summary
    assert "Skill" in summary


def test_graph_summary_with_none():
    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    assert agent._graph_summary(None) == "그래프 없음"


def test_graph_summary_empty_graph():
    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    assert agent._graph_summary(nx.DiGraph()) == "그래프 없음"


@pytest.mark.asyncio
async def test_analysis_agent_raises_on_empty_chunks():
    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    with pytest.raises(ValueError, match="chunks must not be empty"):
        await agent.run([], None)
