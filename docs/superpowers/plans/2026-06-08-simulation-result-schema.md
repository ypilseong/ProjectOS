# Simulation Result Schema Redesign Plan

> Agent note: this pass is documentation-only. Simulation backend/API/UI files contain active WIP, so avoid editing them unless the user explicitly requests implementation.

**Goal:** Define a versioned `simulation.json` schema that supports workflow rendering, event logs, graph delta review, report-section access, and legacy migration.

**Files:**
- `docs/superpowers/specs/2026-06-08-simulation-result-schema.md`
- `docs/superpowers/plans/2026-06-08-simulation-result-schema.md`
- `docs/claude-code-handoff.md`

**Verification:**
- `git diff --check -- docs/superpowers/specs/2026-06-08-simulation-result-schema.md docs/superpowers/plans/2026-06-08-simulation-result-schema.md docs/claude-code-handoff.md`

## Task 1: Current State

- [x] Inspect current `ProjectSimulationAgent` result shape.
- [x] Inspect `/projects/{project_id}/simulation` read/write behavior.
- [x] Inspect current Obsidian `SimulationResult` TypeScript contract.
- [x] Confirm related code files have WIP and keep this task docs-only.

## Task 2: Schema Contract

- [x] Define a versioned top-level envelope.
- [x] Define `workflow_steps` for UI block rendering.
- [x] Define `event_log` for streaming and partial failure persistence.
- [x] Define structured `personas`, `environment`, and `debate`.
- [x] Define `graph_delta` with per-node/per-edge status and evidence refs.
- [x] Define addressable `report_sections`.
- [x] Define compact evidence reference conventions.

## Task 3: Migration Guidance

- [x] Map current legacy fields to schema v2 fields.
- [x] Preserve current UI compatibility through legacy fields.
- [x] Document future compact MCP tools that should consume the schema.
- [x] Record non-goals for this pass.

## Task 4: Handoff

- [x] Update `docs/claude-code-handoff.md` with the completed schema redesign.
- [x] Set the next candidate to simulation UI spec or simulation token-saving tools.
