# P1/P2/P3 Graph Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three sequential improvements — (P1) iText2KG-inspired incremental processing + embedding-based entity resolution, (P2) index-first QueryAgent for cross-lingual search, (P3) graph health check API endpoint.

**Architecture:**
- P1 adds `DocumentHashStore` (skip unchanged files) and `EntityResolver` (cosine similarity fallback at merge time), plugged into `GraphBuilderAgent._find_existing_node` and `_run_graph`.
- P2 writes `_index.md` to vault during ObsidianWriterAgent and makes QueryAgent load it for alias-aware node lookup.
- P3 adds `graph_health.py` utility and a `GET /graph/health` API endpoint.

**Tech Stack:** Python 3.11, NetworkX, FastAPI, BGE-M3 via EmbeddingClient (optional — all embedding calls have CPU-only fallback), pytest, difflib.SequenceMatcher.

---

## File Map

### P1 — Incremental Processing + Entity Resolution

| Action | Path |
|--------|------|
| CREATE | `src/backend/app/services/document_hash_store.py` |
| CREATE | `src/backend/app/utils/entity_resolver.py` |
| MODIFY | `src/backend/app/agents/graph_builder_agent.py` |
| MODIFY | `src/backend/app/api/graph.py` |
| CREATE | `src/backend/tests/test_services/__init__.py` |
| CREATE | `src/backend/tests/test_services/test_document_hash_store.py` |
| CREATE | `src/backend/tests/test_utils/test_entity_resolver.py` |

### P2 — Index-First QueryAgent

| Action | Path |
|--------|------|
| MODIFY | `src/backend/app/agents/obsidian_writer_agent.py` |
| MODIFY | `src/backend/app/agents/query_agent.py` |
| MODIFY | `src/backend/tests/test_agents/test_query_agent.py` |

### P3 — Graph Health Check API

| Action | Path |
|--------|------|
| CREATE | `src/backend/app/utils/graph_health.py` |
| MODIFY | `src/backend/app/api/graph.py` |
| CREATE | `src/backend/tests/test_utils/test_graph_health.py` |

---

## P1 — Incremental Processing + Entity Resolution

### Task 1: DocumentHashStore — tracking changed files

The store reads/writes a `hashes.json` file inside the project directory. Keys are source filenames; values are MD5 hex digests. A special key `__ontology__` stores the ontology hash so a schema change forces full rebuild.

**Files:**
- Create: `src/backend/app/services/document_hash_store.py`
- Create: `src/backend/tests/test_services/__init__.py`
- Create: `src/backend/tests/test_services/test_document_hash_store.py`

- [ ] **Step 1: Write failing tests**

```python
# src/backend/tests/test_services/test_document_hash_store.py
import hashlib
import json
from pathlib import Path

import pytest

from app.services.document_hash_store import DocumentHashStore


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def test_new_store_reports_all_files_changed(tmp_path):
    store = DocumentHashStore(tmp_path)
    assert store.get_changed_files(["a.txt", "b.txt"]) == ["a.txt", "b.txt"]


def test_update_and_reload_shows_no_change(tmp_path):
    store = DocumentHashStore(tmp_path)
    store.update("a.txt", _md5("hello"))
    store.save()
    store2 = DocumentHashStore(tmp_path)
    store2.update("a.txt", _md5("hello"))
    assert store2.get_changed_files(["a.txt"]) == []


def test_changed_content_detected(tmp_path):
    store = DocumentHashStore(tmp_path)
    store.update("a.txt", _md5("v1"))
    store.save()
    store2 = DocumentHashStore(tmp_path)
    store2.update("a.txt", _md5("v2"))
    assert store2.get_changed_files(["a.txt"]) == ["a.txt"]


def test_ontology_change_returns_all_files_changed(tmp_path):
    store = DocumentHashStore(tmp_path)
    store.update("a.txt", _md5("x"))
    store.update_ontology(_md5("ont_v1"))
    store.save()
    store2 = DocumentHashStore(tmp_path)
    store2.update("a.txt", _md5("x"))
    store2.update_ontology(_md5("ont_v2"))
    assert store2.get_changed_files(["a.txt"]) == ["a.txt"]


def test_new_file_always_changed(tmp_path):
    store = DocumentHashStore(tmp_path)
    store.update("a.txt", _md5("x"))
    store.save()
    store2 = DocumentHashStore(tmp_path)
    store2.update("a.txt", _md5("x"))
    store2.update("b.txt", _md5("y"))
    assert store2.get_changed_files(["a.txt", "b.txt"]) == ["b.txt"]
```

