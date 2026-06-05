# Hybrid Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `QueryAgent` retrieval from keyword-only substring matching to hybrid (keyword sparse + BGE-M3 dense, RRF fusion) with build-time embedding cache and graceful fallback.

**Architecture:** Two new modules — `app/utils/hybrid_retrieval.py` (pure scoring/fusion + async search with fallback) and `app/services/retrieval_index.py` (build-time embedding cache as float16 `.npy` + meta JSON). `QueryAgent` node/chunk search call `hybrid_search`. Parse and graph-build pipelines build the indexes best-effort. If `EMBEDDING_BASE_URL` is unset or embedding fails, everything falls back to the current keyword path.

**Tech Stack:** Python, numpy (already a dep), `app.utils.embedding_client.EmbeddingClient` (BGE-M3, OpenAI-compatible), pytest + pytest-asyncio.

---

## File Structure

- **Create** `app/utils/hybrid_retrieval.py` — `keyword_scores`, `rrf_fuse`, `cosine_rank`, `hybrid_search`. Pure functions + one async entry point. No disk I/O except via `retrieval_index.load_index`.
- **Create** `app/services/retrieval_index.py` — `build_chunk_index`, `build_node_index`, `load_index`. Owns `projects/<id>/embeddings/` files.
- **Modify** `app/agents/query_agent.py` — `_search_graph` and `_find_relevant_chunks` become async and delegate ranking to `hybrid_search`; `stream` awaits them.
- **Modify** `app/api/projects.py` — after `chunks.json` write in the parse task, best-effort `build_chunk_index`.
- **Modify** `app/api/graph.py` — after `graph.json` write in `_run_graph`, best-effort `build_node_index` + `build_chunk_index`.
- **Create tests** `tests/test_utils/test_hybrid_retrieval.py`, `tests/test_services/test_retrieval_index.py`, `tests/test_agents/test_query_agent_hybrid.py`.

All commands run from `src/backend/`.

---

## Task 1: Pure scoring + fusion functions

**Files:**
- Create: `app/utils/hybrid_retrieval.py`
- Test: `tests/test_utils/test_hybrid_retrieval.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_utils/test_hybrid_retrieval.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.utils.hybrid_retrieval'`

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_utils/test_hybrid_retrieval.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/utils/hybrid_retrieval.py tests/test_utils/test_hybrid_retrieval.py
git commit -m "feat(retrieval): add keyword/rrf/cosine scoring primitives"
```

---

## Task 2: Embedding index build + load

**Files:**
- Create: `app/services/retrieval_index.py`
- Test: `tests/test_services/test_retrieval_index.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_services/test_retrieval_index.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.retrieval_index'`

- [ ] **Step 3: Write minimal implementation**

```python
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


def load_index(project_id: str, kind: str):
    """Return (matrix, ids) or None. None on missing/stale/corrupt index."""
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_services/test_retrieval_index.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/retrieval_index.py tests/test_services/test_retrieval_index.py
git commit -m "feat(retrieval): add build-time embedding index cache"
```

---

## Task 3: `hybrid_search` async entry with fallback

**Files:**
- Modify: `app/utils/hybrid_retrieval.py`
- Test: `tests/test_utils/test_hybrid_retrieval.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_utils/test_hybrid_retrieval.py
import json
import numpy as np
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_utils/test_hybrid_retrieval.py -k hybrid_search -v`
Expected: FAIL with `AttributeError: module 'app.utils.hybrid_retrieval' has no attribute 'hybrid_search'`

- [ ] **Step 3: Write minimal implementation**

Append to `app/utils/hybrid_retrieval.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_utils/test_hybrid_retrieval.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add app/utils/hybrid_retrieval.py tests/test_utils/test_hybrid_retrieval.py
git commit -m "feat(retrieval): add hybrid_search with keyword fallback"
```

---

## Task 4: Wire QueryAgent to hybrid_search

**Files:**
- Modify: `app/agents/query_agent.py`
- Test: `tests/test_agents/test_query_agent_hybrid.py`

**Context:** `_search_graph` and `_find_relevant_chunks` currently do substring ranking synchronously (`query_agent.py:34-94`). Make both async, delegate ranking to `hybrid_search`, derive `project_id` from `vault_path` basename (invariant: `vault_path == VAULT_DIR/<project_id>`). Keep edge collection, BFS expansion, and prompt building unchanged. `stream()` must `await` the two methods.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agents/test_query_agent_hybrid.py
import networkx as nx
import pytest

from app.agents.query_agent import QueryAgent
from app.models.graph import TextChunk


def _graph():
    g = nx.DiGraph()
    g.add_node("Skill:python", type="Skill", name="Python", description="language")
    g.add_node("Skill:fastapi", type="Skill", name="FastAPI", description="web framework")
    g.add_edge("Skill:python", "Skill:fastapi", relation="USES_SKILL")
    return g


