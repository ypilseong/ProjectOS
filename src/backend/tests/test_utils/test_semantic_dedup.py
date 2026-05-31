import json
import math
from unittest.mock import AsyncMock, patch

import networkx as nx
import pytest

from app.utils.semantic_dedup import (
    deterministic_acronym_dedup,
    merge_user_persons,
    semantic_dedup,
    _merge_node,
)


def _unit_vec(dim: int, idx: int) -> list[float]:
    """Return a unit vector with 1.0 at position idx (orthogonal to others)."""
    v = [0.0] * dim
    v[idx] = 1.0
    return v


def _similar_vec(base: list[float], noise: float = 0.01) -> list[float]:
    """Return a nearly-identical vector (cosine similarity ≈ 1 - noise^2/2)."""
    v = [x + noise if i == 0 else x for i, x in enumerate(base)]
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


def _make_graph(*nodes: tuple[str, str]) -> nx.DiGraph:
    g = nx.DiGraph()
    for ntype, name in nodes:
        g.add_node(f"{ntype}:{name}", type=ntype, name=name, source_files=["f.pdf"])
    return g


# ---------------------------------------------------------------------------
# _merge_node unit tests
# ---------------------------------------------------------------------------

def test_merge_node_redirects_edges():
    g = nx.DiGraph()
    g.add_node("Skill:NLP", type="Skill", name="NLP", source_files=["a.pdf"])
    g.add_node("Skill:자연어처리", type="Skill", name="자연어처리", source_files=["b.pdf"])
    g.add_node("Person:양필성", type="Person", name="양필성", source_files=[])
    g.add_edge("Person:양필성", "Skill:자연어처리", relation="USES_SKILL")

    _merge_node(g, "Skill:NLP", "Skill:자연어처리")

    assert "Skill:자연어처리" not in g
    assert g.has_edge("Person:양필성", "Skill:NLP")
    assert set(g.nodes["Skill:NLP"]["source_files"]) == {"a.pdf", "b.pdf"}


def test_merge_node_preserves_source_chunks():
    g = nx.DiGraph()
    g.add_node("Skill:NLP", type="Skill", name="NLP", source_files=[], source_chunk_ids=["a"])
    g.add_node(
        "Skill:자연어처리",
        type="Skill",
        name="자연어처리",
        source_files=[],
        source_chunk_ids=["b"],
    )

    _merge_node(g, "Skill:NLP", "Skill:자연어처리")

    assert set(g.nodes["Skill:NLP"]["source_chunk_ids"]) == {"a", "b"}


def test_merge_node_does_not_duplicate_existing_edge():
    g = nx.DiGraph()
    g.add_node("Skill:NLP", type="Skill", name="NLP", source_files=[])
    g.add_node("Skill:자연어처리", type="Skill", name="자연어처리", source_files=[])
    g.add_node("Person:A", type="Person", name="A", source_files=[])
    g.add_edge("Person:A", "Skill:NLP", relation="USES_SKILL")
    g.add_edge("Person:A", "Skill:자연어처리", relation="USES_SKILL")

    _merge_node(g, "Skill:NLP", "Skill:자연어처리")

    assert "Skill:자연어처리" not in g
    assert len(list(g.predecessors("Skill:NLP"))) == 1


# ---------------------------------------------------------------------------
# semantic_dedup integration tests (embedding client mocked)
# ---------------------------------------------------------------------------

def test_deterministic_acronym_dedup_merges_full_form_variants():
    g = _make_graph(
        ("Skill", "NLP"),
        ("Skill", "Natural Language Processing"),
        ("Skill", "Python"),
    )
    g.add_node("Person:양필성", type="Person", name="양필성", source_files=[])
    g.add_edge("Person:양필성", "Skill:NLP", relation="USES_SKILL")

    g, merged = deterministic_acronym_dedup(g)

    assert merged == 1
    skill_names = {d["name"] for _, d in g.nodes(data=True) if d.get("type") == "Skill"}
    assert "Natural Language Processing" in skill_names
    assert "NLP" not in skill_names
    nlp_node = next(n for n, d in g.nodes(data=True) if d.get("name") == "Natural Language Processing")
    assert g.has_edge("Person:양필성", nlp_node)

