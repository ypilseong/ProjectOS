# Context-aware web-clip ingest — Design

Date: 2026-06-09
Branch: hybrid-retrieval
Status: approved (brainstorming)

## Problem

The user clips web content with **Obsidian Web Clipper**, which writes a clean
markdown file into the synced inbox (`project-inbox/<device>/...`). ProjectOS
should ingest that clip into the project graph. Unlike a passive file upload, a
clip carries *intent*: the user captured it for a reason and wants it reflected
in their knowledge graph in a particular way.

Therefore, before analysis, the ingest path must **ask the user three questions**
and use the answers to (1) guide entity/relation extraction and (2) record the
capture intent in the graph.

This is **not** a URL fetch/clean feature — Obsidian Web Clipper already produces
the markdown. ProjectOS only consumes the resulting `.md` from the inbox.

## Capture intent (the three questions)

Asked in English to stay consistent with the local-LLM extraction prompts.

1. `capture_reason` — "Why did you capture this content?"
2. `current_focus` — "What are you currently working on that this relates to?"
3. `reflection_intent` — "How should this be reflected in your knowledge graph?"

All three are required. A blank in any field means the context is incomplete.

## Architecture

```
Obsidian Web Clipper → project-inbox/<device>/<clip>.md
        │
        ▼
projectos_ingest_clip (MCP)
   ├─ capture_context missing/incomplete → return needs_context (no side effects)
   └─ complete → save_file_and_start_parse + persist captures.json + parse
        │
        ▼
build_graph (_run_graph)
   ├─ load captures.json → pass to GraphBuilderAgent.run(capture_context=...)
   ├─ inject per-source intent preamble into chunk extraction prompt
   └─ add Capture meta node per clipped source + DERIVED_FROM edges to its entities
```

### 1. Capture-context store — `app/services/capture_context.py`

Deterministic, file-backed helpers over `projects/{id}/captures.json`.

- `load_captures(project_id) -> dict[str, dict]` — map `source_file → context`,
  `{}` if the file is missing.
- `save_capture(project_id, source_file, context)` — merge/overwrite the entry
  for one source file, persist atomically (write full map).
- Context shape persisted:
  `{capture_reason, current_focus, reflection_intent, captured_at}`
  (`captured_at` = ISO timestamp set at save time).
- `is_complete_context(context) -> bool` — all three text fields non-empty after
  strip. Shared by the MCP tool.

The store keys on the **saved project filename** (the sanitized name produced by
`save_file_and_start_parse`), so the later graph build can join by
`chunk.source_file`.

### 2. MCP tool — `projectos_ingest_clip`

Added to `list_mcp_tools()` schema and dispatched in `mcp_tools.py`.

Arguments:
- `project_id` (string, required)
- `relative_path` (string, required) — inbox-relative path to the clipped `.md`.
- `file_type` (string, default `"auto"`) — reuses inbox classification; clips are
  usually `note`, but `auto` lets the local LLM classify.
- `capture_context` (object, optional) — `{capture_reason, current_focus,
  reflection_intent}`.

Behavior:
- Validate `project_id` exists (else error, consistent with other tools).
- If `capture_context` is absent or `is_complete_context` is false →
  return **no-side-effect** payload:
  ```json
  {
    "status": "needs_context",
    "relative_path": "...",
    "required_questions": [
      {"field": "capture_reason", "question": "Why did you capture this content?"},
      {"field": "current_focus", "question": "What are you currently working on that this relates to?"},
      {"field": "reflection_intent", "question": "How should this be reflected in your knowledge graph?"}
    ]
  }
  ```
  No file is saved and no parse task is started. Claude Desktop asks the user,
  collects answers, and re-calls with `capture_context` filled.
- If complete → `read_inbox_file_for_ingest(relative_path, file_type)` →
  `save_file_and_start_parse(project_id, filename, content, file_type)` →
  `save_capture(project_id, saved_source_file, capture_context)` → return:
  ```json
  {
    "status": "ingested",
    "task_id": "...",
    "source_file": "<saved filename>",
    "file_type": "...",
    "capture_context": { ... },
    "classification": { ... }
  }
  ```

`save_file_and_start_parse` returns `files: [saved_filename]`; the tool uses that
saved name as the capture key so it matches `chunk.source_file` downstream.

### 3. Extraction-prompt injection — `GraphBuilderAgent`

- `run(...)` gains optional `capture_context: dict[str, dict] | None` (keyed by
  `source_file`). Stored on the agent for the duration of the build.
- The per-chunk extraction prompt (`extract_one`) looks up
  `capture_context.get(chunk.source_file)`. If present, a short preamble is
  prepended to the prompt:
  ```
  Capture intent for this source:
  - Reason captured: {capture_reason}
  - User is currently working on: {current_focus}
  - Desired reflection: {reflection_intent}
  Prioritize entities and relations relevant to this intent. Do not invent
  entities unrelated to the source text.
  ```
- When `capture_context` is None or the source has no entry, the prompt is
  unchanged (full backward compatibility for normal uploads).
