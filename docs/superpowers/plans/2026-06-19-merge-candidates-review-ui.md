# merge_candidates 리뷰 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 `graph.graph["merge_candidates"]` 노드 병합 후보를 검토해 승인(실제 병합 적용) 또는 거부(denylist 영속화)할 수 있는 풀스택 기능을 추가한다.

**Architecture:** 백엔드는 별도 파일 `projects/{id}/merge_denylist.json`에 거부 쌍을 영속화하고, `collect_merge_candidates`가 이를 필터링한다. apply/reject 두 엔드포인트가 graph.json을 로드·변형·저장한다. 프론트엔드는 GET `/graph` 응답에 실려오는 후보를 순수 함수로 추출해 `MergeReviewPanel.vue` 탭에서 렌더하고, 승인/거부 시 API를 호출한다.

**Tech Stack:** FastAPI, NetworkX DiGraph, pytest / Vue 3 `<script setup>`, Element Plus, Vitest.

**Spec:** `docs/superpowers/specs/2026-06-19-merge-candidates-review-ui-design.md`

---

## 배경 사실 (구현자 필독)

- 노드 id는 안정적 `Type:Name` 형식 (예: `Skill:SOT fine-tuning`). 그래프 재빌드 사이에 동일하므로 denylist 키로 안전하다.
- 후보 dict 형태: `{type, keep_id, keep_name, candidate_id, candidate_name, confidence, aliases[]}`. keep = degree가 더 높은 노드.
- graph.json은 node_link_data 형식이며 graph-level 속성은 `data["graph"]` 아래에 들어간다. `merge_candidates`는 `data["graph"]["merge_candidates"]`에 위치.
- `nx.node_link_graph` / `nx.node_link_data` 는 `graph.graph` 속성을 라운드트립 보존한다. `normalize_graph_entity_types`와 `build_entity_details`는 in-place 변형 후 같은 객체를 반환하므로 GET `/graph` 응답에도 `merge_candidates`가 보존된다.
- `_merge_node(graph, canonical_id, dup_id)` (`app/utils/semantic_dedup.py:213`): predecessor/successor 엣지를 canonical로 리다이렉트, `source_files`/`source_chunk_ids` 합집합, dup name을 alias로 보존(canonical name은 alias에서 제외), dup 노드 제거. **DiGraph 필요.**
- 테스트 환경: `tests/conftest.py`의 autouse `isolate_filesystem` 픽스처가 `config.PROJECTS_DIR`를 tmp 디렉토리로 이미 격리한다. 따라서 테스트에서 `Path(config.PROJECTS_DIR) / project_id`에 직접 파일을 쓰면 된다 (추가 monkeypatch 불필요).
- graph.json 저장 시 항상 "links" 키를 쓰는 기존 패턴 (`app/api/graph.py:223-226`):
  ```python
  out = nx.node_link_data(graph)
  if "edges" in out and "links" not in out:
      out["links"] = out.pop("edges")
  graph_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
  ```
- graph.json 로드 시 기존 패턴 (`app/api/graph.py:148-151`):
  ```python
  data = json.loads(p.read_text(encoding="utf-8"))
  if "links" in data and "edges" not in data:
      data["edges"] = data.pop("links")
  graph = nx.node_link_graph(data)
  ```

---

## File Structure

**백엔드 (생성):**
- `app/utils/merge_denylist.py` — denylist 파일 load/add. 단일 책임: 거부 쌍 영속화.

**백엔드 (수정):**
- `app/utils/merge_review.py` — `collect_merge_candidates`에 `denylist` 파라미터 추가.
- `app/api/graph.py` — apply/reject 엔드포인트 2개 추가, 빌드 경로에서 denylist 적용.

**백엔드 테스트:**
- `tests/test_utils/test_merge_denylist.py` (생성)
- `tests/test_utils/test_merge_review.py` (확장)
- `tests/test_api/test_graph_merge_candidates.py` (생성)

**프론트엔드 (생성):**
- `src/lib/mergeCandidates.js` — 순수 추출 함수.
- `src/lib/mergeCandidates.test.js`
- `src/components/MergeReviewPanel.vue` — 검토 패널.