@pytest.mark.asyncio
async def test_search_graph_is_async_and_ranks_by_keyword(monkeypatch):
    agent = QueryAgent()
    result = await agent._search_graph(_graph(), "python", project_id=None)
    names = [n["name"] for n in result["nodes"]]
    assert "Python" in names


@pytest.mark.asyncio
async def test_find_relevant_chunks_is_async(monkeypatch):
    agent = QueryAgent()
    chunks = [
        TextChunk(chunk_id="c1", text="Python is great", source_file="f",
                  file_type="note", page_num=None, char_offset=0),
        TextChunk(chunk_id="c2", text="unrelated", source_file="f",
                  file_type="note", page_num=None, char_offset=0),
    ]
    out = await agent._find_relevant_chunks(chunks, "python", project_id=None)
    assert any("Python" in t for t in out)


@pytest.mark.asyncio
async def test_stream_awaits_hybrid_path(monkeypatch):
    agent = QueryAgent()

    async def fake_stream(messages):
        yield "answer"

    monkeypatch.setattr(agent._llm, "stream", fake_stream)
    chunks = [TextChunk(chunk_id="c1", text="Python", source_file="f",
                        file_type="note", page_num=None, char_offset=0)]
    tokens = [t async for t in agent.stream("python", _graph(), chunks)]
    assert "".join(tokens) == "answer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_agents/test_query_agent_hybrid.py -v`
Expected: FAIL (`_search_graph` is sync / `TypeError: object dict can't be used in 'await' expression`)

- [ ] **Step 3: Write minimal implementation**

In `app/agents/query_agent.py`:

Add import near the top:
```python
from pathlib import Path  # already present
from app.utils.hybrid_retrieval import hybrid_search
```

Change `stream` body (the three retrieval lines) to derive project_id and await:
```python
    async def stream(self, question, graph, chunks, vault_path=None):
        project_id = Path(vault_path).name if vault_path else None
        context = await self._search_graph(graph, question, project_id=project_id)
        relevant_chunks = await self._find_relevant_chunks(
            chunks, question, project_id=project_id)
        wiki_context = self._load_wiki_context(vault_path, question, context)
        prompt = self._build_prompt(question, context, relevant_chunks, wiki_context)
        logger.info(f"QueryAgent: streaming answer for '{question[:50]}'")
        async for token in self._llm.stream([{"role": "user", "content": prompt}]):
            yield token
```

Replace `_search_graph` node-selection block (keep edges/BFS afterward):
```python
    async def _search_graph(self, graph, query, project_id=None):
        items = {
            node_id: f"{data.get('name', '')} {data.get('name', '')} "
                     f"{data.get('description', '') or ''}"
            for node_id, data in graph.nodes(data=True)
        }
        ranked_ids = await hybrid_search(
            query, project_id, "nodes", items, top_n=10)
        matched_nodes = [
            {
                "id": node_id,
                "type": graph.nodes[node_id].get("type"),
                "name": graph.nodes[node_id].get("name", ""),
                "description": graph.nodes[node_id].get("description", "") or "",
            }
            for node_id in ranked_ids if node_id in graph
        ]

        node_ids = {n["id"] for n in matched_nodes}
        connected_edges = []
        for u, v, edata in graph.edges(data=True):
            if u in node_ids or v in node_ids:
                connected_edges.append({
                    "source": graph.nodes[u].get("name", u),
                    "target": graph.nodes[v].get("name", v),
                    "relation": edata.get("relation", ""),
                })

        bfs_nodes = []
        seen_bfs = set(node_ids)
        for node_id in list(node_ids)[:3]:
            for neighbor in list(graph.successors(node_id)) + list(graph.predecessors(node_id)):
                if neighbor not in seen_bfs:
                    seen_bfs.add(neighbor)
                    ndata = graph.nodes[neighbor]
                    bfs_nodes.append({"type": ndata.get("type"), "name": ndata.get("name")})

        return {"nodes": matched_nodes, "edges": connected_edges, "related": bfs_nodes}
```

Note: the node text repeats `name` twice so keyword matches on the name weigh ~2x relative to description, preserving the old name>desc bias.

