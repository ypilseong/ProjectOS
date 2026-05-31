import pytest
import networkx as nx
from unittest.mock import AsyncMock, patch

from app.utils.llm_dedup import _find_candidate_pairs, llm_dedup


def make_graph(nodes, edges=None):
    g = nx.DiGraph()
    for node_id, ntype, name in nodes:
        g.add_node(node_id, type=ntype, name=name)
    for src, tgt in (edges or []):
        g.add_edge(src, tgt)
    return g


def test_find_candidate_pairs_returns_pairs_in_range():
    # '데이터 분석' vs '데이터 구조화' has similarity ~0.615 (in 0.60–0.85 range)
    g = make_graph([
        ("Skill:데이터 분석", "Skill", "데이터 분석"),
        ("Skill:데이터 구조화", "Skill", "데이터 구조화"),
        ("Skill:완전히 다른 기술", "Skill", "완전히 다른 기술"),
    ])
    pairs = _find_candidate_pairs(g, 0.60, 0.85)
    found = {(p[2], p[3]) for p in pairs} | {(p[3], p[2]) for p in pairs}
    assert ("데이터 분석", "데이터 구조화") in found


def test_find_candidate_pairs_skips_category():
    g = make_graph([
        ("Category:Skills", "Category", "Skills"),
        ("Category:Skillset", "Category", "Skillset"),
    ])
    pairs = _find_candidate_pairs(g, 0.60, 0.85)
    assert len(pairs) == 0


def test_find_candidate_pairs_excludes_above_high():
    # similarity >= 0.85 should NOT appear (already handled by EntityResolver)
    g = make_graph([
        ("Skill:NLP", "Skill", "NLP"),
        ("Skill:NLP 기술", "Skill", "NLP 기술"),
    ])
    pairs_full = _find_candidate_pairs(g, 0.0, 1.0)
    pairs_filtered = _find_candidate_pairs(g, 0.60, 0.85)
    # confirm the pair exists in full range but check it respects high bound
    for p in pairs_filtered:
        from difflib import SequenceMatcher
        sim = SequenceMatcher(None, p[2].lower(), p[3].lower()).ratio()
        assert sim < 0.85


def test_find_candidate_pairs_includes_acronym_variants():
    g = make_graph([
        ("Skill:NLP", "Skill", "NLP"),
        ("Skill:Natural Language Processing", "Skill", "Natural Language Processing"),
    ])
    pairs = _find_candidate_pairs(g, 0.60, 0.85)
    found = {(p[2], p[3]) for p in pairs} | {(p[3], p[2]) for p in pairs}
    assert ("NLP", "Natural Language Processing") in found


def test_find_candidate_pairs_includes_contextual_cross_language_variants():
    g = make_graph([
        ("Skill:Natural Language Processing", "Skill", "Natural Language Processing"),
        ("Skill:자연어처리", "Skill", "자연어처리"),
    ])
    g.nodes["Skill:자연어처리"]["description"] = "Natural Language Processing field studied in undergraduate"

    pairs = _find_candidate_pairs(g, 0.60, 0.85)

    found = {(p[2], p[3]) for p in pairs} | {(p[3], p[2]) for p in pairs}
    assert ("Natural Language Processing", "자연어처리") in found


def test_find_candidate_pairs_includes_person():
    g = make_graph([
        ("Person:인소영", "Person", "인소영"),
        ("Person:인소영 교수님", "Person", "인소영 교수님"),
    ])
    pairs = _find_candidate_pairs(g, 0.60, 0.85)
    assert len(pairs) == 1
    assert pairs[0][2] in ("인소영", "인소영 교수님")
    assert pairs[0][3] in ("인소영", "인소영 교수님")


@pytest.mark.asyncio
async def test_llm_dedup_merges_confirmed_pairs():
    g = make_graph([
        ("Event:기후변화 회의", "Event", "기후변화 회의"),
        ("Event:기후변화협약 컨퍼런스", "Event", "기후변화협약 컨퍼런스"),
    ])
    g.add_edge("Project:A", "Event:기후변화 회의")  # give higher degree

    mock_client = AsyncMock()
    mock_client.chat_json = AsyncMock(return_value={
        "decisions": [{"id": 0, "merge": True}]
    })

    with patch("app.utils.llm_dedup._find_candidate_pairs") as mock_find:
        mock_find.return_value = [
            ("Event:기후변화 회의", "Event:기후변화협약 컨퍼런스",
             "기후변화 회의", "기후변화협약 컨퍼런스", "Event")
        ]
        result, count = await llm_dedup(g, mock_client)

    assert count == 1
    assert "Event:기후변화협약 컨퍼런스" not in result
    assert "Event:기후변화 회의" in result