@pytest.mark.asyncio
async def test_dedup_merges_similar_same_type_nodes(monkeypatch):
    monkeypatch.setattr("app.config.config.EMBEDDING_BASE_URL", "http://fake:1234")
    monkeypatch.setattr("app.config.config.SEMANTIC_DEDUP_THRESHOLD", 0.88)

    g = _make_graph(("Skill", "NLP"), ("Skill", "자연어처리"), ("Skill", "Python"))
    g.add_node("Person:양필성", type="Person", name="양필성", source_files=[])
    g.add_edge("Person:양필성", "Skill:자연어처리", relation="USES_SKILL")

    # NLP and 자연어처리 → nearly identical embeddings; Python → orthogonal
    base = _unit_vec(4, 0)
    embeddings = {
        "NLP": base,
        "자연어처리": _similar_vec(base, noise=0.001),  # cosine ≈ 0.9999
        "Python": _unit_vec(4, 1),
    }

    async def fake_embed(texts):
        return [embeddings[t] for t in texts]

    with patch("app.utils.semantic_dedup.EmbeddingClient") as MockClient:
        MockClient.return_value.embed = AsyncMock(side_effect=fake_embed)
        g, merged = await semantic_dedup(g)

    assert merged == 1
    skill_nodes = [n for n, d in g.nodes(data=True) if d.get("type") == "Skill"]
    assert len(skill_nodes) == 2  # NLP and Python remain
    # Edge should be redirected to canonical
    assert any(d.get("type") == "Skill" for _, d in g.nodes(data=True) if g.has_edge("Person:양필성", _))


@pytest.mark.asyncio
async def test_dedup_skips_person_nodes(monkeypatch):
    monkeypatch.setattr("app.config.config.EMBEDDING_BASE_URL", "http://fake:1234")
    monkeypatch.setattr("app.config.config.SEMANTIC_DEDUP_THRESHOLD", 0.88)

    g = _make_graph(("Person", "Pilseong Yang"), ("Person", "양필성"))

    base = _unit_vec(4, 0)
    embeddings = {
        "Pilseong Yang": base,
        "양필성": _similar_vec(base, noise=0.001),
    }

    async def fake_embed(texts):
        return [embeddings[t] for t in texts]

    with patch("app.utils.semantic_dedup.EmbeddingClient") as MockClient:
        MockClient.return_value.embed = AsyncMock(side_effect=fake_embed)
        g, merged = await semantic_dedup(g)

    assert merged == 0
    assert g.number_of_nodes() == 2


@pytest.mark.asyncio
async def test_dedup_skips_when_no_embedding_url(monkeypatch):
    monkeypatch.setattr("app.config.config.EMBEDDING_BASE_URL", "")

    g = _make_graph(("Skill", "NLP"), ("Skill", "자연어처리"))
    g_before = g.number_of_nodes()

    g, merged = await semantic_dedup(g)

    assert merged == 0
    assert g.number_of_nodes() == g_before


@pytest.mark.asyncio
async def test_dedup_does_not_merge_different_types(monkeypatch):
    monkeypatch.setattr("app.config.config.EMBEDDING_BASE_URL", "http://fake:1234")
    monkeypatch.setattr("app.config.config.SEMANTIC_DEDUP_THRESHOLD", 0.88)

    g = _make_graph(("Skill", "NLP"), ("Project", "NLP"))

    base = _unit_vec(4, 0)

    async def fake_embed(texts):
        return [base for _ in texts]

    with patch("app.utils.semantic_dedup.EmbeddingClient") as MockClient:
        MockClient.return_value.embed = AsyncMock(side_effect=fake_embed)
        g, merged = await semantic_dedup(g)

    assert merged == 0
    assert g.number_of_nodes() == 2