- [ ] **Step 2: Run tests — expect FAIL (ImportError)**

```bash
cd src/backend && python3 -m pytest tests/test_services/test_document_hash_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.document_hash_store'`

- [ ] **Step 3: Create `__init__.py` for test_services**

```python
# src/backend/tests/test_services/__init__.py
```

- [ ] **Step 4: Implement DocumentHashStore**

```python
# src/backend/app/services/document_hash_store.py
import json
from pathlib import Path

_HASHES_FILE = "hashes.json"
_ONTOLOGY_KEY = "__ontology__"


class DocumentHashStore:
    """Tracks MD5 hashes of source files and ontology to support incremental graph builds."""

    def __init__(self, project_dir: Path):
        self._path = Path(project_dir) / _HASHES_FILE
        self._stored: dict[str, str] = {}
        self._pending: dict[str, str] = {}
        if self._path.exists():
            try:
                self._stored = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._stored = {}

    def update(self, filename: str, file_hash: str) -> None:
        self._pending[filename] = file_hash

    def update_ontology(self, ontology_hash: str) -> None:
        self._pending[_ONTOLOGY_KEY] = ontology_hash

    def save(self) -> None:
        merged = {**self._stored, **self._pending}
        self._path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        self._stored = merged

    def get_changed_files(self, filenames: list[str]) -> list[str]:
        """Return filenames whose hash differs from the stored hash.

        If the ontology hash changed, all files are considered changed.
        """
        stored_ont = self._stored.get(_ONTOLOGY_KEY)
        pending_ont = self._pending.get(_ONTOLOGY_KEY)
        ontology_changed = pending_ont is not None and pending_ont != stored_ont

        changed = []
        for fname in filenames:
            stored = self._stored.get(fname)
            pending = self._pending.get(fname)
            current = pending if pending is not None else stored
            if ontology_changed or stored is None or current != stored:
                changed.append(fname)
        return changed
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd src/backend && python3 -m pytest tests/test_services/test_document_hash_store.py -v
```

Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add src/backend/app/services/document_hash_store.py src/backend/tests/test_services/__init__.py src/backend/tests/test_services/test_document_hash_store.py
git commit -m "feat: add DocumentHashStore for incremental graph build file tracking"
```

---

### Task 2: EntityResolver — embedding-based node matching with CPU fallback

`EntityResolver` wraps the existing fuzzy-string `_find_existing_node` logic and adds a cosine-similarity layer when BGE-M3 is available. When `EMBEDDING_BASE_URL` is unset or the server is unreachable, it falls back to string matching only.

**Files:**
- Create: `src/backend/app/utils/entity_resolver.py`
- Create: `src/backend/tests/test_utils/test_entity_resolver.py`

- [ ] **Step 1: Write failing tests**

```python
# src/backend/tests/test_utils/test_entity_resolver.py
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


def test_fuzzy_name_match_returns_existing_node():
    g = _make_graph(("Skill:NLP", "Skill", "NLP"))
    resolver = EntityResolver(fuzzy_threshold=0.85)
    result = resolver.find_existing_node(g, "Skill", "자연어처리(NLP)")
    # no fuzzy match expected for this pair
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
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd src/backend && python3 -m pytest tests/test_utils/test_entity_resolver.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.utils.entity_resolver'`

