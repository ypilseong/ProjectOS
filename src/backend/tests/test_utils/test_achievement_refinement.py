from unittest.mock import AsyncMock

import networkx as nx
import pytest

from app.utils.achievement_refinement import refine_achievement_nodes


def _graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node(
        "Achievement:GPA",
        type="Achievement",
        name="Total GPA 4.35/4.50",
        description="",
        source_files=["cv.pdf"],
    )
    g.add_node(
        "Achievement:Motivation",
        type="Achievement",
        name="AI 도구 개발 의향",
        description="Intent to develop AI tools",
        source_files=["essay.txt"],
    )
    g.add_node(
        "Achievement:Project",
        type="Achievement",
        name="LLM-based Lecture Video Chatbot",
        description="Project work",
        source_files=["cv.pdf"],
    )
    g.add_node(
        "Achievement:TOEIC",
        type="Achievement",
        name="TOEIC 7G5",
        description="English exam score",
        source_files=["cv.pdf"],
    )
    g.add_node("Person:양필성", type="Person", name="양필성")
    g.add_edge("Person:양필성", "Achievement:Project", relation="ACHIEVED")
    return g


@pytest.mark.asyncio
async def test_refine_achievement_nodes_keeps_drops_and_retypes():
    g = _graph()
    mock_client = AsyncMock()
    mock_client.chat_json = AsyncMock(return_value={
        "decisions": [
            {"id": 0, "action": "keep"},
            {"id": 1, "action": "drop"},
            {"id": 2, "action": "retype", "target_type": "Project"},
            {"id": 3, "action": "retype", "target_type": "Skill"},
        ]
    })

    result, changed = await refine_achievement_nodes(g, mock_client)

    assert changed == 3
    assert "Achievement:GPA" in result
    assert "Achievement:Motivation" not in result
    assert "Project:LLM-based Lecture Video Chatbot" in result
    assert result.nodes["Project:LLM-based Lecture Video Chatbot"]["type"] == "Project"
    assert "Skill:TOEIC 7G5" in result
    assert result.nodes["Skill:TOEIC 7G5"]["type"] == "Skill"
    assert result.has_edge("Person:양필성", "Project:LLM-based Lecture Video Chatbot")


@pytest.mark.asyncio
async def test_refine_achievement_nodes_handles_llm_failure():
    g = _graph()
    mock_client = AsyncMock()
    mock_client.chat_json = AsyncMock(side_effect=Exception("timeout"))

    result, changed = await refine_achievement_nodes(g, mock_client)

    assert changed == 0
    assert result.number_of_nodes() == g.number_of_nodes()


@pytest.mark.asyncio
async def test_refine_achievement_nodes_keeps_formal_award_even_if_llm_retypes():
    g = nx.DiGraph()
    g.add_node(
        "Achievement:Award",
        type="Achievement",
        name="교내 경진대회 최우수상",
        description="1st place award",
    )
    mock_client = AsyncMock()
    mock_client.chat_json = AsyncMock(return_value={
        "decisions": [{"id": 0, "action": "retype", "target_type": "Project"}]
    })

    result, changed = await refine_achievement_nodes(g, mock_client)

    assert changed == 0
    assert "Achievement:Award" in result
    assert "Project:교내 경진대회 최우수상" not in result


@pytest.mark.asyncio
async def test_refine_achievement_nodes_default_uses_configured_backend(monkeypatch):
    from app.utils.llm_client import _ClaudeCodeBackend

    monkeypatch.setattr("app.config.config.LLM_BACKEND", "claude_code")
    g = _graph()
    captured = {}

    async def fake_ask(llm_client, batch):
        captured["impl"] = llm_client._impl
        return []

    monkeypatch.setattr(
        "app.utils.achievement_refinement._ask_refinement_batch",
        fake_ask,
    )

    await refine_achievement_nodes(g)

    assert isinstance(captured["impl"], _ClaudeCodeBackend)