# ---------------------------------------------------------------------------
# merge_user_persons tests
# ---------------------------------------------------------------------------

def test_merge_user_persons_merges_name_and_display_name(tmp_path, monkeypatch):
    user_json = tmp_path / "user.json"
    user_json.write_text(json.dumps({"name": "양필성", "display_name": "Pilseong Yang"}))
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    g = _make_graph(("Person", "Pilseong Yang"), ("Person", "양필성"), ("Skill", "Python"))
    g.add_edge("Person:양필성", "Skill:Python", relation="USES_SKILL")

    g, merged = merge_user_persons(g)

    assert merged == 1
    person_nodes = [n for n, d in g.nodes(data=True) if d.get("type") == "Person"]
    assert len(person_nodes) == 1
    # Edge should be redirected to the surviving node
    surviving = person_nodes[0]
    assert g.has_edge(surviving, "Skill:Python")


def test_merge_user_persons_merges_aliases(tmp_path, monkeypatch):
    user_json = tmp_path / "user.json"
    user_json.write_text(json.dumps({
        "name": "양필성",
        "display_name": "Pilseong Yang",
        "aliases": ["Phil"],
    }))
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    g = _make_graph(("Person", "Phil"), ("Person", "양필성"), ("Skill", "Python"))
    g.add_edge("Person:Phil", "Skill:Python", relation="USES_SKILL")

    g, merged = merge_user_persons(g)

    assert merged == 1
    assert "Person:Phil" not in g
    assert "Person:양필성" in g
    assert g.has_edge("Person:양필성", "Skill:Python")


def test_merge_user_persons_skips_when_no_user_json(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(tmp_path / "missing.json"))

    g = _make_graph(("Person", "Pilseong Yang"), ("Person", "양필성"))
    g, merged = merge_user_persons(g)

    assert merged == 0
    assert g.number_of_nodes() == 2


def test_merge_user_persons_skips_when_only_one_variant(tmp_path, monkeypatch):
    user_json = tmp_path / "user.json"
    user_json.write_text(json.dumps({"name": "양필성"}))
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    g = _make_graph(("Person", "양필성"), ("Person", "Pilseong Yang"))
    g, merged = merge_user_persons(g)

    assert merged == 0
    assert g.number_of_nodes() == 2


def test_merge_user_persons_does_not_touch_other_persons(tmp_path, monkeypatch):
    user_json = tmp_path / "user.json"
    user_json.write_text(json.dumps({"name": "양필성", "display_name": "Pilseong Yang"}))
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    g = _make_graph(
        ("Person", "Pilseong Yang"), ("Person", "양필성"), ("Person", "인소영")
    )
    g, merged = merge_user_persons(g)

    assert merged == 1
    person_nodes = [n for n, d in g.nodes(data=True) if d.get("type") == "Person"]
    assert len(person_nodes) == 2  # canonical + 인소영


@pytest.mark.asyncio
async def test_dedup_transitive_merge(monkeypatch):
    """A≈B and B≈C → all three collapse to one canonical node."""
    monkeypatch.setattr("app.config.config.EMBEDDING_BASE_URL", "http://fake:1234")
    monkeypatch.setattr("app.config.config.SEMANTIC_DEDUP_THRESHOLD", 0.88)

    g = _make_graph(("Skill", "A"), ("Skill", "B"), ("Skill", "C"))
    base = _unit_vec(4, 0)
    embeddings = {
        "A": base,
        "B": _similar_vec(base, noise=0.001),
        "C": _similar_vec(base, noise=0.002),
    }

    async def fake_embed(texts):
        return [embeddings[t] for t in texts]

    with patch("app.utils.semantic_dedup.EmbeddingClient") as MockClient:
        MockClient.return_value.embed = AsyncMock(side_effect=fake_embed)
        g, merged = await semantic_dedup(g)

    assert merged == 2
    assert g.number_of_nodes() == 1