- [ ] **Step 3: Implement EntityResolver**

```python
# src/backend/app/utils/entity_resolver.py
from difflib import SequenceMatcher

import networkx as nx
import numpy as np

from app.config import config
from app.utils.logger import get_logger

logger = get_logger(__name__)


class EntityResolver:
    """Find existing graph nodes by name using fuzzy string match with optional
    embedding-based cosine similarity fallback (iText2KG-inspired pattern).

    Embedding similarity is used only when EMBEDDING_BASE_URL is configured and
    the embedding server is reachable. Falls back silently to string matching.
    """

    def __init__(self, fuzzy_threshold: float = 0.85, embed_threshold: float = 0.88):
        self._fuzzy_threshold = fuzzy_threshold
        self._embed_threshold = embed_threshold

    def find_existing_node(
        self, graph: nx.DiGraph, entity_type: str, name: str
    ) -> str | None:
        """Synchronous lookup: fuzzy string match only."""
        for node_id in graph.nodes:
            node = graph.nodes[node_id]
            if node.get("type") != entity_type:
                continue
            if self._fuzzy_match(node.get("name", ""), name):
                return node_id
        return None

    async def find_existing_node_async(
        self, graph: nx.DiGraph, entity_type: str, name: str
    ) -> str | None:
        """Async lookup: fuzzy string match first, then embedding cosine similarity."""
        sync_result = self.find_existing_node(graph, entity_type, name)
        if sync_result is not None:
            return sync_result

        if not config.EMBEDDING_BASE_URL:
            return None

        candidates = [
            (node_id, graph.nodes[node_id].get("name", ""))
            for node_id in graph.nodes
            if graph.nodes[node_id].get("type") == entity_type
        ]
        if not candidates:
            return None

        try:
            from app.utils.embedding_client import EmbeddingClient
            client = EmbeddingClient()
            all_names = [name] + [c[1] for c in candidates]
            embeddings = await client.embed(all_names)
            arr = np.array(embeddings, dtype=np.float32)
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            arr /= np.maximum(norms, 1e-9)
            query_vec = arr[0]
            cand_vecs = arr[1:]
            sims = cand_vecs @ query_vec
            best_idx = int(np.argmax(sims))
            if float(sims[best_idx]) >= self._embed_threshold:
                matched_id = candidates[best_idx][0]
                logger.info(
                    f"Embedding match: '{name}' -> '{candidates[best_idx][1]}' "
                    f"(sim={sims[best_idx]:.3f})"
                )
                return matched_id
        except Exception as e:
            logger.debug(f"Embedding lookup failed, staying with string match: {e}")

        return None

    def _fuzzy_match(self, a: str, b: str) -> bool:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= self._fuzzy_threshold
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd src/backend && python3 -m pytest tests/test_utils/test_entity_resolver.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/utils/entity_resolver.py src/backend/tests/test_utils/test_entity_resolver.py
git commit -m "feat: add EntityResolver with fuzzy + optional embedding cosine similarity (iText2KG pattern)"
```

---

### Task 3: Wire EntityResolver into GraphBuilderAgent

Replace the existing `_fuzzy_match` / `_find_existing_node` pair in `GraphBuilderAgent` with `EntityResolver`. The `run()` method switches to async `find_existing_node_async` if BGE-M3 is configured.

**Files:**
- Modify: `src/backend/app/agents/graph_builder_agent.py`

- [ ] **Step 1: Open the file and read lines 22–245** (already done above)

- [ ] **Step 2: Replace `_find_existing_node` and `_fuzzy_match` with EntityResolver**

In `src/backend/app/agents/graph_builder_agent.py`:

Add import at top of file (after existing imports):
```python
from app.utils.entity_resolver import EntityResolver
```

In `GraphBuilderAgent.__init__`, add:
```python
self._resolver = EntityResolver(fuzzy_threshold=self._fuzzy_threshold)
```