**프론트엔드 (수정):**
- `src/api/client.js` — apply/reject API 메서드.
- `src/views/ProjectDetail.vue` — "병합 검토" 탭 + 후보 개수 + refetch 핸들러.

---

## Task 1: denylist 영속화 유틸

**Files:**
- Create: `src/backend/app/utils/merge_denylist.py`
- Test: `src/backend/tests/test_utils/test_merge_denylist.py`

- [ ] **Step 1: Write the failing tests**

Create `src/backend/tests/test_utils/test_merge_denylist.py`:

```python
from app.config import config
from app.utils.merge_denylist import add_denied_pair, load_denylist


def test_load_missing_returns_empty_set():
    assert load_denylist("no_such_project") == set()


def test_add_then_load_roundtrip():
    add_denied_pair("p1", "Skill:A", "Skill:B")

    dl = load_denylist("p1")

    assert dl == {frozenset({"Skill:A", "Skill:B"})}


def test_add_is_order_independent():
    add_denied_pair("p2", "Skill:B", "Skill:A")

    dl = load_denylist("p2")

    assert frozenset({"Skill:A", "Skill:B"}) in dl


def test_add_duplicate_pair_is_idempotent():
    add_denied_pair("p3", "Skill:A", "Skill:B")
    add_denied_pair("p3", "Skill:B", "Skill:A")

    assert load_denylist("p3") == {frozenset({"Skill:A", "Skill:B"})}


def test_add_multiple_distinct_pairs():
    add_denied_pair("p4", "Skill:A", "Skill:B")
    add_denied_pair("p4", "Skill:C", "Skill:D")

    dl = load_denylist("p4")

    assert dl == {
        frozenset({"Skill:A", "Skill:B"}),
        frozenset({"Skill:C", "Skill:D"}),
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python3 -m pytest tests/test_utils/test_merge_denylist.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.utils.merge_denylist'`

- [ ] **Step 3: Write the implementation**

Create `src/backend/app/utils/merge_denylist.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from app.config import config


def _denylist_path(project_id: str) -> Path:
    return Path(config.PROJECTS_DIR) / project_id / "merge_denylist.json"


def load_denylist(project_id: str) -> set[frozenset]:
    """Load the set of rejected merge pairs for a project.

    Each pair is a frozenset of two node ids. Missing or unreadable files
    yield an empty set so callers can treat "no denylist" as "no exclusions".
    """
    path = _denylist_path(project_id)
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    pairs: set[frozenset] = set()
    for entry in raw:
        if isinstance(entry, list) and len(entry) == 2:
            pairs.add(frozenset(entry))
    return pairs


def add_denied_pair(project_id: str, id_a: str, id_b: str) -> None:
    """Persist a rejected merge pair so it is never re-suggested."""
    denylist = load_denylist(project_id)
    denylist.add(frozenset({id_a, id_b}))

    serialized = sorted(sorted(pair) for pair in denylist)

    path = _denylist_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(serialized, indent=2, ensure_ascii=False), encoding="utf-8"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src/backend && python3 -m pytest tests/test_utils/test_merge_denylist.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/utils/merge_denylist.py src/backend/tests/test_utils/test_merge_denylist.py
git commit -m "feat(merge): persist rejected merge pairs in denylist file"
```

---

## Task 2: collect_merge_candidates denylist 필터

**Files:**
- Modify: `src/backend/app/utils/merge_review.py:27-90`
- Test: `src/backend/tests/test_utils/test_merge_review.py`

- [ ] **Step 1: Write the failing tests**

Append to `src/backend/tests/test_utils/test_merge_review.py`:

```python
def test_denylist_excludes_pair():
    g = nx.DiGraph()
    g.add_node("Skill:TensorFlow", type="Skill", name="TensorFlow", source_files=[])
    g.add_node("Skill:Tensorflow", type="Skill", name="Tensorflow", source_files=[])

    denylist = {frozenset({"Skill:TensorFlow", "Skill:Tensorflow"})}
    candidates = collect_merge_candidates(g, denylist=denylist)

    assert candidates == []


def test_denylist_none_keeps_default_behavior():
    g = nx.DiGraph()
    g.add_node("Skill:TensorFlow", type="Skill", name="TensorFlow", source_files=[])
    g.add_node("Skill:Tensorflow", type="Skill", name="Tensorflow", source_files=[])

    assert len(collect_merge_candidates(g, denylist=None)) == 1


def test_denylist_only_filters_listed_pair():
    g = nx.DiGraph()
    g.add_node("Skill:TensorFlow", type="Skill", name="TensorFlow", source_files=[])
    g.add_node("Skill:Tensorflow", type="Skill", name="Tensorflow", source_files=[])
    g.add_node("Skill:PyTorch", type="Skill", name="PyTorch", source_files=[])
    g.add_node("Skill:Pytorch", type="Skill", name="Pytorch", source_files=[])

    denylist = {frozenset({"Skill:TensorFlow", "Skill:Tensorflow"})}
    candidates = collect_merge_candidates(g, denylist=denylist)

    pairs = {frozenset({c["keep_id"], c["candidate_id"]}) for c in candidates}
    assert frozenset({"Skill:TensorFlow", "Skill:Tensorflow"}) not in pairs
    assert frozenset({"Skill:PyTorch", "Skill:Pytorch"}) in pairs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python3 -m pytest tests/test_utils/test_merge_review.py -v -k denylist`
Expected: FAIL with `TypeError: collect_merge_candidates() got an unexpected keyword argument 'denylist'`

- [ ] **Step 3: Modify the signature and add the filter**

In `src/backend/app/utils/merge_review.py`, change the function signature (line 27-29):

```python
def collect_merge_candidates(
    graph: nx.DiGraph,
    threshold: float | None = None,
    denylist: set[frozenset] | None = None,
) -> list[dict]:
```

Then inside the inner `for j` loop, immediately after `id_a, id_b = node_ids[i], node_ids[j]` (currently line 55), add:

```python
                if denylist and frozenset({id_a, id_b}) in denylist:
                    continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src/backend && python3 -m pytest tests/test_utils/test_merge_review.py -v`
Expected: PASS (all existing + 3 new)

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/utils/merge_review.py src/backend/tests/test_utils/test_merge_review.py
git commit -m "feat(merge): filter merge candidates against denylist"
```

---

## Task 3: 빌드 경로에서 denylist 적용

**Files:**
- Modify: `src/backend/app/api/graph.py:499-501`

- [ ] **Step 1: Modify the build path**

In `src/backend/app/api/graph.py`, locate (around line 499-501):

```python
        from app.utils.merge_review import collect_merge_candidates
        merge_candidates = collect_merge_candidates(graph)
        graph.graph["merge_candidates"] = merge_candidates
```

Replace with:

```python
        from app.utils.merge_denylist import load_denylist
        from app.utils.merge_review import collect_merge_candidates
        merge_candidates = collect_merge_candidates(
            graph, denylist=load_denylist(project_id)
        )
        graph.graph["merge_candidates"] = merge_candidates
```

- [ ] **Step 2: Verify nothing breaks**

Run: `cd src/backend && python3 -m pytest tests/ -q`
Expected: PASS (513 passed, same as baseline — this change only wires an already-tested function)

- [ ] **Step 3: Commit**

```bash
git add src/backend/app/api/graph.py
git commit -m "feat(merge): exclude denied pairs when collecting candidates on build"
```

---

## Task 4: apply 엔드포인트 (승인 → 병합)

**Files:**
- Modify: `src/backend/app/api/graph.py` (add endpoint after `cleanup_graph`, around line 238)
- Test: `src/backend/tests/test_api/test_graph_merge_candidates.py`

- [ ] **Step 1: Write the failing tests**

Create `src/backend/tests/test_api/test_graph_merge_candidates.py`:

```python
import json
from pathlib import Path

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from app.config import config


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def _write_graph_with_candidates(project_id: str) -> None:
    """Two similar Skill nodes both linked to a Person, with collected candidates."""
    from app.utils.merge_review import collect_merge_candidates

    g = nx.DiGraph()
    g.add_node("Person:Kim", type="Person", name="Kim", source_files=["cv.pdf"])
    g.add_node(
        "Skill:TensorFlow", type="Skill", name="TensorFlow", source_files=["cv.pdf"]
    )
    g.add_node(
        "Skill:Tensorflow", type="Skill", name="Tensorflow", source_files=["p.pdf"]
    )
    g.add_edge("Person:Kim", "Skill:TensorFlow", relation="USES_SKILL")
    g.add_edge("Person:Kim", "Skill:Tensorflow", relation="USES_SKILL")
    g.graph["merge_candidates"] = collect_merge_candidates(g)

    proj_dir = Path(config.PROJECTS_DIR) / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    out = nx.node_link_data(g)
    if "edges" in out and "links" not in out:
        out["links"] = out.pop("edges")
    (proj_dir / "graph.json").write_text(json.dumps(out), encoding="utf-8")


