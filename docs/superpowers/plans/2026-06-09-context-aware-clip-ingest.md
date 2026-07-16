# Context-aware web-clip ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest Obsidian Web Clipper markdown into a ProjectOS graph after capturing the user's intent (why/current focus/desired reflection), using that intent to guide extraction and recording it as a Capture meta node.

**Architecture:** A new MCP tool `projectos_ingest_clip` returns a `needs_context` question contract when intent is missing, otherwise saves the clip + persists intent to `captures.json` + starts parsing. During graph build the intent is injected into the per-chunk extraction prompt, and after build a `Capture` meta node is added per clipped source with `DERIVED_FROM` edges to its entities. Capture nodes carry `meta=True` and are excluded from career-graph render/health/duplicate logic via a shared `is_meta_node` predicate.

**Tech Stack:** Python 3.14, FastAPI, NetworkX, pytest. Run all commands from `src/backend/`.

---

## File Structure

- **New:** `app/services/capture_context.py` — load/save capture intent (`captures.json`), `is_complete_context`, `attach_capture_nodes`.
- **New:** `tests/test_services/test_capture_context.py`.
- **Modify:** `app/utils/graph_restructure.py` — add `is_meta_node` predicate.
- **Modify:** `app/mcp_tools.py` — `projectos_ingest_clip` schema + dispatch.
- **Modify:** `app/agents/graph_builder_agent.py` — `run(capture_context=...)` + prompt injection in `_extract_from_chunk`.
- **Modify:** `app/api/graph.py` — `_run_graph` loads captures, passes to builder, attaches Capture nodes before save.
- **Modify (exclusion):** `app/agents/obsidian_writer_agent.py`, `app/utils/graph_health.py`, `app/services/vault_reconcile.py`, `app/services/autoresearch.py`.
- **Modify (tests):** `tests/test_api/test_mcp_api.py`, `tests/test_agents/test_graph_builder.py` (or nearest existing graph-builder test file).

Notes for the implementer:
- The local-LLM extraction prompts are written in English; the three intake questions are English for consistency.
- `save_file_and_start_parse(project_id, filename, content, file_type)` returns `{"task_id", "files": [saved_filename]}`. Use `files[0]` as the capture key so it matches `chunk.source_file` downstream.
- Existing tests write directly to `Path(config.INBOX_DIR)` and `config.PROJECTS_DIR` (a conftest points these at temp dirs). Follow that pattern.

---

## Task 1: Capture-context store

