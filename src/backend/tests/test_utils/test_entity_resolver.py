import networkx as nx
import pytest

from app.utils.entity_resolver import EntityResolver


def _make_graph(*nodes: tuple[str, str, str]) -> nx.DiGraph:
    g = nx.DiGraph()
    for nid, ntype, name in nodes:
        g.add_node(nid, type=ntype, name=name)
    return g


def test_exact_name_match_returns_existing_node():
    g = _make_graph(("Skill:Python", "Skill", "Python"))
    resolver = EntityResolver(fuzzy_threshold=0.85)
    result = resolver.find_existing_node(g, "Skill", "Python")
    assert result == "Skill:Python"


def test_fuzzy_name_no_match_for_different_language():
    g = _make_graph(("Skill:NLP", "Skill", "NLP"))
    resolver = EntityResolver(fuzzy_threshold=0.85)
    result = resolver.find_existing_node(g, "Skill", "자연어처리(NLP)")
    assert result is None


def test_type_mismatch_returns_none():
    g = _make_graph(("Project:Python", "Project", "Python"))
    resolver = EntityResolver(fuzzy_threshold=0.85)
    result = resolver.find_existing_node(g, "Skill", "Python")
    assert result is None


def test_no_match_returns_none():
    g = _make_graph(("Skill:PyTorch", "Skill", "PyTorch"))
    resolver = EntityResolver(fuzzy_threshold=0.85)
    result = resolver.find_existing_node(g, "Skill", "TensorFlow")
    assert result is None


def test_high_fuzzy_match_found():
    g = _make_graph(("Skill:딥러닝", "Skill", "딥러닝"))
    resolver = EntityResolver(fuzzy_threshold=0.85)
    # "딥 러닝" vs "딥러닝" — SequenceMatcher ratio ~0.89
    result = resolver.find_existing_node(g, "Skill", "딥 러닝")
    assert result == "Skill:딥러닝"


@pytest.mark.asyncio
async def test_async_find_falls_back_to_sync_when_no_embedding_url(monkeypatch):
    import app.utils.entity_resolver as mod
    monkeypatch.setattr(mod.config, "EMBEDDING_BASE_URL", "")
    g = _make_graph(("Skill:Python", "Skill", "Python"))
    resolver = EntityResolver(fuzzy_threshold=0.85)
    result = await resolver.find_existing_node_async(g, "Skill", "Python")
    assert result == "Skill:Python"