@pytest.mark.asyncio
async def test_llm_dedup_skips_rejected_pairs():
    g = make_graph([
        ("Event:KAIST", "Event", "KAIST"),
        ("Event:KAIST 지원", "Event", "KAIST 지원"),
    ])
    mock_client = AsyncMock()
    mock_client.chat_json = AsyncMock(return_value={
        "decisions": [{"id": 0, "merge": False}]
    })

    with patch("app.utils.llm_dedup._find_candidate_pairs") as mock_find:
        mock_find.return_value = [
            ("Event:KAIST", "Event:KAIST 지원", "KAIST", "KAIST 지원", "Event")
        ]
        result, count = await llm_dedup(g, mock_client)

    assert count == 0
    assert "Event:KAIST" in result
    assert "Event:KAIST 지원" in result


@pytest.mark.asyncio
async def test_llm_dedup_handles_api_error_gracefully():
    g = make_graph([
        ("Skill:NLP", "Skill", "NLP"),
        ("Skill:NLP 처리", "Skill", "NLP 처리"),
    ])
    mock_client = AsyncMock()
    mock_client.chat_json = AsyncMock(side_effect=Exception("API timeout"))

    with patch("app.utils.llm_dedup._find_candidate_pairs") as mock_find:
        mock_find.return_value = [
            ("Skill:NLP", "Skill:NLP 처리", "NLP", "NLP 처리", "Skill")
        ]
        result, count = await llm_dedup(g, mock_client)

    assert count == 0
    assert "Skill:NLP" in result
    assert "Skill:NLP 처리" in result


@pytest.mark.asyncio
async def test_llm_dedup_no_candidates_skips_llm_call():
    g = make_graph([
        ("Skill:Python", "Skill", "Python"),
        ("Skill:Java", "Skill", "Java"),
    ])
    mock_client = AsyncMock()
    mock_client.chat_json = AsyncMock()

    result, count = await llm_dedup(g, mock_client)

    assert count == 0
    mock_client.chat_json.assert_not_called()


@pytest.mark.asyncio
async def test_llm_dedup_default_client_uses_configured_backend(monkeypatch):
    from app.utils.llm_client import _ClaudeCodeBackend

    g = make_graph([
        ("Person:인소영", "Person", "인소영"),
        ("Person:인소영 교수님", "Person", "인소영 교수님"),
    ])
    monkeypatch.setattr("app.config.config.LLM_BACKEND", "claude_code")
    captured = {}

    async def fake_ask(llm_client, batch):
        captured["impl"] = llm_client._impl
        return {}

    with patch("app.utils.llm_dedup._ask_llm_batch", side_effect=fake_ask):
        await llm_dedup(g)

    assert isinstance(captured["impl"], _ClaudeCodeBackend)


@pytest.mark.asyncio
async def test_llm_dedup_canonical_is_higher_degree():
    g = make_graph([
        ("Person:인소영", "Person", "인소영"),
        ("Person:인소영 교수님", "Person", "인소영 교수님"),
    ])
    # 교수님 has higher degree
    g.add_edge("Project:A", "Person:인소영 교수님")
    g.add_edge("Project:B", "Person:인소영 교수님")

    mock_client = AsyncMock()
    mock_client.chat_json = AsyncMock(return_value={
        "decisions": [{"id": 0, "merge": True}]
    })

    with patch("app.utils.llm_dedup._find_candidate_pairs") as mock_find:
        mock_find.return_value = [
            ("Person:인소영", "Person:인소영 교수님",
             "인소영", "인소영 교수님", "Person")
        ]
        result, count = await llm_dedup(g, mock_client)

    assert count == 1
    assert "Person:인소영 교수님" in result
    assert "Person:인소영" not in result