**Files:**
- Create: `app/services/capture_context.py`
- Test: `tests/test_services/test_capture_context.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_services/test_capture_context.py
from app.config import config
from app.services.capture_context import (
    is_complete_context,
    load_captures,
    save_capture,
)


def test_is_complete_context():
    full = {
        "capture_reason": "r",
        "current_focus": "f",
        "reflection_intent": "i",
    }
    assert is_complete_context(full) is True
    assert is_complete_context({**full, "current_focus": "  "}) is False
    assert is_complete_context({"capture_reason": "r"}) is False
    assert is_complete_context(None) is False


def test_save_and_load_round_trip():
    pid = "cap-proj-1"
    assert load_captures(pid) == {}
    save_capture(pid, "clip.md", {
        "capture_reason": "useful method",
        "current_focus": "thesis ch3",
        "reflection_intent": "link to graph methods",
    })
    loaded = load_captures(pid)
    assert "clip.md" in loaded
    entry = loaded["clip.md"]
    assert entry["capture_reason"] == "useful method"
    assert entry["current_focus"] == "thesis ch3"
    assert entry["reflection_intent"] == "link to graph methods"
    assert entry["captured_at"]  # populated


def test_save_capture_merges_multiple_sources():
    pid = "cap-proj-2"
    save_capture(pid, "a.md", {"capture_reason": "a", "current_focus": "a", "reflection_intent": "a"})
    save_capture(pid, "b.md", {"capture_reason": "b", "current_focus": "b", "reflection_intent": "b"})
    loaded = load_captures(pid)
    assert set(loaded.keys()) == {"a.md", "b.md"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_services/test_capture_context.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.capture_context'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/capture_context.py
import json
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

from app.config import config

_REQUIRED_FIELDS = ("capture_reason", "current_focus", "reflection_intent")


def _captures_path(project_id: str) -> Path:
    return Path(config.PROJECTS_DIR) / project_id / "captures.json"


def is_complete_context(context: dict | None) -> bool:
    if not isinstance(context, dict):
        return False
    return all(str(context.get(field) or "").strip() for field in _REQUIRED_FIELDS)


def load_captures(project_id: str) -> dict[str, dict]:
    path = _captures_path(project_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_capture(project_id: str, source_file: str, context: dict) -> dict:
    captures = load_captures(project_id)
    entry = {
        "capture_reason": str(context.get("capture_reason") or "").strip(),
        "current_focus": str(context.get("current_focus") or "").strip(),
        "reflection_intent": str(context.get("reflection_intent") or "").strip(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    captures[source_file] = entry
    path = _captures_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(captures, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry


def attach_capture_nodes(graph: nx.DiGraph, captures: dict[str, dict]) -> int:
    """Add one Capture meta node per source_file with DERIVED_FROM edges to its entities."""
    added = 0
    for source_file, ctx in captures.items():
        node_id = f"capture::{source_file}"
        focus = str(ctx.get("current_focus") or "").strip()
        graph.add_node(
            node_id,
            type="Capture",
            meta=True,
            name=(focus[:60] or source_file),
            capture_reason=str(ctx.get("capture_reason") or ""),
            current_focus=focus,
            reflection_intent=str(ctx.get("reflection_intent") or ""),
            captured_at=str(ctx.get("captured_at") or ""),
            source_files=[source_file],
        )
        added += 1
        for nid, data in list(graph.nodes(data=True)):
            if nid == node_id or data.get("meta"):
                continue
            if source_file in (data.get("source_files") or []):
                graph.add_edge(node_id, nid, relation="DERIVED_FROM", meta=True)
    return added
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_services/test_capture_context.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/capture_context.py tests/test_services/test_capture_context.py
git commit -m "feat(capture): capture-context store and capture-node attachment"
```

---

## Task 2: `is_meta_node` predicate + `attach_capture_nodes` edge test

**Files:**
- Modify: `app/utils/graph_restructure.py` (add helper near top, after imports)
- Test: `tests/test_services/test_capture_context.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_services/test_capture_context.py
import networkx as nx

from app.services.capture_context import attach_capture_nodes
from app.utils.graph_restructure import is_meta_node


def test_is_meta_node():
    assert is_meta_node({"meta": True}) is True
    assert is_meta_node({"type": "Capture"}) is True
    assert is_meta_node({"type": "Category"}) is True
    assert is_meta_node({"type": "Skill"}) is False
    assert is_meta_node({}) is False


def test_attach_capture_nodes_links_source_entities():
    g = nx.DiGraph()
    g.add_node("n1", type="Skill", name="NetworkX", source_files=["clip.md"])
    g.add_node("n2", type="Project", name="Other", source_files=["other.md"])
    added = attach_capture_nodes(g, {
        "clip.md": {
            "capture_reason": "r", "current_focus": "graph work",
            "reflection_intent": "i", "captured_at": "2026-06-09T00:00:00+00:00",
        }
    })
    assert added == 1
    cap_id = "capture::clip.md"
    assert g.nodes[cap_id]["type"] == "Capture"
    assert g.nodes[cap_id]["meta"] is True
    assert g.has_edge(cap_id, "n1")
    assert g.edges[cap_id, "n1"]["relation"] == "DERIVED_FROM"
    assert not g.has_edge(cap_id, "n2")  # different source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_services/test_capture_context.py -k "meta or attach" -q`
Expected: FAIL with `ImportError: cannot import name 'is_meta_node'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/utils/graph_restructure.py` immediately after the existing imports (top of file):

```python
def is_meta_node(data: dict) -> bool:
    """True for provenance/meta nodes that must be excluded from career-graph logic."""
    return bool(data.get("meta")) or data.get("type") in {"Category", "Capture"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_services/test_capture_context.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/utils/graph_restructure.py tests/test_services/test_capture_context.py
git commit -m "feat(graph): is_meta_node predicate, verify capture-node linking"
```

