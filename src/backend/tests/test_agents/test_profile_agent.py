import pytest
from unittest.mock import AsyncMock, patch
import networkx as nx


MOCK_PROFILE_RESPONSE = {
    "expertise": ["Machine Learning", "NLP"],
    "skills": ["Python", "PyTorch"],
    "projects": ["ProjectOS"],
    "organizations": ["KAIST"],
    "publications": [],
    "achievements": ["우수 논문상"],
    "persona_summary": "ML 전문 연구자로 NLP와 그래프 AI에 강점이 있다.",
    "timeline": [{"year": 2020, "event": "KAIST 입학"}],
}


@pytest.fixture
def sample_graph():
    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong",
               description="ML 연구자", source_files=["cv.pdf"])
    g.add_node("Skill:Python", type="Skill", name="Python",
               description="프로그래밍 언어", source_files=["cv.pdf"])
    g.add_node("Organization:KAIST", type="Organization", name="KAIST",
               description="한국 과학기술원", source_files=["cv.pdf"])
    g.add_node("Project:ProjectOS", type="Project", name="ProjectOS",
               description="지식 그래프 빌더", source_files=["readme.md"])
    g.add_edge("Person:Yang Pilseong", "Skill:Python", relation="USES_SKILL")
    g.add_edge("Person:Yang Pilseong", "Organization:KAIST", relation="WORKED_AT")
    g.add_edge("Person:Yang Pilseong", "Project:ProjectOS", relation="DEVELOPED")
    return g


@pytest.mark.asyncio
async def test_profile_agent_creates_profile(sample_graph):
    from app.agents.profile_agent import ProfileAgent

    agent = ProfileAgent()
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_PROFILE_RESPONSE)):
        profiles = await agent.run(sample_graph)

    assert len(profiles) == 1
    assert profiles[0].name == "Yang Pilseong"


@pytest.mark.asyncio
async def test_profile_has_correct_fields(sample_graph):
    from app.agents.profile_agent import ProfileAgent

    agent = ProfileAgent()
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_PROFILE_RESPONSE)):
        profiles = await agent.run(sample_graph)

    p = profiles[0]
    assert "Python" in p.skills
    assert "Machine Learning" in p.expertise
    assert p.persona_summary == "ML 전문 연구자로 NLP와 그래프 AI에 강점이 있다."
    assert p.timeline[0]["year"] == 2020


def test_collect_context_includes_neighbors(sample_graph):
    from app.agents.profile_agent import ProfileAgent

    agent = ProfileAgent()
    context = agent._collect_context(sample_graph, "Person:Yang Pilseong")
    assert "Python" in context["skills"]
    assert "KAIST" in context["organizations"]
    assert "ProjectOS" in context["projects"]


def test_empty_graph_returns_no_profiles():
    from app.agents.profile_agent import ProfileAgent
    import asyncio

    agent = ProfileAgent()
    empty_graph = nx.DiGraph()

    async def run_empty():
        return await agent.run(empty_graph)

    profiles = asyncio.run(run_empty())
    assert profiles == []


@pytest.fixture
def two_person_graph():
    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong",
               description="ML researcher", source_files=["cv.pdf"])
    g.add_node("Person:Kim Chulsoo", type="Person", name="Kim Chulsoo",
               description="Advisor", source_files=["cv.pdf"])
    g.add_node("Skill:Python", type="Skill", name="Python",
               description="", source_files=["cv.pdf"])
    g.add_edge("Person:Yang Pilseong", "Skill:Python", relation="USES_SKILL")
    return g


@pytest.mark.asyncio
async def test_profile_agent_filters_by_person_ids(two_person_graph):
    from app.agents.profile_agent import ProfileAgent

    agent = ProfileAgent()
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_PROFILE_RESPONSE)):
        profiles = await agent.run(two_person_graph, person_ids=["Person:Yang Pilseong"])

    assert len(profiles) == 1
    assert profiles[0].name == "Yang Pilseong"


@pytest.mark.asyncio
async def test_profile_agent_returns_all_when_person_ids_is_none(two_person_graph):
    from app.agents.profile_agent import ProfileAgent

    agent = ProfileAgent()
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_PROFILE_RESPONSE)):
        profiles = await agent.run(two_person_graph, person_ids=None)

    assert len(profiles) == 2
