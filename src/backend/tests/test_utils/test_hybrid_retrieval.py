# tests/test_utils/test_hybrid_retrieval.py
from app.utils.hybrid_retrieval import keyword_scores, rrf_fuse, cosine_rank
import numpy as np


def test_keyword_scores_counts_token_substring_matches():
    items = {"a": "Python FastAPI", "b": "networkx graph", "c": "java"}
    scores = keyword_scores("python graph", items)
    assert scores["a"] == 1  # "python" in a
    assert scores["b"] == 1  # "graph" in b
    assert "c" not in scores  # no match -> omitted


def test_keyword_scores_ignores_single_char_tokens():
    items = {"a": "x ray python"}
    scores = keyword_scores("x python", items)
    assert scores["a"] == 1  # only "python" counts, "x" is len 1


def test_rrf_fuse_combines_two_rankings():
    fused = rrf_fuse([["a", "b", "c"], ["b", "a", "d"]], k=60)
    # b is rank0+rank1, a is rank1+rank0 -> tie, both above c/d
    assert set(fused[:2]) == {"a", "b"}
    assert "d" in fused and "c" in fused


def test_rrf_fuse_handles_id_in_one_ranking_only():
    fused = rrf_fuse([["a"], ["b"]], k=60)
    assert set(fused) == {"a", "b"}


def test_cosine_rank_orders_by_similarity():
    matrix = np.array([[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]], dtype=np.float16)
    ids = ["x", "y", "z"]
    ranked = cosine_rank([1.0, 0.0], matrix, ids)
    assert ranked[0] == "x"  # identical direction
    assert ranked[-1] == "y"  # orthogonal


import json
import pytest
from app.config import config
from app.utils import hybrid_retrieval
from app.services import retrieval_index


class _FakeEmbedder:
    def __init__(self, vec):
        self.vec = vec

    async def embed(self, texts):
        return [self.vec for _ in texts]


@pytest.mark.asyncio
async def test_hybrid_search_keyword_only_when_no_index(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    items = {"a": "python graph", "b": "java"}
    result = await hybrid_retrieval.hybrid_search(
        "python", "pX", "chunks", items, top_n=5)
    assert result == ["a"]  # only keyword match, no index present


@pytest.mark.asyncio
async def test_hybrid_search_blends_dense_when_index_present(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "BAAI/bge-m3")
    pid = "pY"
    emb = tmp_path / pid / "embeddings"
    emb.mkdir(parents=True)
    # b is dense-similar to the query vector [1,0]; keyword favors a
    np.save(emb / "chunks.npy", np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float16))
    (emb / "chunks_meta.json").write_text(json.dumps(
        {"ids": ["a", "b"], "model": "BAAI/bge-m3", "dim": 2}), encoding="utf-8")
    items = {"a": "python", "b": "serpent reptile"}
    result = await hybrid_retrieval.hybrid_search(
        "python", pid, "chunks", items, top_n=5,
        embedder=_FakeEmbedder([1.0, 0.0]))
    # both surface: a via keyword, b via dense
    assert set(result) == {"a", "b"}


@pytest.mark.asyncio
async def test_hybrid_search_falls_back_when_embed_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "BAAI/bge-m3")
    pid = "pZ"
    emb = tmp_path / pid / "embeddings"
    emb.mkdir(parents=True)
    np.save(emb / "chunks.npy", np.array([[1.0, 0.0]], dtype=np.float16))
    (emb / "chunks_meta.json").write_text(json.dumps(
        {"ids": ["a"], "model": "BAAI/bge-m3", "dim": 2}), encoding="utf-8")

    class Boom:
        async def embed(self, texts):
            raise RuntimeError("down")

    items = {"a": "python", "b": "java"}
    result = await hybrid_retrieval.hybrid_search(
        "python", pid, "chunks", items, top_n=5, embedder=Boom())
    assert result == ["a"]  # keyword-only fallback
