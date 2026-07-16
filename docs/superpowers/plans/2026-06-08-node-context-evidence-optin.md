# node_context Evidence Opt-in Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `include_evidence` mode to `projectos_get_node_context` so Claude Desktop can fetch source-chunk excerpts (with citation labels) for a node only when needed, keeping the default response low-token.

**Architecture:** The pure deterministic service `get_node_context` gains an optional pre-fetched `evidence` parameter (no I/O, no embeddings). The async MCP wrapper performs `hybrid_search` over chunks (keyword fallback when no embedding index) and injects the evidence list. Evidence is a separate top-level key, never inside `counts`, and is omitted entirely when not requested — so existing strict-equality tests stay valid.

**Tech Stack:** Python, networkx, pytest, existing `app.utils.hybrid_retrieval.hybrid_search`, `app.models.graph.TextChunk`, citation label format from `QueryAgent._chunk_source_label`.

---

## Context the engineer needs

- The token-saving tools already exist as uncommitted WIP: `app/services/graph_context.py`
  (`summarize_graph_context`, `get_node_context`, `get_subgraph_context`) plus MCP wiring in
  `app/mcp_tools.py` and tests in `tests/test_services/test_graph_context.py` /
  `tests/test_api/test_mcp_api.py`. Do NOT rewrite these. This plan only ADDS evidence opt-in.
- `get_node_context` current signature:
  `get_node_context(graph, node_name, node_type=None, max_neighbors=20)`.
  It returns a dict with keys `kind, read_only, query, match, counts, limits, node, edges`.
- Existing MCP test asserts `node_payload["counts"] == {"in_edges": 1, "out_edges": 1, "neighbors": 2}`
  with EXACT dict equality. Therefore evidence MUST NOT be added to `counts`. Put it at top level
  as `"evidence"` and only when requested.
- Citation label format must match QueryAgent: `[source_file#chunk_id p.N char:offset]`
  (`QueryAgent._chunk_source_label(chunk)` is a staticmethod — callable without constructing the agent).
- In the test env `EMBEDDING_BASE_URL` is unset, so `hybrid_search` falls back to keyword-only
  ranking over the provided `items` dict. Evidence assembly therefore works in tests without embeddings.

## File Structure

- Modify: `src/backend/app/services/graph_context.py` — add optional `evidence` param to `get_node_context`.
- Test: `src/backend/tests/test_services/test_graph_context.py` — unit tests for evidence included/omitted.
- Modify: `src/backend/app/mcp_tools.py` — `projectos_get_node_context` block: add `include_evidence`/`max_evidence`, fetch + inject evidence; update tools/list schema (UNCOMMITTED WIP file — stays in working tree).
- Test: `src/backend/tests/test_api/test_mcp_api.py` — MCP-level evidence test (UNCOMMITTED WIP file).

---

### Task 1: Service — optional pre-fetched `evidence` on `get_node_context`

**Files:**
- Modify: `src/backend/app/services/graph_context.py`
- Test: `src/backend/tests/test_services/test_graph_context.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_services/test_graph_context.py`:

```python
def test_get_node_context_includes_pre_fetched_evidence_when_provided():
    evidence = [
        {"label": "[cv.pdf#c1 p.1 char:0]", "text": "ProjectOS builds a graph."},
        {"label": "[readme.md#c2 p.1 char:0]", "text": "ProjectOS syncs to Obsidian."},
    ]
    payload = get_node_context(
        _graph(), "ProjectOS", node_type="Project", max_neighbors=3, evidence=evidence
    )
    assert payload["evidence"] == evidence
    # evidence must stay OUT of counts (strict-equality consumers depend on counts shape)
    assert "evidence" not in payload["counts"]


def test_get_node_context_omits_evidence_key_when_not_provided():
    payload = get_node_context(_graph(), "ProjectOS", node_type="Project", max_neighbors=3)
    assert "evidence" not in payload


def test_get_node_context_includes_empty_evidence_list_when_explicitly_empty():
    payload = get_node_context(
        _graph(), "ProjectOS", node_type="Project", max_neighbors=3, evidence=[]
    )
    assert payload["evidence"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python3 -m pytest tests/test_services/test_graph_context.py -q -k evidence`
