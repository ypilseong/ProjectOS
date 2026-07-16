# Claude Desktop MCP Instructions Plan

> Repo has substantial WIP. Keep this documentation-only and do not revert existing changes.

**Goal:** Reflect token-saving graph context tools in the Claude Desktop MCP instructions.

**Files:**
- `docs/claude-desktop-mcp.md`
- `docs/superpowers/specs/2026-06-07-claude-desktop-mcp-instructions.md`
- `docs/superpowers/plans/2026-06-07-claude-desktop-mcp-instructions.md`

## Task 1: Review Existing Instructions

- [x] Read current Claude Desktop MCP setup documentation.
- [x] Read token-saving graph context tool design and plan.
- [x] Confirm this pass is documentation-only.

## Task 2: Update Claude Desktop MCP Guidance

- [x] Add `projectos_get_graph_summary`, `projectos_get_node_context`, and `projectos_get_subgraph` to exposed tools.
- [x] Document graph-ready workflow as `projectos_get_graph_summary` first, then targeted node or subgraph context.
- [x] Restrict `projectos_get_graph` to explicit full graph needs such as export, debugging, or patch preparation.
- [x] Document that `projectos_get_simulation` should be used only for short confirmation or explicit user-requested inspection until delta/report-section tools exist.

## Task 3: Verification

- [x] Inspect docs diff.
- [x] Confirm no backend, Inbox, Google, or Simulation code was edited in this pass.
