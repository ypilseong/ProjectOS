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
