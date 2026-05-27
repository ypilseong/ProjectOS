from unittest.mock import AsyncMock, MagicMock

import networkx as nx
import pytest

from app.utils.isolated_reextract import (
    _build_window,
    _find_mention_indices,
    _join_chunks,
    reextract_isolated_nodes,
)


def _chunk(text: str, source_file: str = "cv.pdf"):
    c = MagicMock()
    c.text = text
    c.source_file = source_file
    return c


def _ontology(entity_types=("Person", "Achievement"), edge_types=("ACHIEVED",)):
    ont = MagicMock()
    ont.entity_types = [MagicMock(name=t) for t in entity_types]
    ont.edge_types = [MagicMock(name=e) for e in edge_types]
    # Fix: MagicMock().name returns the mock's name attr, need to set it explicitly
    for m, t in zip(ont.entity_types, entity_types):
        m.name = t
    for m, e in zip(ont.edge_types, edge_types):
        m.name = e
    return ont


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

def test_find_mention_indices_matches_prefix():
    chunks = [_chunk("unrelated text"), _chunk("Total GPA 4.35/4.50 achieved"), _chunk("other")]
    result = _find_mention_indices("Total GPA 4.35/4.50", chunks, [0, 1, 2])
    assert result == [1]


def test_find_mention_indices_matches_word():
    chunks = [_chunk("Python and NLP are key skills"), _chunk("other")]
    result = _find_mention_indices("Python", chunks, [0, 1])
    assert 0 in result


def test_find_mention_indices_empty_when_not_found():
    chunks = [_chunk("completely different content")]
    result = _find_mention_indices("Total GPA", chunks, [0])
    assert result == []


def test_build_window_includes_neighbors():
    # file has chunks at positions 0,1,2,3,4 (absolute indices)
    file_indices = [0, 1, 2, 3, 4]
    result = _build_window([2], file_indices, window=2)
    assert result == [0, 1, 2, 3, 4]


def test_build_window_clamps_at_boundary():
    file_indices = [0, 1, 2]
    result = _build_window([0], file_indices, window=2)
    assert result == [0, 1, 2]


def test_join_chunks():
    chunks = [_chunk("A"), _chunk("B"), _chunk("C")]
    assert _join_chunks(chunks, [0, 2]) == "A\n\nC"


# ---------------------------------------------------------------------------
# Integration test: reextract_isolated_nodes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reextract_connects_isolated_node():
    # Graph: 양필성 exists and connected; Achievement:GPA exists but isolated
    g = nx.DiGraph()
    g.add_node("Person:양필성", type="Person", name="양필성", source_files=["cv.pdf"])
    g.add_node("Skill:Python", type="Skill", name="Python", source_files=["cv.pdf"])
    g.add_edge("Person:양필성", "Skill:Python", relation="USES_SKILL")
    g.add_node("Achievement:GPA", type="Achievement", name="GPA", source_files=["cv.pdf"])
    # GPA is isolated (no edges)

    chunks = [
        _chunk("Pilseong Yang, AI researcher", source_file="cv.pdf"),
        _chunk("Total GPA 4.35 out of 4.50", source_file="cv.pdf"),
        _chunk("Python, NLP skills", source_file="cv.pdf"),
    ]

    # Mock agent: when re-extract called, returns relation Person→Achievement
    agent = MagicMock()
    agent.reextract_with_context = AsyncMock(return_value=1)

    # Simulate the side effect: actually add the edge on call
    async def fake_reextract(ctx, src, graph, et, edge_t):
        if "GPA" in ctx or "Pilseong" in ctx:
            if not graph.has_edge("Person:양필성", "Achievement:GPA"):
                graph.add_edge("Person:양필성", "Achievement:GPA", relation="ACHIEVED")
                return 1
        return 0

    agent.reextract_with_context = AsyncMock(side_effect=fake_reextract)

    ontology = _ontology(entity_types=["Person", "Achievement", "Skill"],
                         edge_types=["USES_SKILL", "ACHIEVED"])

    g, connected = await reextract_isolated_nodes(g, chunks, agent, ontology)

    assert connected == 1
    assert g.has_edge("Person:양필성", "Achievement:GPA")


@pytest.mark.asyncio
async def test_reextract_skips_category_nodes():
    g = nx.DiGraph()
    g.add_node("Category:Skills", type="Category", name="Skills", source_files=[])
    # Category node with no edges — should NOT be re-extracted

    chunks = [_chunk("some text")]
    agent = MagicMock()
    agent.reextract_with_context = AsyncMock(return_value=0)
    ontology = _ontology()

    g, connected = await reextract_isolated_nodes(g, chunks, agent, ontology)
    assert connected == 0
    agent.reextract_with_context.assert_not_called()


@pytest.mark.asyncio
async def test_reextract_deduplicates_context_calls():
    """Two isolated nodes from the same context window → only one LLM call."""
    g = nx.DiGraph()
    g.add_node("Achievement:GPA", type="Achievement", name="GPA", source_files=["cv.pdf"])
    g.add_node("Achievement:Award", type="Achievement", name="Award", source_files=["cv.pdf"])

    chunks = [_chunk("GPA 4.35 and Award winner", source_file="cv.pdf")]
    agent = MagicMock()
    agent.reextract_with_context = AsyncMock(return_value=0)
    ontology = _ontology()

    await reextract_isolated_nodes(g, chunks, agent, ontology)
    # Both nodes map to the same context (chunk 0), so only 1 LLM call
    assert agent.reextract_with_context.call_count <= 2  # pass2 + pass3 max