- `_run_graph` loads `captures.json` via `load_captures(project_id)` and passes
  it to `graph_agent.run(...)` for both `GraphBuilderAgent` and
  `ClaudeTaskGraphBuilderAgent` branches. (If the Claude-task branch cannot
  accept the kwarg cleanly, it is passed only where supported; the meta-node
  recording in step 4 still runs.)

### 4. Capture meta node + exclusion wiring

Meta-node recording runs in `_run_graph` **after** `graph_agent.run(...)` returns
and **before** save, so it applies uniformly to both the `GraphBuilderAgent` and
`ClaudeTaskGraphBuilderAgent` branches. (Only the prompt injection in step 3
lives inside `GraphBuilderAgent`.) For each `source_file` that has a capture
entry:

- Add a node:
  - `id = f"capture::{source_file}"`
  - `type = "Capture"`, `meta = True`
  - `name` = short label derived from `current_focus` (truncated) or the filename
  - attributes: `capture_reason`, `current_focus`, `reflection_intent`,
    `source_files = [source_file]`, `captured_at`
- For every domain node whose `source_files` includes `source_file`, add a
  directed edge `Capture --DERIVED_FROM--> entity` with `meta = True`.

`Capture` is a **meta/provenance** node, not one of the nine fixed domain entity
types. To honor the "fixed 9 types, no abstract types" rule and avoid polluting
career-graph operations, add a shared predicate and exclude meta nodes/edges at
the same points where `type == "Category"` is already excluded:

- `app/utils/graph_restructure.py` — `is_meta_node(data) -> bool` returning
  `bool(data.get("meta")) or data.get("type") in {"Category", "Capture"}`
  (single source of truth; reuse the existing Category checks by routing them
  through the predicate where practical).
- Exclusion points to wire (mirror existing Category handling):
  - `app/agents/obsidian_writer_agent.py` — render/demote/canvas (no page or hub
    for Capture nodes).
  - `app/utils/graph_health.py` — exclude from node/type counts and health
    findings.
  - `app/services/autoresearch.py` — exclude from candidates (already excludes
    Category; extend to meta).
  - `app/agents/profile_agent.py` — Person selection already type-scoped; verify
    Capture is ignored.
  - `app/services/vault_reconcile.py` — exclude Capture from render-aware diff so
    it never produces vault pages or delete candidates.

This keeps the meta nodes queryable in `graph.json` (the graph "remembers" why a
source was added) while leaving all career-graph metrics, vault rendering, and
autoresearch behavior unchanged.

### 5. Input location assumption

Clipped `.md` files arrive in the existing inbox (`project-inbox/<device>/...`)
via Syncthing, exactly like other inbox files. `projectos_ingest_clip` takes an
inbox-relative `relative_path`, reusing `resolve_inbox_path` /
`read_inbox_file_for_ingest`. No new sync mechanism.

## Testing (TDD)

- **capture_context store** (`tests/test_services/test_capture_context.py`):
  save then load round-trip; merge/overwrite per source; missing file → `{}`;
  `is_complete_context` true/false cases; `captured_at` populated.
- **MCP `projectos_ingest_clip`** (`tests/test_api/test_mcp_api.py`):
  - missing/incomplete `capture_context` → `status == "needs_context"`, three
    required questions, **no file written, no task created**.
  - complete context → `status == "ingested"`, task created, `captures.json`
    written with the saved source filename, capture fields persisted.
  - tools/list includes `projectos_ingest_clip` with the documented schema.
- **GraphBuilderAgent injection** (`tests/test_agents/test_graph_builder*.py`):
  - with `capture_context` for a source, the extraction prompt contains the
    intent preamble (assert via the LLM seam/mock).
  - without capture_context the prompt is unchanged (regression guard).
- **Capture meta node** (graph builder / restructure tests):
  - Capture node added with `meta=True` and `DERIVED_FROM` edges to entities of
    that source.
  - `is_meta_node` predicate truth table.
  - at least one consumer exclusion test (e.g., graph_health counts ignore
    Capture; obsidian render produces no Capture page).

## Scope / non-goals (YAGNI)

- No backend URL fetching or HTML→markdown cleaning (Obsidian Web Clipper owns
  that step).
- No frontend UI and no REST endpoint in this iteration — MCP tool + service
  only. (Can be added later if needed.)
- No automatic linking of the clip to a "current work / project" node. The intent
  is recorded on the Capture node and its `DERIVED_FROM` edges only.
- No de-duplication or "skip re-asking" logic for re-ingesting the same clip;
  each ingest captures fresh intent.
- No change to existing upload/inbox tools; `projectos_ingest_inbox_file`
  remains for context-free ingest.

## Affected files

- New: `app/services/capture_context.py`, `tests/test_services/test_capture_context.py`.
- Edit: `app/mcp_tools.py` (tool schema + dispatch), `app/api/graph.py`
  (`_run_graph`: load captures + pass to builder + record Capture meta nodes/edges
  after build), `app/agents/graph_builder_agent.py` (`run` kwarg + prompt
  injection only), `app/utils/graph_restructure.py` (`is_meta_node`), and the
  exclusion points in
  `obsidian_writer_agent.py`, `graph_health.py`, `autoresearch.py`,
  `profile_agent.py`, `vault_reconcile.py`.
- Tests: `test_mcp_api.py`, graph builder tests.