---

## Task 3: `projectos_ingest_clip` MCP tool

**Files:**
- Modify: `app/mcp_tools.py` (schema in `list_mcp_tools`, dispatch in `call_mcp_tool`)
- Test: `tests/test_api/test_mcp_api.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_api/test_mcp_api.py
from pathlib import Path

from app.config import config
from app.services.project_store import project_store


def _call_clip(client, args, req_id=11):
    return client.post("/mcp", json={
        "jsonrpc": "2.0", "id": req_id, "method": "tools/call",
        "params": {"name": "projectos_ingest_clip", "arguments": args},
    }).json()["result"]


def test_mcp_ingest_clip_in_tools_list():
    from app.mcp_tools import list_mcp_tools
    names = {t["name"] for t in list_mcp_tools()}
    assert "projectos_ingest_clip" in names


def test_mcp_ingest_clip_needs_context(monkeypatch):
    from app.services.task_manager import task_manager
    project = project_store.create(name="Clip Needs Ctx", description="")
    (Path(config.INBOX_DIR) / "clip1.md").write_text("# Clipped\nbody", encoding="utf-8")
    client = TestClient(app)
    before_tasks = len(task_manager.list_all()) if hasattr(task_manager, "list_all") else None
    result = _call_clip(client, {
        "project_id": project.project_id,
        "relative_path": "clip1.md",
    })
    sc = result["structuredContent"]
    assert sc["status"] == "needs_context"
    assert {q["field"] for q in sc["required_questions"]} == {
        "capture_reason", "current_focus", "reflection_intent",
    }
    # no file saved
    assert not (Path(config.PROJECTS_DIR) / project.project_id / "files" / "clip1.md").exists()


def test_mcp_ingest_clip_ingests_with_context():
    project = project_store.create(name="Clip Ingest", description="")
    (Path(config.INBOX_DIR) / "clip2.md").write_text("# Clipped\nbody", encoding="utf-8")
    client = TestClient(app)
    result = _call_clip(client, {
        "project_id": project.project_id,
        "relative_path": "clip2.md",
        "file_type": "note",
        "capture_context": {
            "capture_reason": "useful reference",
            "current_focus": "graph ingest feature",
            "reflection_intent": "connect to ProjectOS",
        },
    })
    sc = result["structuredContent"]
    assert sc["status"] == "ingested"
    assert sc["task_id"]
    saved_name = sc["source_file"]
    assert (Path(config.PROJECTS_DIR) / project.project_id / "files" / saved_name).exists()
    from app.services.capture_context import load_captures
    captures = load_captures(project.project_id)
    assert saved_name in captures
    assert captures[saved_name]["current_focus"] == "graph ingest feature"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api/test_mcp_api.py -k clip -q`
Expected: FAIL — `projectos_ingest_clip` not in tools list / dispatch returns error.

- [ ] **Step 3a: Add the tool schema**

In `app/mcp_tools.py`, inside `list_mcp_tools()` immediately after the `projectos_ingest_inbox_files` `_tool(...)` block, add:

```python
        _tool(
            "projectos_ingest_clip",
            (
                "Ingest an Obsidian Web Clipper markdown file from the inbox into a project, "
                "capturing the user's intent first. Call without capture_context to receive the "
                "required questions (status=needs_context); ask the user, then call again with "
                "capture_context to start ingestion. The intent guides graph extraction and is "
                "recorded as a Capture node."
            ),
            {
                "project_id": {"type": "string"},
                "relative_path": {"type": "string"},
                "file_type": {
                    "type": "string",
                    "default": "auto",
                    "enum": ["auto", "cv", "paper", "report", "memo", "email", "note"],
                },
                "capture_context": {
                    "type": "object",
                    "description": "{capture_reason, current_focus, reflection_intent}. Omit to get the question contract.",
                    "properties": {
                        "capture_reason": {"type": "string"},
                        "current_focus": {"type": "string"},
                        "reflection_intent": {"type": "string"},
                    },
                },
            },
            ["project_id", "relative_path"],
        ),
```