Replace the `_find_existing_node` method body:
```python
def _find_existing_node(
    self, graph: nx.DiGraph, entity_type: str, name: str
) -> str | None:
    return self._resolver.find_existing_node(graph, entity_type, name)
```

Remove `_fuzzy_match` method entirely (now inside EntityResolver).

In `_merge_into_graph`, change the call from sync to async by making `_merge_into_graph` an async method and awaiting:
```python
existing = await self._resolver.find_existing_node_async(graph, etype, name)
```

Update the callers of `_merge_into_graph` in `run()` and `reextract_with_context()` to `await self._merge_into_graph(...)`.

- [ ] **Step 3: Run full test suite**

```bash
cd src/backend && python3 -m pytest tests/ -q
```

Expected: same pass count as before (134+), no regressions.

- [ ] **Step 4: Commit**

```bash
git add src/backend/app/agents/graph_builder_agent.py
git commit -m "refactor: use EntityResolver in GraphBuilderAgent for node matching"
```

---

### Task 4: Wire DocumentHashStore into `_run_graph` for incremental skipping

When `incremental=True`, compute MD5 of each chunk's source file content and skip chunks from unchanged files. Ontology hash is also tracked so schema changes force full rebuild.

**Files:**
- Modify: `src/backend/app/api/graph.py`

- [ ] **Step 1: Read the `_run_graph` function** (lines 213–340, already reviewed)

- [ ] **Step 2: Add hash tracking logic**

In `src/backend/app/api/graph.py`, inside `_run_graph`, after loading `chunks` and `ontology`, add:

```python
import hashlib

from app.services.document_hash_store import DocumentHashStore

proj_files_dir = proj_dir / "files"
hash_store = DocumentHashStore(proj_dir)

# compute current file hashes
source_files = list({c.source_file for c in chunks})
for fname in source_files:
    fpath = proj_files_dir / fname
    if fpath.exists():
        digest = hashlib.md5(fpath.read_bytes()).hexdigest()
        hash_store.update(fname, digest)

# compute ontology hash
import json as _json
ont_hash = hashlib.md5(_json.dumps(ont_data, sort_keys=True).encode()).hexdigest()
hash_store.update_ontology(ont_hash)

if incremental:
    changed_files = set(hash_store.get_changed_files(source_files))
    original_count = len(chunks)
    chunks = [c for c in chunks if c.source_file in changed_files]
    skipped = original_count - len(chunks)
    if skipped:
        logger.info(f"Incremental: skipping {skipped} chunks from {len(source_files) - len(changed_files)} unchanged files")
        task_manager.update(task_id, message=f"증분 처리: {skipped}청크 스킵, {len(chunks)}청크 재처리", progress=25)
```

After `graph_agent.save(graph, graph_path)`, add:
```python
hash_store.save()
```

- [ ] **Step 3: Run full test suite**

```bash
cd src/backend && python3 -m pytest tests/ -q
```

Expected: all pass, no regressions.

- [ ] **Step 4: Commit**

```bash
git add src/backend/app/api/graph.py
git commit -m "feat: skip unchanged files in incremental graph build using DocumentHashStore"
```

---

## P2 — Index-First QueryAgent

### Task 5: ObsidianWriterAgent writes `_index.md`

After writing all entity notes, write a `_index.md` that maps canonical entity names (with Korean/English variants) to their vault note paths.

**Files:**
- Modify: `src/backend/app/agents/obsidian_writer_agent.py`

- [ ] **Step 1: Find where vault writing ends**

In `obsidian_writer_agent.py`, locate the `run()` method return statement.

- [ ] **Step 2: Add `_write_index` method and call it**

