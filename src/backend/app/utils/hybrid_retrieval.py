# app/utils/hybrid_retrieval.py
import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)


def _tokens(query: str) -> list[str]:
    return [t for t in query.lower().split() if len(t) > 1]


def keyword_scores(query: str, items: dict[str, str]) -> dict[str, float]:
    """Token-substring match count per item. Items with 0 matches are omitted.

    Substring (not set intersection) matching handles Korean particles
    (e.g. "Python을" still contains "python").
    """
    tokens = _tokens(query)
    scores: dict[str, float] = {}
    for item_id, text in items.items():
        text_lower = (text or "").lower()
        score = sum(1.0 for t in tokens if t in text_lower)
        if score > 0:
            scores[item_id] = score
    return scores


def rrf_fuse(rankings: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion. score[id] = sum 1/(k + rank). Higher first."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking):
            fused[item_id] = fused.get(item_id, 0.0) + 1.0 / (k + rank)
    return [item_id for item_id, _ in sorted(fused.items(), key=lambda x: -x[1])]


def cosine_rank(query_vec, matrix: np.ndarray, ids: list[str]) -> list[str]:
    """Rank ids by cosine similarity of each matrix row to query_vec."""
    q = np.asarray(query_vec, dtype=np.float32)
    q_norm = q / max(float(np.linalg.norm(q)), 1e-9)
    mat = matrix.astype(np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    mat = mat / np.maximum(norms, 1e-9)
    sims = mat @ q_norm
    order = np.argsort(-sims)
    return [ids[i] for i in order]


async def hybrid_search(query, project_id, kind, items, top_n, embedder=None):
    """Return up to top_n item ids ranked by hybrid keyword+dense relevance.

    Falls back to keyword-only ranking when no index exists or embedding fails.
    `items` is {id: text} for the current corpus; results are restricted to it.
    """
    from app.services.retrieval_index import load_index

    kw = keyword_scores(query, items)
    kw_ranking = [i for i, _ in sorted(kw.items(), key=lambda x: -x[1])]

    loaded = load_index(project_id, kind)
    if loaded is None:
        return kw_ranking[:top_n]

    matrix, ids = loaded
    if embedder is None:
        from app.utils.embedding_client import EmbeddingClient
        embedder = EmbeddingClient()
    try:
        query_vec = (await embedder.embed([query]))[0]
    except Exception as e:
        logger.warning(f"hybrid_search: query embed failed: {e}")
        return kw_ranking[:top_n]

    dense_ranking = cosine_rank(query_vec, matrix, ids)
    fused = rrf_fuse([kw_ranking, dense_ranking])
    fused = [i for i in fused if i in items]
    return fused[:top_n]