- [ ] **Step 3b: Add the dispatch branch**

In `app/mcp_tools.py`, inside `call_mcp_tool`, immediately after the `if name == "projectos_ingest_inbox_files":` block (which ends with its `return _text_result(...)`), add:

```python
        if name == "projectos_ingest_clip":
            from app.api.projects import save_file_and_start_parse
            from app.services.capture_context import (
                is_complete_context,
                save_capture,
            )
            from app.services.inbox import read_inbox_file_for_ingest

            project_id = str(args["project_id"])
            if not project_store.get(project_id):
                raise ValueError("Project not found")
            relative_path = str(args["relative_path"])
            capture_context = args.get("capture_context")
            if not is_complete_context(capture_context):
                payload = {
                    "status": "needs_context",
                    "project_id": project_id,
                    "relative_path": relative_path,
                    "required_questions": [
                        {"field": "capture_reason",
                         "question": "Why did you capture this content?"},
                        {"field": "current_focus",
                         "question": "What are you currently working on that this relates to?"},
                        {"field": "reflection_intent",
                         "question": "How should this be reflected in your knowledge graph?"},
                    ],
                }
                return _text_result(json.dumps(payload, ensure_ascii=False), payload)

            file_payload = await read_inbox_file_for_ingest(
                relative_path,
                file_type=str(args.get("file_type") or "auto"),
            )
            result = await save_file_and_start_parse(
                project_id,
                file_payload["filename"],
                file_payload["content"],
                file_payload["file_type"],
            )
            saved_source_file = result["files"][0]
            saved_context = save_capture(project_id, saved_source_file, capture_context)
            payload = {
                "status": "ingested",
                "project_id": project_id,
                "task_id": result["task_id"],
                "source_file": saved_source_file,
                "relative_path": file_payload["relative_path"],
                "file_type": file_payload["file_type"],
                "capture_context": saved_context,
                "classification": file_payload["classification"],
            }
            return _text_result(json.dumps(payload, ensure_ascii=False), payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api/test_mcp_api.py -k clip -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/mcp_tools.py tests/test_api/test_mcp_api.py
git commit -m "feat(mcp): projectos_ingest_clip with needs_context contract"
```

---

## Task 4: Graph-builder capture-context prompt injection

**Files:**
- Modify: `app/agents/graph_builder_agent.py` (`run` signature + `_extract_from_chunk`)
- Test: `tests/test_agents/test_graph_builder.py` (append; if the file does not exist, create it)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_agents/test_graph_builder.py
import pytest

from app.agents.graph_builder_agent import GraphBuilderAgent
from app.models.graph import EdgeTypeDef, EntityTypeDef, Ontology, TextChunk


class _RecordingLLM:
    def __init__(self):
        self.prompts = []

    async def chat_json(self, messages, **kwargs):
        self.prompts.append(messages[0]["content"])
        return {"entities": [], "relations": []}


def _ontology():
    return Ontology(
        entity_types=[EntityTypeDef(name="Skill", description="")],
        edge_types=[EdgeTypeDef(name="USES_SKILL", description="")],
        analysis_summary="",
    )


def _chunk(source="clip.md"):
    return TextChunk(
        chunk_id="c1", text="NetworkX is used.", source_file=source,
        file_type="note", page_num=None, char_offset=0,
    )


@pytest.mark.asyncio
async def test_capture_context_injected_into_prompt():
    agent = GraphBuilderAgent()
    llm = _RecordingLLM()
    agent._llm = llm
    await agent.run(
        [_chunk("clip.md")],
        _ontology(),
        capture_context={"clip.md": {
            "capture_reason": "ref method",
            "current_focus": "thesis graph",
            "reflection_intent": "link methods",
        }},
    )
    assert any("Capture intent for this source" in p for p in llm.prompts)
    assert any("thesis graph" in p for p in llm.prompts)