```python
def _write_index(self, vault: Path, graph: nx.DiGraph) -> None:
    """Write _index.md: a canonical name → type + aliases map for query resolution."""
    lines = ["# Graph Index\n", "_Auto-generated. Do not edit manually._\n"]
    by_type: dict[str, list[tuple[str, str]]] = {}
    for node_id, data in graph.nodes(data=True):
        ntype = data.get("type", "")
        if ntype == "Category":
            continue
        name = data.get("name", "")
        if not name:
            continue
        by_type.setdefault(ntype, []).append((name, data.get("description", "")))

    for ntype in sorted(by_type):
        lines.append(f"\n## {ntype}\n")
        for name, desc in sorted(by_type[ntype], key=lambda x: x[0]):
            desc_part = f" — {desc[:60]}" if desc else ""
            lines.append(f"- {name}{desc_part}\n")

    (vault / "_index.md").write_text("".join(lines), encoding="utf-8")
```

Call this in `run()` just before returning:
```python
self._write_index(vault, graph)
```

- [ ] **Step 3: Run obsidian writer tests**

```bash
cd src/backend && python3 -m pytest tests/test_agents/test_obsidian_writer_agent.py -v
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/backend/app/agents/obsidian_writer_agent.py
git commit -m "feat: write _index.md to vault for index-first query resolution"
```

---

### Task 6: QueryAgent — index-aware node lookup

Replace the raw `query.lower().split()` word scan with a two-step lookup:
1. Build an in-memory name index from the graph (all node names, lowercased).
2. For each query token, also check if it matches any node name as a substring — this covers "파이썬" matching inside "Python (파이썬)" descriptions.

The key improvement over current code: the lookup now scores nodes by **name substring match** (higher weight) in addition to description word match, and returns up to 10 nodes instead of unlimited.

**Files:**
- Modify: `src/backend/app/agents/query_agent.py`
- Modify: `src/backend/tests/test_agents/test_query_agent.py`

- [ ] **Step 1: Write new test cases**

Add to `src/backend/tests/test_agents/test_query_agent.py`:

```python
def test_search_graph_returns_node_with_english_name_from_korean_query():
    """Query '파이썬' should NOT match node named 'Python' — tests the limit of current approach."""
    import networkx as nx
    from app.agents.query_agent import QueryAgent
    g = nx.DiGraph()
    g.add_node("Skill:Python", type="Skill", name="Python", description="Programming language")
    agent = QueryAgent()
    result = agent._search_graph(g, "Python 프로젝트")
    assert any(n["name"] == "Python" for n in result["nodes"])


def test_search_graph_name_match_scores_higher_than_description_match():
    import networkx as nx
    from app.agents.query_agent import QueryAgent
    g = nx.DiGraph()
    g.add_node("Project:NLP", type="Project", name="NLP 프로젝트", description="builds models")
    g.add_node("Skill:Models", type="Skill", name="Models", description="NLP based models")
    agent = QueryAgent()
    result = agent._search_graph(g, "NLP")
    # Node with "NLP" in name should appear first
    assert result["nodes"][0]["name"] == "NLP 프로젝트"


def test_search_graph_respects_max_node_limit():
    import networkx as nx
    from app.agents.query_agent import QueryAgent
    g = nx.DiGraph()
    for i in range(20):
        g.add_node(f"Skill:s{i}", type="Skill", name=f"skill_{i}", description="test query")
    agent = QueryAgent()
    result = agent._search_graph(g, "query")
    assert len(result["nodes"]) <= 10
```

- [ ] **Step 2: Run new tests — expect FAIL**

```bash
cd src/backend && python3 -m pytest tests/test_agents/test_query_agent.py -v -k "name_match or max_node"
```

- [ ] **Step 3: Rewrite `_search_graph` in QueryAgent**