Replace `_find_relevant_chunks`:
```python
    async def _find_relevant_chunks(self, chunks, query, project_id=None):
        if not query.strip():
            return []
        items = {c.chunk_id: c.text for c in chunks}
        by_id = {c.chunk_id: c.text for c in chunks}
        ranked_ids = await hybrid_search(
            query, project_id, "chunks", items, top_n=3)
        return [by_id[cid] for cid in ranked_ids if cid in by_id]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_agents/test_query_agent_hybrid.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run existing query/chat/mcp tests for regressions**

Run: `python3 -m pytest tests/test_api/test_mcp_api.py tests/test_api -k "chat or query or mcp" -v`
Expected: PASS (no regressions; if any chat test calls `_search_graph` synchronously, update it to await)

- [ ] **Step 6: Commit**

```bash
git add app/agents/query_agent.py tests/test_agents/test_query_agent_hybrid.py
git commit -m "feat(query): route QueryAgent retrieval through hybrid_search"
```

---

## Task 5: Wire pipeline index builds (best-effort)

**Files:**
- Modify: `app/api/projects.py` (parse task, after `chunks.json` write near line 421)
- Modify: `app/api/graph.py` (`_run_graph`, after vault write / graph.json persisted)
- Test: `tests/test_services/test_retrieval_index.py` (add wiring smoke is covered indirectly; add one guard test)

**Context:** `graph.json` is written inside `_run_graph` before vault write (see `app/api/graph.py` around the `nx.node_link_data` persist + `writer.run`). Confirm the exact line where `graph.json` is saved (search `graph.json` in `graph.py`) and insert the node/chunk index build right after a successful save. Both calls are wrapped so a failure never fails the task.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_services/test_retrieval_index.py
@pytest.mark.asyncio
async def test_build_chunk_index_skips_when_chunks_missing(project):
    pid, _ = project
    # no chunks.json written
    result = await retrieval_index.build_chunk_index(pid + "_missing")
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `python3 -m pytest tests/test_services/test_retrieval_index.py::test_build_chunk_index_skips_when_chunks_missing -v`
Expected: PASS (guard already returns None for missing file — this locks the contract the wiring relies on)

- [ ] **Step 3: Add wiring in `app/api/projects.py`**

After the `out.write_text(json.dumps(combined, ...))` block that persists `chunks.json` in the parse task, add:
```python
        try:
            from app.services.retrieval_index import build_chunk_index
            await build_chunk_index(project_id)
        except Exception as e:
            logger.warning(f"chunk index build skipped: {e}")
```
(Use the module's existing logger; if none is imported, add `from app.utils.logger import get_logger` and `logger = get_logger(__name__)` at module top.)

- [ ] **Step 4: Add wiring in `app/api/graph.py`**

In `_run_graph`, immediately after the line that writes `graph.json` to disk (search for `graph.json` write; it is the `nx.node_link_data` persisted output), add:
```python
        try:
            from app.services.retrieval_index import build_node_index, build_chunk_index
            await build_node_index(project_id)
            await build_chunk_index(project_id)
        except Exception as e:
            logger.warning(f"retrieval index build skipped: {e}")
```
If `graph.json` is only written via `ObsidianWriterAgent`/elsewhere, place the build right after `project.status = ProjectStatus.READY` save, where both `graph.json` and `chunks.json` are guaranteed present.

- [ ] **Step 5: Run the build/parse API tests**

Run: `python3 -m pytest tests/test_api/test_projects_api.py tests/test_api/test_graph_api.py -v`
Expected: PASS (index build is best-effort; with `EMBEDDING_BASE_URL` unset in tests it returns None and writes nothing)

- [ ] **Step 6: Commit**

```bash
git add app/api/projects.py app/api/graph.py tests/test_services/test_retrieval_index.py
git commit -m "feat(retrieval): build embedding index on parse and graph build"
```

---

## Task 6: Full regression + handoff update

**Files:**
- Modify: `docs/claude-code-handoff.md`

- [ ] **Step 1: Run the full backend suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (all prior tests + ~17 new). Record the count.

- [ ] **Step 2: Update handoff doc**

Under the `## 2026-06-05 claude-obsidian 비교 개선 (진행 중)` section, change `#1 상태` to완료, listing: new files, wiring points, test count, and the fallback behavior (embedding endpoint optional). Note `#2` as next.

- [ ] **Step 3: Commit**

```bash
git add docs/claude-code-handoff.md
git commit -m "docs: record hybrid retrieval completion (claude-obsidian #1)"
```

---

## Self-Review Notes

- **Spec coverage:** §3.1 retrieval_index (Task 2), §3.2 hybrid_retrieval (Tasks 1+3), §3.3 QueryAgent wiring (Task 4), §3.4 pipeline hooks (Task 5), §5 fallback table (Tasks 2/3 tests), §6 tests (Tasks 1-5). All covered.
- **Fallback invariant:** every embedding path returns None/keyword-only on missing URL or exception — locked by tests in Tasks 2 and 3.
- **Korean:** substring keyword scorer retained as sparse component (Task 1), dense BGE-M3 adds semantic recall.
- **No new deps / no config additions** — reuses `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, numpy.