@pytest.mark.asyncio
async def test_no_capture_context_leaves_prompt_clean():
    agent = GraphBuilderAgent()
    llm = _RecordingLLM()
    agent._llm = llm
    await agent.run([_chunk("clip.md")], _ontology())
    assert all("Capture intent for this source" not in p for p in llm.prompts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_agents/test_graph_builder.py -k capture -q`
Expected: FAIL — `run()` got an unexpected keyword argument `capture_context`.

- [ ] **Step 3a: Add the `capture_context` parameter to `run`**

In `app/agents/graph_builder_agent.py`, change the `run` signature (currently ends with `progress_callback: ... = None,`) to add the new kwarg, and set it on `self` at the top of the method body (right after `graph = nx.DiGraph()`):

```python
    async def run(
        self,
        chunks: list[TextChunk],
        ontology: Ontology,
        incremental: bool = False,
        graph_path: str | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        capture_context: dict[str, dict] | None = None,
    ) -> nx.DiGraph:
        graph = nx.DiGraph()
        self._capture_context = capture_context or {}
```

- [ ] **Step 3b: Inject the preamble in `_extract_from_chunk`**

In `_extract_from_chunk`, after the line `doc_rules_block = f"\n{doc_rules}\n" if doc_rules else ""`, add:

```python
        capture = getattr(self, "_capture_context", {}).get(chunk.source_file)
        capture_block = ""
        if capture:
            capture_block = (
                "\nCapture intent for this source:\n"
                f"- Reason captured: {capture.get('capture_reason', '')}\n"
                f"- User is currently working on: {capture.get('current_focus', '')}\n"
                f"- Desired reflection: {capture.get('reflection_intent', '')}\n"
                "Prioritize entities and relations relevant to this intent. "
                "Do not invent entities unrelated to the source text.\n"
            )
```

Then insert `{capture_block}` into the prompt f-string, immediately after the opening line `Extract entities and relations from the text below.` and before `{user_ctx}`:

```python
        prompt = f"""Extract entities and relations from the text below.
{capture_block}{user_ctx}
Allowed entity types: {', '.join(entity_types)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_agents/test_graph_builder.py -k capture -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/agents/graph_builder_agent.py tests/test_agents/test_graph_builder.py
git commit -m "feat(graph-builder): inject capture intent into extraction prompt"
```

---

## Task 5: Wire captures into `_run_graph` and attach Capture nodes

**Files:**
- Modify: `app/api/graph.py` (`_run_graph`)
- Test: `tests/test_agents/test_graph_builder.py` (append — integration-style on the helper path)

Note: `_run_graph` is a long async pipeline that is awkward to unit-test end-to-end. The new wiring is small and mechanical; the behavior of `attach_capture_nodes` is already covered in Task 2. Add one focused test asserting that, given a `captures.json`, the attach step produces a Capture node joined to a same-source entity. This test exercises the integration contract (`load_captures` + `attach_capture_nodes`) used by `_run_graph`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_agents/test_graph_builder.py
import networkx as nx

from app.config import config
from pathlib import Path


def test_run_graph_capture_integration_contract(tmp_path, monkeypatch):
    # Simulate what _run_graph does: load captures, attach nodes to a built graph.
    from app.services.capture_context import (
        attach_capture_nodes,
        load_captures,
        save_capture,
    )
    pid = "rg-cap-1"
    save_capture(pid, "clip.md", {
        "capture_reason": "r", "current_focus": "focus", "reflection_intent": "i",
    })
    g = nx.DiGraph()
    g.add_node("s1", type="Skill", name="NetworkX", source_files=["clip.md"])
    captures = load_captures(pid)
    attach_capture_nodes(g, captures)
    assert g.nodes["capture::clip.md"]["type"] == "Capture"
    assert g.has_edge("capture::clip.md", "s1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_agents/test_graph_builder.py -k run_graph_capture -q`
Expected: PASS only after Tasks 1-2 are merged (it depends on `attach_capture_nodes`). If those are already merged it will PASS immediately — in that case treat this as a regression guard and proceed to wire `_run_graph` in Step 3.

- [ ] **Step 3a: Pass captures to the GraphBuilderAgent branch**

In `app/api/graph.py`, inside `_run_graph`, before the `if config.GRAPH_BUILD_MODE == "claude_task":` branch (around the `graph_path = str(proj_dir / "graph.json")` line), load captures:

```python
        from app.services.capture_context import attach_capture_nodes, load_captures
        captures = load_captures(project_id)
```

Then in the `else:` branch call (currently lines ~335-341), add the `capture_context` kwarg:

```python
        else:
            graph = await graph_agent.run(
                chunks,
                ontology,
                incremental=incremental,
                graph_path=graph_path,
                progress_callback=on_chunk_progress,
                capture_context=captures,
            )
```

(The `claude_task` branch keeps its existing signature; Capture nodes are still attached in Step 3b for both branches.)

- [ ] **Step 3b: Attach Capture nodes before save**

Still in `_run_graph`, immediately before the existing `graph_agent.save(graph, graph_path)` line, add:

```python
        if captures:
            capture_added = attach_capture_nodes(graph, captures)
            if capture_added:
                logger.info(f"Capture meta nodes attached: {capture_added}")
```

- [ ] **Step 4: Run test + import sanity**

Run: `python3 -m pytest tests/test_agents/test_graph_builder.py -q`
Expected: PASS. Also run `python3 -c "import app.api.graph"` — expected: no error.

- [ ] **Step 5: Commit**

```bash
git add app/api/graph.py tests/test_agents/test_graph_builder.py
git commit -m "feat(graph): wire capture intent into build and attach Capture nodes"
```

---

## Task 6: Exclude Capture/meta nodes from career-graph consumers

**Files:**
- Modify: `app/agents/obsidian_writer_agent.py`, `app/utils/graph_health.py`, `app/services/vault_reconcile.py`, `app/services/autoresearch.py`
- Test: `tests/test_services/test_capture_context.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_services/test_capture_context.py
import networkx as nx

from app.utils import graph_health


def _graph_with_capture():
    g = nx.DiGraph()
    g.add_node("s1", type="Skill", name="NetworkX", source_files=["clip.md"])
    g.add_node("capture::clip.md", type="Capture", meta=True,
               name="focus", source_files=["clip.md"])
    g.add_edge("capture::clip.md", "s1", relation="DERIVED_FROM", meta=True)
    return g


def test_health_isolated_excludes_capture():
    g = _graph_with_capture()
    g.add_node("lonely", type="Skill", name="Lonely")
    isolated = graph_health.check_isolated_nodes(g)
    ids = {item["node_id"] for item in isolated}
    assert "lonely" in ids
    assert "capture::clip.md" not in ids


def test_obsidian_writer_skips_capture_page():
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent
    agent = ObsidianWriterAgent()
    index_md = agent._render_index(_graph_with_capture())
    assert "NetworkX" in index_md
    assert "focus" not in index_md  # Capture node not listed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_services/test_capture_context.py -k "health or writer" -q`
Expected: FAIL — `capture::clip.md` appears in isolated nodes / Capture name appears in index.

(Note: in `_graph_with_capture` the Capture node has a DERIVED_FROM edge so it is not strictly degree-0; the isolated test relies on the explicit assertion that it is excluded by predicate, not just by degree. Keep the assertion.)

- [ ] **Step 3a: obsidian_writer_agent.py**

Add import at top: `from app.utils.graph_restructure import is_meta_node`.

Change the page-node list (currently `if data.get("type") != "Category"`):

```python
        nodes = [
            (node_id, data)
            for node_id, data in graph.nodes(data=True)
            if not is_meta_node(data)
        ]
```

In `_render_index`, change `if ntype == "Category":` to:

```python
            if is_meta_node(data):
                continue
```

In `_render_canvas`, find the node iteration that currently skips `Category` and apply the same `is_meta_node(data)` guard (mirror the existing Category skip). If the canvas iterates `graph.nodes(data=True)`, add `if is_meta_node(data): continue` at the top of that loop.

- [ ] **Step 3b: graph_health.py**

Add import at top: `from app.utils.graph_restructure import is_meta_node`.

In each node-iterating function, skip meta nodes:
- `check_isolated_nodes`: after `for node_id in graph.nodes:` add
  `if is_meta_node(graph.nodes[node_id]): continue`
- `check_weak_components`: inside `for nid in comp:` add
  `if is_meta_node(graph.nodes[nid]): continue`
- `check_duplicate_candidates`: inside `for node_id, data in graph.nodes(data=True):` add
  `if is_meta_node(data): continue`
- `check_hub_nodes`: after `for node_id in graph.nodes:` add
  `if is_meta_node(graph.nodes[node_id]): continue`
- `check_wiki_graph_consistency`: inside the `for node_id, data in graph.nodes(data=True):` loop(s) add
  `if is_meta_node(data): continue`

- [ ] **Step 3c: vault_reconcile.py**

Add import at top: `from app.utils.graph_restructure import is_meta_node`.

Where it builds expected pages from the rendered graph (currently `if data.get("type") == "Category": continue`), change to:

```python
        if is_meta_node(data):
            continue
```

Where it diffs rendered edges and skips Category→Category (lines using `rendered.nodes[u].get("type") == "Category"`), also skip any edge touching a meta node:

```python
        if is_meta_node(rendered.nodes[u]) or is_meta_node(rendered.nodes[v]):
            continue
```

- [ ] **Step 3d: autoresearch.py**

In `_find_duplicate_pairs`, change `if _is_category(data):` to:

```python
        if _is_category(data) or data.get("meta"):
            continue
```

(`_eligible` already excludes Capture because `type="Capture"` is not in the allowed domain types, so isolated/sparse/source candidates are already safe.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_services/test_capture_context.py -q`
Expected: PASS (all capture tests green)

- [ ] **Step 5: Commit**

```bash
git add app/agents/obsidian_writer_agent.py app/utils/graph_health.py app/services/vault_reconcile.py app/services/autoresearch.py tests/test_services/test_capture_context.py
git commit -m "feat(graph): exclude Capture/meta nodes from render, health, reconcile, dedup"
```

---

## Task 7: Full-suite verification and handoff

**Files:**
- Modify: `docs/claude-code-handoff.md` (prepend a dated entry)

- [ ] **Step 1: Run the full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS — baseline was 446; expect 446 + new tests (≈ 446 + 9 capture/health/writer + 4 MCP clip + 4 graph-builder = ~463). Confirm no regressions (0 failed).

- [ ] **Step 2: Manual import sanity**

Run: `python3 -c "import app.main; from app.mcp_tools import list_mcp_tools; print('ingest_clip' in {t['name'] for t in list_mcp_tools()})"`
Expected: prints `True`, no import errors.

- [ ] **Step 3: Update the handoff**

Prepend a dated section to `docs/claude-code-handoff.md` summarizing: the feature (context-aware web-clip ingest), the `needs_context` contract, intent prompt injection, Capture meta node + `is_meta_node` exclusion wiring, the spec/plan paths, the final test count, and the YAGNI non-goals (no URL fetch, no frontend/REST, no current-work auto-link).

- [ ] **Step 4: Commit**

```bash
git add docs/claude-code-handoff.md
git commit -m "docs(handoff): context-aware web-clip ingest"
```

- [ ] **Step 5: Finish the branch**

Invoke the `superpowers:finishing-a-development-branch` skill to decide merge/PR/cleanup for the work on `hybrid-retrieval`.

---

## Self-review notes

- **Spec coverage:** store (Task 1), needs_context MCP contract (Task 3), prompt injection (Task 4), Capture meta node + DERIVED_FROM (Tasks 1/5), exclusion wiring across the five consumers (Task 6 — autoresearch `_eligible` already safe, documented), inbox input reuse (Task 3 via `read_inbox_file_for_ingest`). All spec sections map to a task.
- **Type/name consistency:** `is_complete_context`, `load_captures`, `save_capture`, `attach_capture_nodes`, `is_meta_node` are used with identical signatures across tasks. Capture node id format `capture::{source_file}`, edge relation `DERIVED_FROM`, flag `meta=True` are consistent everywhere.
- **No placeholders:** every code step shows full code; exclusion edits name exact functions/lines to change.