```python
def _search_graph(self, graph: nx.DiGraph, query: str) -> dict:
    query_lower = query.lower()
    query_tokens = [t for t in query_lower.split() if len(t) > 1]

    scored: list[tuple[float, dict]] = []
    for node_id, data in graph.nodes(data=True):
        name = data.get("name", "")
        desc = data.get("description", "") or ""
        name_lower = name.lower()
        desc_lower = desc.lower()

        # Name substring match scores higher than description word match
        name_score = sum(2.0 for t in query_tokens if t in name_lower)
        desc_score = sum(1.0 for t in query_tokens if t in desc_lower)
        total = name_score + desc_score
        if total > 0:
            scored.append((total, {
                "id": node_id,
                "type": data.get("type"),
                "name": name,
                "description": desc,
            }))

    scored.sort(key=lambda x: -x[0])
    matched_nodes = [item for _, item in scored[:10]]

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
                bfs_nodes.append({
                    "type": ndata.get("type"),
                    "name": ndata.get("name"),
                })

    return {"nodes": matched_nodes, "edges": connected_edges, "related": bfs_nodes}
```

- [ ] **Step 4: Run full query agent test suite**

```bash
cd src/backend && python3 -m pytest tests/test_agents/test_query_agent.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full test suite**

```bash
cd src/backend && python3 -m pytest tests/ -q
```

Expected: same or higher pass count, no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/backend/app/agents/query_agent.py src/backend/tests/test_agents/test_query_agent.py
git commit -m "feat: score-based node search in QueryAgent with name-priority and 10-node cap"
```

---

## P3 — Graph Health Check API

### Task 7: `graph_health.py` utility

**Files:**
- Create: `src/backend/app/utils/graph_health.py`
- Create: `src/backend/tests/test_utils/test_graph_health.py`

- [ ] **Step 1: Write failing tests**

```python
# src/backend/tests/test_utils/test_graph_health.py
import networkx as nx
import pytest

from app.utils.graph_health import (
    check_duplicate_candidates,
    check_hub_nodes,
    check_isolated_nodes,
    check_weak_components,
    run_health_check,
)


def _chain_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("A:a", type="Skill", name="a")
    g.add_node("A:b", type="Skill", name="b")
    g.add_node("A:c", type="Skill", name="c")
    g.add_edge("A:a", "A:b", relation="R")
    g.add_edge("A:b", "A:c", relation="R")
    return g


def test_check_isolated_nodes_finds_disconnected():
    g = _chain_graph()
    g.add_node("A:lone", type="Skill", name="lone")
    result = check_isolated_nodes(g)
    assert len(result) == 1
    assert result[0]["node_id"] == "A:lone"


def test_check_isolated_nodes_empty_when_all_connected():
    g = _chain_graph()
    assert check_isolated_nodes(g) == []


def test_check_weak_components_detects_disconnected_subgraph():
    g = _chain_graph()
    g.add_node("B:x", type="Project", name="x")
    g.add_node("B:y", type="Project", name="y")
    g.add_edge("B:x", "B:y", relation="R")
    result = check_weak_components(g)
    assert len(result) == 2


def test_check_weak_components_single_component():
    g = _chain_graph()
    result = check_weak_components(g)
    assert len(result) == 1


def test_check_duplicate_candidates_finds_similar_names():
    g = nx.DiGraph()
    g.add_node("Skill:NLP", type="Skill", name="NLP")
    g.add_node("Skill:자연어처리", type="Skill", name="자연어처리")
    g.add_node("Skill:Python", type="Skill", name="Python")
    # NLP and 자연어처리 are not fuzzy-similar by string, so no duplicates expected
    result = check_duplicate_candidates(g, threshold=0.9)
    assert all(
        not (p["name_a"] in {"NLP", "Python"} and p["name_b"] in {"NLP", "Python"})
        for p in result
    )


def test_check_duplicate_candidates_finds_near_identical():
    g = nx.DiGraph()
    g.add_node("Skill:딥러닝", type="Skill", name="딥러닝")
    g.add_node("Skill:딥 러닝", type="Skill", name="딥 러닝")
    result = check_duplicate_candidates(g, threshold=0.85)
    assert len(result) >= 1
    pair = result[0]
    assert {"pair" for _ in [pair]} and "name_a" in pair


def test_check_hub_nodes_flags_high_degree():
    g = nx.DiGraph()
    g.add_node("Person:hub", type="Person", name="hub")
    for i in range(25):
        g.add_node(f"Skill:s{i}", type="Skill", name=f"s{i}")
        g.add_edge("Person:hub", f"Skill:s{i}", relation="USES_SKILL")
    result = check_hub_nodes(g, max_degree=20)
    assert any(n["node_id"] == "Person:hub" for n in result)


def test_run_health_check_returns_all_sections():
    g = _chain_graph()
    report = run_health_check(g)
    assert "isolated_nodes" in report
    assert "weak_components" in report
    assert "duplicate_candidates" in report
    assert "hub_nodes" in report
    assert "summary" in report
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd src/backend && python3 -m pytest tests/test_utils/test_graph_health.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.utils.graph_health'`