Expected: FAIL — `get_node_context() got an unexpected keyword argument 'evidence'`

- [ ] **Step 3: Add the `evidence` parameter**

In `src/backend/app/services/graph_context.py`, change the `get_node_context` signature from:

```python
def get_node_context(
    graph: nx.DiGraph,
    node_name: str,
    node_type: str | None = None,
    max_neighbors: int = 20,
) -> dict[str, Any]:
```

to:

```python
def get_node_context(
    graph: nx.DiGraph,
    node_name: str,
    node_type: str | None = None,
    max_neighbors: int = 20,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
```

Then in BOTH `return` dicts of `get_node_context` (the `selected is None` early-return and the
final return), append the evidence key conditionally. Do this by building the result dict then
attaching evidence before returning. Replace the early-return block:

```python
    if selected is None:
        return {
            "kind": "node_context",
            "read_only": True,
            "query": {"name": node_name, "type": node_type},
            "match": metadata,
            "counts": {"in_edges": 0, "out_edges": 0, "neighbors": 0},
            "limits": {"max_neighbors": limit},
            "node": None,
            "edges": {"in": [], "out": []},
        }
```

with:

```python
    if selected is None:
        result = {
            "kind": "node_context",
            "read_only": True,
            "query": {"name": node_name, "type": node_type},
            "match": metadata,
            "counts": {"in_edges": 0, "out_edges": 0, "neighbors": 0},
            "limits": {"max_neighbors": limit},
            "node": None,
            "edges": {"in": [], "out": []},
        }
        if evidence is not None:
            result["evidence"] = list(evidence)
        return result
```

And replace the final return:

```python
    return {
        "kind": "node_context",
        "read_only": True,
        "query": {"name": node_name, "type": node_type},
        "match": metadata,
        "counts": {
            "in_edges": len(incoming),
            "out_edges": len(outgoing),
            "neighbors": len({item.get("from") or item.get("to") for item in incoming + outgoing}),
        },
        "limits": {"max_neighbors": limit},
        "node": _node_summary(graph, selected),
        "edges": {
            "in": [item for item in selected_edges if item["direction"] == "in"],
            "out": [item for item in selected_edges if item["direction"] == "out"],
        },
    }
```

with:

```python
    result = {
        "kind": "node_context",
        "read_only": True,
        "query": {"name": node_name, "type": node_type},
        "match": metadata,
        "counts": {
            "in_edges": len(incoming),
            "out_edges": len(outgoing),
            "neighbors": len({item.get("from") or item.get("to") for item in incoming + outgoing}),
        },
        "limits": {"max_neighbors": limit},
        "node": _node_summary(graph, selected),
        "edges": {
            "in": [item for item in selected_edges if item["direction"] == "in"],
            "out": [item for item in selected_edges if item["direction"] == "out"],
        },
    }
    if evidence is not None:
        result["evidence"] = list(evidence)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src/backend && python3 -m pytest tests/test_services/test_graph_context.py -q`
Expected: PASS (existing 6 + 3 new = 9 passed)

- [ ] **Step 5: Commit (clean service + unit test only)**

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS
git add src/backend/app/services/graph_context.py src/backend/tests/test_services/test_graph_context.py
git commit -m "$(cat <<'EOF'
feat(graph-context): optional pre-fetched evidence in get_node_context

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

Note: `graph_context.py` and its unit test may currently be untracked WIP. If `git add` stages
more than intended, stage only these two paths (already specified above).

---

### Task 2: MCP wrapper — `include_evidence` / `max_evidence` args + evidence assembly

**Files:**
- Modify: `src/backend/app/mcp_tools.py` (tools/list schema ~line 221-231; tool dispatch ~line 782-802)
- Test: `src/backend/tests/test_api/test_mcp_api.py`

- [ ] **Step 1: Write the failing MCP test**

Append a new test to `tests/test_api/test_mcp_api.py`. Mirror the setup of the existing graph-context
test (the one that posts `projectos_get_node_context`). Place this test next to it; reuse the same
project/graph fixture pattern already used there (a project with a `Project:ProjectOS` node and at
least one chunk in `chunks.json`). Concretely:

```python
def test_mcp_get_node_context_include_evidence_attaches_labeled_chunks(client, tmp_path):
    # Arrange: create project, write graph.json with a Project:ProjectOS node,
    # and write chunks.json containing a chunk whose text mentions "ProjectOS".
    # (Follow the exact arrangement used by the existing graph-context MCP test in this file.)
    project = _make_project_with_graph_and_chunks(
        client,
        chunks=[
            {
                "chunk_id": "c1",
                "text": "ProjectOS builds a NetworkX graph from local files.",
                "source_file": "cv.pdf",
                "page_num": 1,
                "char_offset": 0,
            }
        ],
    )

    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {
                "name": "projectos_get_node_context",
                "arguments": {
                    "project_id": project.project_id,
                    "node_name": "ProjectOS",
                    "node_type": "Project",
                    "include_evidence": True,
                    "max_evidence": 2,
                },
            },
        },
    )

    payload = resp.json()["result"]["structuredContent"]
    assert resp.json()["result"]["isError"] is False
    assert "evidence" in payload
    assert len(payload["evidence"]) >= 1
    first = payload["evidence"][0]
    assert first["label"] == "[cv.pdf#c1 p.1 char:0]"
    assert "ProjectOS" in first["text"]
    # counts shape unchanged
    assert set(payload["counts"]) == {"in_edges", "out_edges", "neighbors"}
```

IMPORTANT: There may be no `_make_project_with_graph_and_chunks` helper. If the existing test
inlines its arrangement, inline the same steps here instead of inventing a helper: create the
project via `project_store.create`, write `graph.json` (node-link with a `Project:ProjectOS` node),
and write `chunks.json` with the single chunk above into `config.PROJECTS_DIR/<id>/`. Match exactly
how the existing graph-context MCP test sets up its project.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd src/backend && python3 -m pytest tests/test_api/test_mcp_api.py -q -k include_evidence`
Expected: FAIL — `evidence` key absent (wrapper does not yet build it).

- [ ] **Step 3: Update the tools/list schema for node_context**

In `src/backend/app/mcp_tools.py`, replace the `projectos_get_node_context` `_tool(...)` schema
(currently around lines 221-231):

```python
        _tool(
            "projectos_get_node_context",
            "Return compact read-only one-hop graph context for a node name or id.",
            {
                "project_id": {"type": "string"},
                "node_name": {"type": "string"},
                "node_type": {"type": "string", "default": ""},
                "max_neighbors": {"type": "integer", "minimum": 0, "maximum": 100, "default": 20},
            },
            ["project_id", "node_name"],
        ),
```

with:

```python
        _tool(
            "projectos_get_node_context",
            "Return compact read-only one-hop graph context for a node name or id. "
            "Set include_evidence=true to also attach up to max_evidence source-chunk "
            "excerpts with citation labels.",
            {
                "project_id": {"type": "string"},
                "node_name": {"type": "string"},
                "node_type": {"type": "string", "default": ""},
                "max_neighbors": {"type": "integer", "minimum": 0, "maximum": 100, "default": 20},
                "include_evidence": {"type": "boolean", "default": False},
                "max_evidence": {"type": "integer", "minimum": 0, "maximum": 10, "default": 3},
            },
            ["project_id", "node_name"],
        ),
```

- [ ] **Step 4: Build and inject evidence in the dispatch block**

In `src/backend/app/mcp_tools.py`, replace the `projectos_get_node_context` dispatch block
(currently around lines 782-802):

```python
        if name == "projectos_get_node_context":
            from app.services.graph_context import get_node_context

            project_id = str(args["project_id"])
            _require_project(project_id)
            graph = _load_graph(project_id)
            payload = get_node_context(
                graph,
                str(args["node_name"]),
                node_type=str(args.get("node_type") or "") or None,
                max_neighbors=int(args.get("max_neighbors", 20)),
            )
            payload["project_id"] = project_id
            selected = payload["match"]["selected_id"] or "not found"
            text = "\n".join([
                "Node context",
                f"Selected: {selected}",
                f"In edges: {payload['counts']['in_edges']}",
                f"Out edges: {payload['counts']['out_edges']}",
            ])
            return _text_result(text, payload)
