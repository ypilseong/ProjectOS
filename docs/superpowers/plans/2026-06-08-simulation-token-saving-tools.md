# Simulation Token-Saving Tools Plan

> Agent note: documentation-only. Backend simulation and MCP files contain active WIP, so do not edit code in this pass.

**Goal:** Design compact read-only MCP/API tools for simulation summary, graph delta, report section, event log, and selected evidence access.

**Files:**
- `docs/superpowers/specs/2026-06-08-simulation-token-saving-tools.md`
- `docs/superpowers/plans/2026-06-08-simulation-token-saving-tools.md`
- `docs/claude-code-handoff.md`

**Verification:**
- `git diff --check -- docs/superpowers/specs/2026-06-08-simulation-token-saving-tools.md docs/superpowers/plans/2026-06-08-simulation-token-saving-tools.md docs/claude-code-handoff.md`

## Task 1: Current Tool Inventory

- [x] Inspect current `projectos_run_simulation` MCP schema.
- [x] Inspect current `projectos_get_simulation` full-payload behavior.
- [x] Align design with schema v2 and UI spec docs.
- [x] Keep this pass docs-only due to active WIP.

## Task 2: Compact Tool Contracts

- [x] Define `projectos_get_simulation_summary`.
- [x] Define `projectos_get_simulation_graph_delta`.
- [x] Define `projectos_get_simulation_report_section`.
- [x] Define `projectos_get_simulation_event_log`.
- [x] Define `projectos_get_simulation_evidence`.
- [x] Define shared parameters, errors, and legacy fallback behavior.

## Task 3: Implementation Guidance

- [x] Define a future `app/services/simulation_context.py` service boundary.
- [x] Define deterministic adapter functions.
- [x] Define service and MCP test strategy.
- [x] Define Claude Desktop default workflow that avoids full payload reads.
- [x] Record non-goals.

## Task 4: Handoff

- [x] Update `docs/claude-code-handoff.md` with completed tool design.
- [x] Set next candidate to simulation schema implementation or compact tool implementation.
