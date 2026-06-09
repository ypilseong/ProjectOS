# tests/test_services/test_retrieval_index.py
import json
from pathlib import Path

import numpy as np
import pytest

from app.config import config
from app.services import retrieval_index


class FakeEmbedder:
    def __init__(self, mapping):
        self.mapping = mapping

    async def embed(self, texts):
        return [self.mapping[t] for t in texts]


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(config, "EMBEDDING_BASE_URL", "http://fake")
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "BAAI/bge-m3")
    pid = "p1"
    (tmp_path / pid).mkdir()
    return pid, tmp_path


@pytest.mark.asyncio
async def test_build_chunk_index_writes_npy_and_meta(project, monkeypatch):
    pid, root = project
    chunks = [
        {"chunk_id": "c1", "text": "alpha", "source_file": "f", "file_type": "note",
         "page_num": None, "char_offset": 0},
        {"chunk_id": "c2", "text": "beta", "source_file": "f", "file_type": "note",
         "page_num": None, "char_offset": 0},
    ]
    (root / pid / "chunks.json").write_text(json.dumps(chunks), encoding="utf-8")
    embedder = FakeEmbedder({"alpha": [1.0, 0.0], "beta": [0.0, 1.0]})
    monkeypatch.setattr(retrieval_index, "EmbeddingClient", lambda: embedder)

    result = await retrieval_index.build_chunk_index(pid)

    assert result["count"] == 2
    loaded = retrieval_index.load_index(pid, "chunks")
    assert loaded is not None
    matrix, ids = loaded
    assert ids == ["c1", "c2"]
    assert matrix.shape == (2, 2)


@pytest.mark.asyncio
async def test_build_returns_none_without_embedding_url(project, monkeypatch):
    pid, root = project
    monkeypatch.setattr(config, "EMBEDDING_BASE_URL", "")
    (root / pid / "chunks.json").write_text(json.dumps([
        {"chunk_id": "c1", "text": "alpha", "source_file": "f", "file_type": "note",
         "page_num": None, "char_offset": 0}]), encoding="utf-8")
    result = await retrieval_index.build_chunk_index(pid)
    assert result is None
    assert not (root / pid / "embeddings" / "chunks.npy").exists()


@pytest.mark.asyncio
async def test_build_node_index_uses_name_and_description(project, monkeypatch):
    pid, root = project
    graph = {"nodes": [
        {"id": "n1", "name": "Python", "type": "Skill", "description": "language"},
        {"id": "n2", "name": "FastAPI", "type": "Skill", "description": ""},
    ], "links": []}
    (root / pid / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    embedder = FakeEmbedder({"Python: language": [1.0, 0.0], "FastAPI: ": [0.0, 1.0]})
    monkeypatch.setattr(retrieval_index, "EmbeddingClient", lambda: embedder)

    result = await retrieval_index.build_node_index(pid)
    assert result["count"] == 2
    loaded = retrieval_index.load_index(pid, "nodes")
    assert loaded[1] == ["n1", "n2"]


def test_load_index_invalidates_on_model_change(project, monkeypatch):
    pid, root = project
    emb = root / pid / "embeddings"
    emb.mkdir(parents=True)
    np.save(emb / "chunks.npy", np.array([[1.0, 0.0]], dtype=np.float16))
    (emb / "chunks_meta.json").write_text(json.dumps(
        {"ids": ["c1"], "model": "old-model", "dim": 2}), encoding="utf-8")
    assert retrieval_index.load_index(pid, "chunks") is None


def test_load_index_missing_returns_none(project):
    pid, _ = project
    assert retrieval_index.load_index(pid, "chunks") is None


@pytest.mark.asyncio
async def test_build_chunk_index_skips_when_chunks_missing(project):
    pid, _ = project
    result = await retrieval_index.build_chunk_index(pid + "_missing")
    assert result is None