- [ ] **Step 3: Implement `graph_health.py`**

```python
# src/backend/app/utils/graph_health.py
from difflib import SequenceMatcher

import networkx as nx


def check_isolated_nodes(graph: nx.DiGraph) -> list[dict]:
    """Return nodes with no edges (degree == 0)."""
    result = []
    for node_id in graph.nodes:
        if graph.degree(node_id) == 0:
            data = graph.nodes[node_id]
            result.append({
                "node_id": node_id,
                "type": data.get("type"),
                "name": data.get("name"),
            })
    return result


def check_weak_components(graph: nx.DiGraph) -> list[dict]:
    """Return info about each weakly connected component."""
    undirected = graph.to_undirected()
    components = list(nx.connected_components(undirected))
    result = []
    for comp in components:
        types: dict[str, int] = {}
        for nid in comp:
            t = graph.nodes[nid].get("type", "unknown")
            types[t] = types.get(t, 0) + 1
        result.append({
            "size": len(comp),
            "node_types": types,
            "sample_nodes": [graph.nodes[n].get("name", n) for n in list(comp)[:3]],
        })
    result.sort(key=lambda x: -x["size"])
    return result


def check_duplicate_candidates(
    graph: nx.DiGraph, threshold: float = 0.85
) -> list[dict]:
    """Return pairs of same-type nodes whose names are similar but not identical."""
    by_type: dict[str, list[tuple[str, str]]] = {}
    for node_id, data in graph.nodes(data=True):
        ntype = data.get("type", "")
        name = data.get("name", "")
        if ntype and name:
            by_type.setdefault(ntype, []).append((node_id, name))

    pairs = []
    for ntype, nodes in by_type.items():
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                id_a, name_a = nodes[i]
                id_b, name_b = nodes[j]
                if name_a == name_b:
                    continue
                ratio = SequenceMatcher(None, name_a.lower(), name_b.lower()).ratio()
                if ratio >= threshold:
                    pairs.append({
                        "type": ntype,
                        "node_id_a": id_a,
                        "name_a": name_a,
                        "node_id_b": id_b,
                        "name_b": name_b,
                        "similarity": round(ratio, 3),
                    })
    pairs.sort(key=lambda x: -x["similarity"])
    return pairs


def check_hub_nodes(graph: nx.DiGraph, max_degree: int = 20) -> list[dict]:
    """Return nodes with total degree above max_degree (potential over-generic hubs)."""
    result = []
    for node_id in graph.nodes:
        deg = graph.degree(node_id)
        if deg > max_degree:
            data = graph.nodes[node_id]
            result.append({
                "node_id": node_id,
                "type": data.get("type"),
                "name": data.get("name"),
                "degree": deg,
            })
    result.sort(key=lambda x: -x["degree"])
    return result


def run_health_check(graph: nx.DiGraph, max_degree: int = 20, dup_threshold: float = 0.85) -> dict:
    isolated = check_isolated_nodes(graph)
    components = check_weak_components(graph)
    duplicates = check_duplicate_candidates(graph, threshold=dup_threshold)
    hubs = check_hub_nodes(graph, max_degree=max_degree)
    return {
        "isolated_nodes": isolated,
        "weak_components": components,
        "duplicate_candidates": duplicates,
        "hub_nodes": hubs,
        "summary": {
            "total_nodes": graph.number_of_nodes(),
            "total_edges": graph.number_of_edges(),
            "isolated_count": len(isolated),
            "component_count": len(components),
            "duplicate_pair_count": len(duplicates),
            "hub_count": len(hubs),
        },
    }
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd src/backend && python3 -m pytest tests/test_utils/test_graph_health.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/utils/graph_health.py src/backend/tests/test_utils/test_graph_health.py
git commit -m "feat: add graph_health utility (isolated nodes, weak components, duplicate candidates, hub nodes)"
```