```

with:

```python
        if name == "projectos_get_node_context":
            from app.agents.query_agent import QueryAgent
            from app.services.graph_context import get_node_context
            from app.utils.hybrid_retrieval import hybrid_search

            project_id = str(args["project_id"])
            _require_project(project_id)
            graph = _load_graph(project_id)
            node_name = str(args["node_name"])
            node_type = str(args.get("node_type") or "") or None
            max_neighbors = int(args.get("max_neighbors", 20))

            evidence = None
            if bool(args.get("include_evidence", False)):
                max_evidence = int(args.get("max_evidence", 3))
                chunks = _load_chunks(project_id)
                evidence = []
                if chunks and max_evidence > 0:
                    items = {c.chunk_id: c.text for c in chunks}
                    ranked = await hybrid_search(
                        node_name, project_id, "chunks", items, top_n=max_evidence)
                    by_id = {c.chunk_id: c for c in chunks}
                    evidence = [
                        {
                            "label": QueryAgent._chunk_source_label(by_id[cid]),
                            "text": by_id[cid].text,
                        }
                        for cid in ranked
                        if cid in by_id
                    ]

            payload = get_node_context(
                graph,
                node_name,
                node_type=node_type,
                max_neighbors=max_neighbors,
                evidence=evidence,
            )
            payload["project_id"] = project_id
            selected = payload["match"]["selected_id"] or "not found"
            text = "\n".join([
                "Node context",
                f"Selected: {selected}",
                f"In edges: {payload['counts']['in_edges']}",
                f"Out edges: {payload['counts']['out_edges']}",
            ])
            return _text_result(text, payload)
```

- [ ] **Step 5: Run the targeted test, then the MCP suite**

Run: `cd src/backend && python3 -m pytest tests/test_api/test_mcp_api.py -q -k include_evidence`
Expected: PASS

Run: `cd src/backend && python3 -m pytest tests/test_api/test_mcp_api.py -q`
Expected: PASS (all existing MCP tests + new one)

- [ ] **Step 6: Do NOT commit the MCP wiring separately**

`app/mcp_tools.py` and `tests/test_api/test_mcp_api.py` carry the user's unrelated uncommitted WIP.
Per the established handoff policy (#1-#5 wiring), leave these two files in the working tree to be
committed together with the user's WIP. Only Task 1's service + unit test are committed cleanly.

---

### Task 3: Full regression + handoff note

**Files:**
- Modify: `docs/claude-code-handoff.md`

- [ ] **Step 1: Run the full backend suite**

Run: `cd src/backend && python3 -m pytest tests/ -q`
Expected: PASS — baseline was 437; expect 437 + 3 service + 1 MCP = 441 passed.

- [ ] **Step 2: Append a handoff entry**

Add a dated section to `docs/claude-code-handoff.md` recording: the discovery that the three
token-saving tools already existed as WIP; that this work added only `include_evidence` opt-in to
`get_node_context`; the citation-label format reuse; verification count; and that the MCP wiring
stays uncommitted per policy while the service + unit test are committed.

- [ ] **Step 3: Commit the handoff + spec/plan docs**

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS
git add docs/claude-code-handoff.md docs/superpowers/plans/2026-06-08-node-context-evidence-optin.md
git commit -m "$(cat <<'EOF'
docs: record node_context evidence opt-in and graph-context WIP discovery

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

- **Spec coverage:** The revised spec's actual scope ("include_evidence opt-in on get_node_context")
  is implemented by Task 1 (service param) + Task 2 (MCP fetch/inject + schema). graph_summary/
  subgraph already exist and are explicitly out of scope. Covered.
- **Placeholder scan:** No TBD/TODO. The one soft spot is Task 2 Step 1's test arrangement, which
  depends on the existing test's setup style; the step instructs inlining the exact existing
  arrangement rather than inventing helpers. Acceptable — the engineer reads the neighboring test.
- **Type consistency:** `get_node_context(..., evidence=...)` signature matches between Task 1
  (definition) and Task 2 (call site). Evidence item shape `{"label","text"}` is consistent across
  service tests, MCP test, and the wrapper assembly. `QueryAgent._chunk_source_label` returns the
  `[file#chunk p.N char:off]` format asserted in the MCP test.
- **counts invariant:** evidence is never added to `counts`; existing strict-equality MCP test stays valid.
