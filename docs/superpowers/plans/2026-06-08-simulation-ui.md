# Simulation UI Spec Plan

> Agent note: documentation-only. Do not edit `SimulationSection.svelte`, plugin types, backend simulation code, or styles in this pass because related files contain active WIP.

**Goal:** Define how the Obsidian plugin should render schema v2 simulation results with workflow blocks, report sections, debate turns, graph deltas, and evidence refs while preserving legacy payload compatibility.

**Files:**
- `docs/superpowers/specs/2026-06-08-simulation-ui.md`
- `docs/superpowers/plans/2026-06-08-simulation-ui.md`
- `docs/claude-code-handoff.md`

**Verification:**
- `git diff --check -- docs/superpowers/specs/2026-06-08-simulation-ui.md docs/superpowers/plans/2026-06-08-simulation-ui.md docs/claude-code-handoff.md`

## Task 1: Current UI Inventory

- [x] Inspect current `SimulationSection.svelte`.
- [x] Inspect current `SimulationResult` TypeScript interface.
- [x] Inspect current simulation CSS classes.
- [x] Confirm code files are WIP and keep this pass docs-only.

## Task 2: UI Contract

- [x] Define target information architecture.
- [x] Define schema v2 preferred fields and legacy fallback behavior.
- [x] Define a pure view-model adapter target.
- [x] Define workflow strip behavior.
- [x] Define report, workflow, agents, debate, graph delta, and evidence tabs.
- [x] Define empty/error states.
- [x] Define responsive and styling constraints for the Obsidian side panel.

## Task 3: Implementation Guidance

- [x] Specify the implementation sequence for future code work.
- [x] Preserve current legacy rendering through the adapter.
- [x] Record non-goals.

## Task 4: Handoff

- [x] Update `docs/claude-code-handoff.md` with the completed UI spec.
- [x] Set the next candidate to simulation token-saving tools or schema implementation.
