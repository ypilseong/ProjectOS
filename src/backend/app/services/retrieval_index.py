# app/services/retrieval_index.py
import json
from pathlib import Path

import numpy as np

from app.config import config
from app.utils.embedding_client import EmbeddingClient
from app.utils.logger import get_logger

logger = get_logger(__name__)

_BATCH = 64


def _emb_dir(project_id: str) -> Path:
    return Path(config.PROJECTS_DIR) / project_id / "embeddings"


async def _embed_all(texts: list[str]) -> list[list[float]] | None:
    if not config.EMBEDDING_BASE_URL or not texts:
        return None
    client = EmbeddingClient()
    vectors: list[list[float]] = []
    try:
        for i in range(0, len(texts), _BATCH):
            vectors.extend(await client.embed(texts[i:i + _BATCH]))
    except Exception as e:  # best-effort; never break the pipeline
        logger.warning(f"retrieval_index: embedding failed: {e}")
        return None
    return vectors


def _write_index(project_id: str, kind: str, ids: list[str],
                 vectors: list[list[float]]) -> dict:
    arr = np.array(vectors, dtype=np.float16)
    out = _emb_dir(project_id)
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / f"{kind}.npy", arr)
    meta = {
        "ids": ids,
        "model": config.EMBEDDING_MODEL,
        "dim": int(arr.shape[1]) if arr.ndim == 2 else 0,
    }
    (out / f"{kind}_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return {"count": len(ids), "dim": meta["dim"]}


async def build_chunk_index(project_id: str) -> dict | None:
    path = Path(config.PROJECTS_DIR) / project_id / "chunks.json"
    if not path.exists():
        return None
    chunks = json.loads(path.read_text(encoding="utf-8"))
    ids = [c["chunk_id"] for c in chunks]
    texts = [c.get("text", "") for c in chunks]
    vectors = await _embed_all(texts)
    if vectors is None:
        return None
    return _write_index(project_id, "chunks", ids, vectors)


async def build_node_index(project_id: str) -> dict | None:
    path = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    ids = [n["id"] for n in nodes]
    texts = [f"{n.get('name', '')}: {n.get('description', '') or ''}" for n in nodes]
    vectors = await _embed_all(texts)
    if vectors is None:
        return None
    return _write_index(project_id, "nodes", ids, vectors)


def load_index(project_id: str | None, kind: str):
    """Return (matrix, ids) or None. None on missing/stale/corrupt index."""
    if project_id is None:
        return None
    npy = _emb_dir(project_id) / f"{kind}.npy"
    meta_path = _emb_dir(project_id) / f"{kind}_meta.json"
    if not npy.exists() or not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("model") != config.EMBEDDING_MODEL:
            return None
        ids = meta.get("ids", [])
        matrix = np.load(npy)
        if matrix.shape[0] != len(ids):
            return None
        return matrix, ids
    except Exception as e:
        logger.warning(f"retrieval_index: load failed for {kind}: {e}")
        return None