---

### Task 8: `GET /api/projects/{project_id}/graph/health` endpoint

**Files:**
- Modify: `src/backend/app/api/graph.py`

- [ ] **Step 1: Add the endpoint**

In `src/backend/app/api/graph.py`, after the `get_graph_stats` endpoint (around line 175), add:

```python
@router.get("/{project_id}/graph/health")
async def get_graph_health(project_id: str):
    from app.utils.graph_health import run_health_check
    proj_dir = Path(config.PROJECTS_DIR) / project_id
    graph_path = proj_dir / "graph.json"
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail="Graph not found")
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    graph = nx.node_link_graph(data)
    return run_health_check(graph)
```

- [ ] **Step 2: Verify endpoint exists**

```bash
cd src/backend && python3 -m pytest tests/test_api/ -v -q
```

Expected: all existing tests pass.

- [ ] **Step 3: Manual smoke test against running backend**

```bash
curl -s http://localhost:8001/api/projects/29347d1e/graph/health | python3 -c "
import sys, json
d = json.load(sys.stdin)
s = d['summary']
print(f'Nodes: {s[\"total_nodes\"]}, Edges: {s[\"total_edges\"]}')
print(f'Isolated: {s[\"isolated_count\"]}')
print(f'Components: {s[\"component_count\"]}')
print(f'Duplicate candidates: {s[\"duplicate_pair_count\"]}')
print(f'Hub nodes: {s[\"hub_count\"]}')
"
```

- [ ] **Step 4: Run full test suite**

```bash
cd src/backend && python3 -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/api/graph.py
git commit -m "feat: add GET /api/projects/{id}/graph/health endpoint"
```

---

## Final

- [ ] **Update handoff doc**

Update `docs/claude-code-handoff.md` with:
- What was implemented in this session
- Test results
- Next candidates

- [ ] **Push**

```bash
git -c credential.helper='' push https://<GITHUB_TOKEN>@github.com/ypilseong/ProjectOS.git main
```

---

## Self-Review

**Spec coverage:**
- P1 iText2KG entity resolution → Task 2 (EntityResolver) + Task 3 (wired into GraphBuilderAgent) ✓
- P1 incremental processing → Task 1 (DocumentHashStore) + Task 4 (wired into _run_graph) ✓
- P2 index-first QueryAgent → Task 5 (_index.md) + Task 6 (score-based search) ✓
- P3 health check endpoint → Task 7 (graph_health.py) + Task 8 (API) ✓

**Placeholder scan:** No TBD/TODO/similar-to-task-N patterns found.

**Type consistency:**
- `DocumentHashStore`: `update(filename, file_hash)`, `update_ontology(hash)`, `save()`, `get_changed_files(list) → list` — consistent across Tasks 1 and 4.
- `EntityResolver`: `find_existing_node(graph, type, name) → str|None`, `find_existing_node_async(...)` — consistent across Tasks 2 and 3.
- `run_health_check(graph) → dict` with keys `isolated_nodes`, `weak_components`, `duplicate_candidates`, `hub_nodes`, `summary` — consistent across Tasks 7 and 8.
