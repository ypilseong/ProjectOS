from unittest.mock import AsyncMock

import networkx as nx
import pytest

from app.utils.entity_canonicalization import canonicalize_entity_names


def _graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node(
        "Skill:자연어처리",
        type="Skill",
        name="자연어처리",
        description="language processing method",
        source_files=["essay.txt"],
    )
    g.add_node(
        "Organization:KAIST",
        type="Organization",
        name="KAIST",
        description="university",
        source_files=["cv.pdf"],
    )
    g.add_node("Person:양필성", type="Person", name="양필성")
    g.add_edge("Person:양필성", "Skill:자연어처리", relation="USES_SKILL")
    return g


@pytest.mark.asyncio
async def test_canonicalize_entity_names_renames_general_concepts_and_keeps_aliases():
    g = _graph()
    mock_client = AsyncMock()
    mock_client.chat_json = AsyncMock(return_value={
        "decisions": [
            {
                "id": 0,
                "canonical_name": "Natural Language Processing",
                "is_proper_noun": False,
                "aliases": ["자연어처리"],
                "confidence": 0.95,
            },
            {
                "id": 1,
                "canonical_name": "KAIST",
                "is_proper_noun": True,
                "aliases": [],
                "confidence": 0.98,
            },
        ]
    })

    result, changed = await canonicalize_entity_names(g, mock_client)

    assert changed == 1
    assert "Skill:자연어처리" not in result
    assert "Skill:Natural Language Processing" in result
    assert result.has_edge("Person:양필성", "Skill:Natural Language Processing")
    assert result.nodes["Skill:Natural Language Processing"]["aliases"] == ["자연어처리"]
    assert "Organization:KAIST" in result


@pytest.mark.asyncio
async def test_canonicalize_entity_names_skips_proper_noun_renames():
    g = nx.DiGraph()
    g.add_node(
        "Institution:KAIST",
        type="Institution",
        name="KAIST",
        description="Korea Advanced Institute of Science and Technology",
    )
    mock_client = AsyncMock()
    mock_client.chat_json = AsyncMock(return_value={
        "decisions": [
            {
                "id": 0,
                "canonical_name": "Korea Advanced Institute of Science and Technology",
                "is_proper_noun": True,
                "aliases": ["KAIST"],
                "confidence": 0.95,
            }
        ]
    })

    result, changed = await canonicalize_entity_names(g, mock_client)

    assert changed == 0
    assert "Institution:KAIST" in result


@pytest.mark.asyncio
async def test_canonicalize_entity_names_merges_into_existing_node():
    g = _graph()
    g.add_node(
        "Skill:Natural Language Processing",
        type="Skill",
        name="Natural Language Processing",
        source_files=["cv.pdf"],
        source_chunk_ids=["a"],
    )
    g.nodes["Skill:자연어처리"]["source_chunk_ids"] = ["b"]
    mock_client = AsyncMock()
    mock_client.chat_json = AsyncMock(return_value={
        "decisions": [
            {
                "id": 0,
                "canonical_name": "Natural Language Processing",
                "is_proper_noun": False,
                "aliases": ["자연어처리"],
                "confidence": 0.95,
            },
            {"id": 1, "canonical_name": "KAIST", "is_proper_noun": True, "confidence": 0.9},
        ]
    })

    result, changed = await canonicalize_entity_names(g, mock_client)

    assert changed == 1
    assert "Skill:자연어처리" not in result
    assert set(result.nodes["Skill:Natural Language Processing"]["source_chunk_ids"]) == {"a", "b"}


@pytest.mark.asyncio
async def test_canonicalize_entity_names_skips_low_confidence():
    g = _graph()
    mock_client = AsyncMock()
    mock_client.chat_json = AsyncMock(return_value={
        "decisions": [
            {
                "id": 0,
                "canonical_name": "Natural Language Processing",
                "confidence": 0.4,
            }
        ]
    })

    result, changed = await canonicalize_entity_names(g, mock_client)

    assert changed == 0
    assert "Skill:자연어처리" in result


@pytest.mark.asyncio
async def test_canonicalize_entity_names_reviews_short_skill_acronyms():
    g = nx.DiGraph()
    g.add_node("Skill:NLP", type="Skill", name="NLP", description="")
    mock_client = AsyncMock()
    mock_client.chat_json = AsyncMock(return_value={
        "decisions": [
            {
                "id": 0,
                "canonical_name": "Natural Language Processing",
                "is_proper_noun": False,
                "aliases": ["NLP"],
                "confidence": 0.95,
            }
        ]
    })

    result, changed = await canonicalize_entity_names(g, mock_client)

    assert changed == 1
    assert "Skill:Natural Language Processing" in result
    assert result.nodes["Skill:Natural Language Processing"]["aliases"] == ["NLP"]