def _load_graph_json(project_id: str) -> dict:
    p = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_apply_merges_nodes_and_refreshes_candidates(client):
    _write_graph_with_candidates("proj_apply")

    r = client.post(
        "/api/projects/proj_apply/graph/merge-candidates/apply",
        json={"keep_id": "Skill:TensorFlow", "candidate_id": "Skill:Tensorflow"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["merged"] is True
    # The dup node is gone from the persisted graph.
    node_ids = {n["id"] for n in _load_graph_json("proj_apply")["nodes"]}
    assert "Skill:Tensorflow" not in node_ids
    assert "Skill:TensorFlow" in node_ids
    # The merged pair no longer appears among candidates.
    pairs = {
        frozenset({c["keep_id"], c["candidate_id"]}) for c in body["merge_candidates"]
    }
    assert frozenset({"Skill:TensorFlow", "Skill:Tensorflow"}) not in pairs


def test_apply_with_stale_node_returns_409(client):
    _write_graph_with_candidates("proj_stale")

    r = client.post(
        "/api/projects/proj_stale/graph/merge-candidates/apply",
        json={"keep_id": "Skill:TensorFlow", "candidate_id": "Skill:DoesNotExist"},
    )

    assert r.status_code == 409


def test_apply_missing_graph_returns_404(client):
    r = client.post(
        "/api/projects/no_project/graph/merge-candidates/apply",
        json={"keep_id": "Skill:A", "candidate_id": "Skill:B"},
    )

    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python3 -m pytest tests/test_api/test_graph_merge_candidates.py -v -k apply`
Expected: FAIL with 404/405 (endpoint not defined)

- [ ] **Step 3: Add a Pydantic request model and the apply endpoint**

In `src/backend/app/api/graph.py`, add the import near the top (after line 8, with the other fastapi imports add `pydantic`):

```python
from pydantic import BaseModel
```

Add the request model just below `router = APIRouter()` (after line 19):

```python
class MergeCandidateAction(BaseModel):
    keep_id: str
    candidate_id: str
```

Add the endpoint immediately after the `cleanup_graph` function (after its final line, around line 238):

```python
@router.post("/{project_id}/graph/merge-candidates/apply")
async def apply_merge_candidate(project_id: str, body: MergeCandidateAction):
    from app.utils.merge_denylist import load_denylist
    from app.utils.merge_review import collect_merge_candidates
    from app.utils.semantic_dedup import _merge_node

    p = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    if not p.exists():
        raise HTTPException(404, "Graph not built yet")

    data = json.loads(p.read_text(encoding="utf-8"))
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    graph = nx.node_link_graph(data)

    if body.keep_id not in graph or body.candidate_id not in graph:
        raise HTTPException(409, "Candidate is stale; node no longer exists")

    _merge_node(graph, body.keep_id, body.candidate_id)

    merge_candidates = collect_merge_candidates(
        graph, denylist=load_denylist(project_id)
    )
    graph.graph["merge_candidates"] = merge_candidates

    out = nx.node_link_data(graph)
    if "edges" in out and "links" not in out:
        out["links"] = out.pop("edges")
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"merged": True, "merge_candidates": merge_candidates}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src/backend && python3 -m pytest tests/test_api/test_graph_merge_candidates.py -v -k apply`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/api/graph.py src/backend/tests/test_api/test_graph_merge_candidates.py
git commit -m "feat(merge): add apply endpoint to merge a reviewed candidate"
```

---

## Task 5: reject 엔드포인트 (거부 → denylist)

**Files:**
- Modify: `src/backend/app/api/graph.py` (add endpoint after `apply_merge_candidate`)
- Test: `src/backend/tests/test_api/test_graph_merge_candidates.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `src/backend/tests/test_api/test_graph_merge_candidates.py`:

```python
def test_reject_records_denylist_and_drops_candidate(client):
    _write_graph_with_candidates("proj_reject")

    r = client.post(
        "/api/projects/proj_reject/graph/merge-candidates/reject",
        json={"keep_id": "Skill:TensorFlow", "candidate_id": "Skill:Tensorflow"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["rejected"] is True
    # Pair removed from returned candidates.
    pairs = {
        frozenset({c["keep_id"], c["candidate_id"]}) for c in body["merge_candidates"]
    }
    assert frozenset({"Skill:TensorFlow", "Skill:Tensorflow"}) not in pairs
    # Denylist file persisted the pair.
    from app.utils.merge_denylist import load_denylist

    assert frozenset({"Skill:TensorFlow", "Skill:Tensorflow"}) in load_denylist(
        "proj_reject"
    )
    # Both nodes still exist (reject does not mutate graph structure).
    node_ids = {n["id"] for n in _load_graph_json("proj_reject")["nodes"]}
    assert {"Skill:TensorFlow", "Skill:Tensorflow"} <= node_ids


def test_reject_missing_graph_returns_404(client):
    r = client.post(
        "/api/projects/no_project/graph/merge-candidates/reject",
        json={"keep_id": "Skill:A", "candidate_id": "Skill:B"},
    )

    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python3 -m pytest tests/test_api/test_graph_merge_candidates.py -v -k reject`
Expected: FAIL with 404/405 (endpoint not defined)

- [ ] **Step 3: Add the reject endpoint**

In `src/backend/app/api/graph.py`, add immediately after `apply_merge_candidate`:

```python
@router.post("/{project_id}/graph/merge-candidates/reject")
async def reject_merge_candidate(project_id: str, body: MergeCandidateAction):
    from app.utils.merge_denylist import add_denied_pair

    p = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    if not p.exists():
        raise HTTPException(404, "Graph not built yet")

    add_denied_pair(project_id, body.keep_id, body.candidate_id)

    data = json.loads(p.read_text(encoding="utf-8"))
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    graph = nx.node_link_graph(data)

    rejected_pair = frozenset({body.keep_id, body.candidate_id})
    merge_candidates = [
        c
        for c in graph.graph.get("merge_candidates", [])
        if frozenset({c["keep_id"], c["candidate_id"]}) != rejected_pair
    ]
    graph.graph["merge_candidates"] = merge_candidates

    out = nx.node_link_data(graph)
    if "edges" in out and "links" not in out:
        out["links"] = out.pop("edges")
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"rejected": True, "merge_candidates": merge_candidates}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src/backend && python3 -m pytest tests/test_api/test_graph_merge_candidates.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/api/graph.py src/backend/tests/test_api/test_graph_merge_candidates.py
git commit -m "feat(merge): add reject endpoint persisting denied pairs"
```

---

## Task 6: 프론트엔드 후보 추출 순수 함수

**Files:**
- Create: `src/frontend/src/lib/mergeCandidates.js`
- Test: `src/frontend/src/lib/mergeCandidates.test.js`

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/src/lib/mergeCandidates.test.js`:

```js
import { describe, expect, it } from 'vitest'
import { extractMergeCandidates } from './mergeCandidates.js'

describe('extractMergeCandidates', () => {
  it('returns [] when graph data or candidates are missing', () => {
    expect(extractMergeCandidates(null)).toEqual([])
    expect(extractMergeCandidates({})).toEqual([])
    expect(extractMergeCandidates({ graph: {} })).toEqual([])
    expect(extractMergeCandidates({ graph: { merge_candidates: null } })).toEqual([])
  })

  it('returns the candidate list when present', () => {
    const gd = { graph: { merge_candidates: [{ keep_id: 'a', confidence: 0.8 }] } }
    expect(extractMergeCandidates(gd)).toHaveLength(1)
  })

  it('sorts by confidence descending', () => {
    const gd = {
      graph: {
        merge_candidates: [
          { keep_id: 'a', confidence: 0.7 },
          { keep_id: 'b', confidence: 0.9 },
          { keep_id: 'c', confidence: 0.8 },
        ],
      },
    }
    expect(extractMergeCandidates(gd).map((c) => c.keep_id)).toEqual(['b', 'c', 'a'])
  })

  it('does not mutate the input array', () => {
    const list = [
      { keep_id: 'a', confidence: 0.7 },
      { keep_id: 'b', confidence: 0.9 },
    ]
    const gd = { graph: { merge_candidates: list } }
    extractMergeCandidates(gd)
    expect(list.map((c) => c.keep_id)).toEqual(['a', 'b'])
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/frontend && npx vitest run src/lib/mergeCandidates.test.js`
Expected: FAIL — cannot resolve `./mergeCandidates.js`

- [ ] **Step 3: Write the implementation**

Create `src/frontend/src/lib/mergeCandidates.js`:

```js
export function extractMergeCandidates(graphData) {
  const list = graphData?.graph?.merge_candidates
  if (!Array.isArray(list)) return []
  return [...list].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0))
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src/frontend && npx vitest run src/lib/mergeCandidates.test.js`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/lib/mergeCandidates.js src/frontend/src/lib/mergeCandidates.test.js
git commit -m "feat(merge): add pure merge-candidate extractor for frontend"
```

---

## Task 7: API 클라이언트 메서드

**Files:**
- Modify: `src/frontend/src/api/client.js:37`

- [ ] **Step 1: Add the two methods**

In `src/frontend/src/api/client.js`, locate the line (37):

```js
  resolveSimulationEvidence: (id, data) => api.post(`/projects/${id}/simulation/evidence`, data),
```

Add immediately after it:

```js
  applyMergeCandidate: (id, data) => api.post(`/projects/${id}/graph/merge-candidates/apply`, data),
  rejectMergeCandidate: (id, data) => api.post(`/projects/${id}/graph/merge-candidates/reject`, data),
```

- [ ] **Step 2: Verify the file still parses**

Run: `cd src/frontend && npx vitest run src/lib/mergeCandidates.test.js`
Expected: PASS (import graph still resolves; no syntax error)

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/api/client.js
git commit -m "feat(merge): add apply/reject merge-candidate API client methods"
```

---

## Task 8: MergeReviewPanel 컴포넌트

**Files:**
- Create: `src/frontend/src/components/MergeReviewPanel.vue`

- [ ] **Step 1: Create the component**

Create `src/frontend/src/components/MergeReviewPanel.vue`:

```vue
<template>
  <div class="merge-review-panel">
    <el-empty
      v-if="candidates.length === 0"
      description="검토할 병합 후보가 없습니다"
    />
    <div v-else class="candidate-list">
      <el-card
        v-for="c in candidates"
        :key="c.keep_id + '|' + c.candidate_id"
        class="candidate-card"
        shadow="hover"
      >
        <div class="card-head">
          <el-tag size="small" type="info">{{ c.type }}</el-tag>
          <span class="confidence">{{ Math.round((c.confidence ?? 0) * 100) }}%</span>
        </div>
        <div class="merge-line">
          <strong>{{ c.keep_name }}</strong>
          <span class="arrow">←</span>
          <span class="dup">{{ c.candidate_name }}</span>
        </div>
        <div v-if="c.aliases && c.aliases.length" class="aliases">
          <el-tag
            v-for="alias in c.aliases"
            :key="alias"
            size="small"
            effect="plain"
            class="alias-chip"
          >
            {{ alias }}
          </el-tag>
        </div>
        <div class="card-actions">
          <el-button
            type="primary"
            size="small"
            :loading="isBusy(c)"
            @click="approve(c)"
          >
            승인
          </el-button>
          <el-button
            size="small"
            :loading="isBusy(c)"
            @click="reject(c)"
          >
            거부
          </el-button>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { projectsApi } from '../api/client.js'
import { extractMergeCandidates } from '../lib/mergeCandidates.js'

const props = defineProps({
  projectId: { type: String, required: true },
  graphData: { type: Object, default: null },
})
const emit = defineEmits(['merged'])

const candidates = ref(extractMergeCandidates(props.graphData))
const busyKey = ref(null)

watch(
  () => props.graphData,
  (gd) => {
    candidates.value = extractMergeCandidates(gd)
  },
)

function keyOf(c) {
  return c.keep_id + '|' + c.candidate_id
}

function isBusy(c) {
  return busyKey.value === keyOf(c)
}

async function approve(c) {
  busyKey.value = keyOf(c)
  try {
    const r = await projectsApi.applyMergeCandidate(props.projectId, {
      keep_id: c.keep_id,
      candidate_id: c.candidate_id,
    })
    candidates.value = r.data.merge_candidates ?? []
    ElMessage.success(`병합 적용: ${c.keep_name} ← ${c.candidate_name}`)
    emit('merged')
  } catch (e) {
    if (e?.response?.status === 409) {
      ElMessage.warning('이미 변경된 후보입니다. 그래프를 다시 불러옵니다.')
      emit('merged')
    } else {
      ElMessage.error('병합 적용에 실패했습니다.')
    }
  } finally {
    busyKey.value = null
  }
}

async function reject(c) {
  busyKey.value = keyOf(c)
  try {
    const r = await projectsApi.rejectMergeCandidate(props.projectId, {
      keep_id: c.keep_id,
      candidate_id: c.candidate_id,
    })
    candidates.value = r.data.merge_candidates ?? []
    ElMessage.info(`거부됨: ${c.keep_name} ← ${c.candidate_name}`)
  } catch (e) {
    ElMessage.error('거부 처리에 실패했습니다.')
  } finally {
    busyKey.value = null
  }
}
</script>

<style scoped>
.merge-review-panel {
  height: 500px;
  overflow-y: auto;
  padding: 8px;
}
.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.confidence {
  font-weight: 600;
  color: #409eff;
}
.merge-line {
  font-size: 15px;
  margin-bottom: 8px;
}
.merge-line .arrow {
  margin: 0 8px;
  color: #909399;
}
.merge-line .dup {
  color: #909399;
}
.aliases {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 10px;
}
.card-actions {
  display: flex;
  gap: 8px;
}
</style>
```

- [ ] **Step 2: Verify the build compiles**

Run: `cd src/frontend && npm run build`
Expected: `✓ built` with no errors referencing MergeReviewPanel.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/components/MergeReviewPanel.vue
git commit -m "feat(merge): add MergeReviewPanel component for candidate review"
```

---

## Task 9: ProjectDetail 탭 통합

**Files:**
- Modify: `src/frontend/src/views/ProjectDetail.vue` (template tabs ~line 220-226, imports ~line 266, script ~line 281-287, handler near line 431)

- [ ] **Step 1: Import the component and the extractor**

In `src/frontend/src/views/ProjectDetail.vue`, after the `SimulationPanel` import (line 266):

```js
import MergeReviewPanel from '../components/MergeReviewPanel.vue'
import { extractMergeCandidates } from '../lib/mergeCandidates.js'
```

- [ ] **Step 2: Add a computed candidate count**

After `const resultTab = ref('graph')` (line 287), add the `computed` import to the existing `vue` import if not already present, then add:

```js
const mergeCandidateCount = computed(() => extractMergeCandidates(graphData.value).length)
```

(If `computed` is not in the top `import { ... } from 'vue'`, add it.)

- [ ] **Step 3: Add the tab pane**

In the template, after the simulation `el-tab-pane` (closes at line 226), add:

```vue
            <el-tab-pane name="merge">
              <template #label>
                병합 검토
                <el-badge
                  v-if="mergeCandidateCount > 0"
                  :value="mergeCandidateCount"
                  class="merge-badge"
                />
              </template>
              <MergeReviewPanel
                :project-id="projectId"
                :graph-data="graphData"
                @merged="onMergeApplied"
              />
            </el-tab-pane>
```

- [ ] **Step 4: Add the refetch handler**

After the `onSimulationGraphUpdated` function (ends line 434), add:

```js
async function onMergeApplied() {
  try {
    const r = await projectsApi.getGraph(projectId.value)
    graphData.value = r.data
    await loadSidebarData()
  } catch (e) {
    console.error('Failed to refresh graph after merge:', e)
  }
}
```

- [ ] **Step 5: Add badge spacing style**

In the `<style scoped>` block of `ProjectDetail.vue`, add:

```css
.merge-badge {
  margin-left: 6px;
}
```

- [ ] **Step 6: Verify the build compiles**

Run: `cd src/frontend && npm run build`
Expected: `✓ built` with no errors.

- [ ] **Step 7: Commit**

```bash
git add src/frontend/src/views/ProjectDetail.vue
git commit -m "feat(merge): add 병합 검토 tab with candidate badge and refetch"
```

---

## Task 10: 전체 검증 + 핸드오프 갱신

**Files:**
- Modify: `docs/claude-code-handoff.md`

- [ ] **Step 1: Run the full backend suite**

Run: `cd src/backend && python3 -m pytest tests/ -q`
Expected: PASS — baseline was 513; now 513 + 5 (denylist) + 3 (merge_review) + 7 (api) ≈ 528 passed. No failures.

- [ ] **Step 2: Run the full frontend suite + build**

Run: `cd src/frontend && npx vitest run && npm run build`
Expected: vitest PASS (7 baseline + 4 new = 11 passed), build `✓ built`.

- [ ] **Step 3: Update the handoff doc**

In `docs/claude-code-handoff.md`, add a changelog entry describing: merge_candidates review UI shipped (denylist persistence, apply/reject endpoints, MergeReviewPanel tab), verification results (backend/frontend pass counts), and remove/close the "no dedicated frontend review UI yet" gap (around line 140). Add a next-work candidate: "denylist 항목 해제(undo) UI" if useful.

- [ ] **Step 4: Commit**

```bash
git add docs/claude-code-handoff.md
git commit -m "docs(handoff): merge_candidates review UI shipped"
```

- [ ] **Step 5: Finish the branch**

Use superpowers:finishing-a-development-branch to verify tests, present options, and complete the work.

---

## Self-Review

**1. Spec coverage:**
- denylist 별도 파일 저장 (Approach A) → Task 1 ✓
- collect_merge_candidates denylist 필터 → Task 2 ✓
- 빌드 경로 denylist 적용 → Task 3 ✓
- apply 엔드포인트 (병합 + 409 + 재수집) → Task 4 ✓
- reject 엔드포인트 (denylist 기록 + 후보 제거) → Task 5 ✓
- extractMergeCandidates 순수 함수 → Task 6 ✓
- client.js apply/reject → Task 7 ✓
- MergeReviewPanel (카드/승인/거부/빈 상태) → Task 8 ✓
- ProjectDetail 탭 + 개수 배지 + refetch → Task 9 ✓
- 테스트(백/프론트) → 각 task + Task 10 ✓
- 에러 처리(409→refetch, API 실패 toast, denylist graceful) → Task 4/8/1 ✓

**2. Placeholder scan:** 모든 코드 스텝에 완전한 코드 포함. "TBD"/"적절히 처리" 없음. ✓

**3. Type consistency:**
- 요청 바디 `{keep_id, candidate_id}` — Task 4/5 `MergeCandidateAction`, Task 7 client, Task 8 호출부 일치 ✓
- 응답 키 `merged`/`rejected` + `merge_candidates` — Task 4/5 반환, Task 8 소비 일치 ✓
- `extractMergeCandidates` 시그니처 — Task 6 정의, Task 8/9 사용 일치 ✓
- `frozenset` denylist 표현 — Task 1 정의, Task 2 필터, Task 4/5 사용 일치 ✓
- emit `'merged'` — Task 8 정의, Task 9 `@merged="onMergeApplied"` 일치 ✓
```
