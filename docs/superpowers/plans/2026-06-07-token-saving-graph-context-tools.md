# Token-Saving Graph Context Tools Implementation Plan

> Agent note: repo has substantial WIP. Do not revert existing changes and do not touch Simulation, Inbox, or Google for this pass.

**Goal:** Add a read-only graph context service that lets Claude Desktop request compact graph summaries, node neighborhoods, and bounded subgraphs.

**Files:**
- `src/backend/app/services/graph_context.py`
- `src/backend/tests/test_services/test_graph_context.py`
- `src/backend/app/mcp_tools.py`
- `src/backend/tests/test_api/test_mcp_api.py`

**Focused test:**
- `cd /raid/home/a202121010/workspace/projects/ProjectOS/src/backend && python3 -m pytest tests/test_services/test_graph_context.py -q`
- `cd /raid/home/a202121010/workspace/projects/ProjectOS/src/backend && python3 -m pytest tests/test_services/test_graph_context.py tests/test_api/test_mcp_api.py -q`

## Task 1: Service

- [x] Implement `summarize_graph_context`.
- [x] Implement `get_node_context`.
- [x] Implement `get_subgraph_context`.
- [x] Include `read_only`, counts, limits, and match metadata.
- [x] Preserve `source_files`.
- [x] Include directed in/out relation context.
- [x] Keep deterministic ordering and max limits.

## Task 2: Tests

- [x] Cover deterministic summary output.
- [x] Cover no graph mutation.
- [x] Cover node id/name/type matching.
- [x] Cover ambiguous matches.
- [x] Cover missing node payload.
- [x] Cover subgraph depth and max node limits.

## Task 3: Verification

- [x] Run focused service pytest.
- [x] Wire MCP tools `projectos_get_graph_summary`, `projectos_get_node_context`, and `projectos_get_subgraph`.
- [x] Cover MCP tools/list and tool calls.
- [x] Avoid unrelated WIP files.
