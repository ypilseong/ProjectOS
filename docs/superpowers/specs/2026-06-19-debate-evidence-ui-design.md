# Debate Turn Evidence UI — Design

Date: 2026-06-19
Status: Approved (implementation not yet started)
Scope: ProjectOS web frontend (`src/frontend`)

## Problem

The simulation review UI resolves evidence refs and renders them through the
shared `EvidenceList.vue` in the **Report** tab (`SimulationPanel.vue:140`) and
the **Graph Delta** tab (`SimulationPanel.vue:196`). The **Debate** tab does
**not** render any evidence for its turns — each `turn-item`
(`SimulationPanel.vue:160-170`) shows only `claim`, `proposal`, and
`unresolvedQuestions`.

This is the known gap recorded in the handoff: "Simulation debate turn evidence
refs are not yet rendered through the shared evidence panel."

The data already exists end to end:
- `buildDebateRounds` populates `turn.evidenceRefs` for each turn
  (`simulationViewModel.js:323`).
- `buildEvidenceRefs` already folds debate-turn refs into the global
  `vm.evidenceRefs` (`simulationViewModel.js:442`), so the existing
  "증거 해석" call already resolves debate refs — they just surface only in the
  Evidence tab, never inline in the Debate tab.

## Goal

Render each debate turn's evidence inline, beneath the turn, reusing the shared
`EvidenceList.vue` exactly as Report/Delta do. Auto-resolve quote/source when
the user opens the Debate tab so the experience matches Report/Delta.

## Approach (chosen: A)

**A — Template + watch only (chosen).** Add `EvidenceList` to the Debate tab and
add `'debate'` to the auto-resolve watch. No view-model changes: `turn.evidenceRefs`
and `refsToEvidence()` already exist. Mirrors the validated Report/Delta pattern,
minimizing regression risk.

**B — view-model debate-specific resolved-evidence helper (rejected).** Introduce
a new helper that pre-groups resolved evidence per turn. More "structural" but
adds a path Report/Delta do not use — unnecessary abstraction (YAGNI).

## Design (single file: `src/frontend/src/components/SimulationPanel.vue`)

1. **Debate turn rendering.** Inside each `turn-item` (after the
   `unresolvedQuestions` list, `SimulationPanel.vue:167-169`), add:
   ```vue
   <EvidenceList v-if="turn.evidenceRefs.length" :items="refsToEvidence(turn.evidenceRefs)" />
   ```
   Identical to Report (`:140`) and Delta (`:196`). When unresolved, `refsToEvidence`
   yields ref-id cards; after resolution it yields quote/source/directness/confidence
   cards via the shared `resolvedIndex`.

2. **Auto-resolve on tab entry.** Extend the `activeTab` watcher
   (`SimulationPanel.vue:271`) to include `'debate'`:
   ```js
   if (['evidence', 'report', 'delta', 'debate'].includes(tab) && !resolvedEvidence.value.length && vm.value?.evidenceRefs.length) {
   ```

No changes to `simulationViewModel.js` or `EvidenceList.vue`.

## Testing

Template wiring cannot be unit-tested in the current setup (view-model unit tests
only; no component-test harness). TDD guards the **data path** instead — add to
`src/frontend/src/lib/simulationViewModel.test.js`:

- Given a v2 result with a debate turn carrying `evidence_refs`, assert
  `buildSimulationViewModel(result)`:
  - exposes those refs at `vm.debateRounds[].turns[].evidenceRefs`, and
  - includes them in the global `vm.evidenceRefs`.

Write the test first (it should pass against current view-model code, locking the
contract the template depends on), then make the template change.

Verification: `npx vitest run` + `npm run build`. Browser visual verification is
**not possible** in this server environment (no GTK libs for Playwright/Puppeteer);
that limitation will be stated explicitly rather than claimed as verified.

## Non-goals (YAGNI)

- No new view-model helpers or resolved-evidence grouping.
- No changes to `EvidenceList.vue` markup/styles.
- No backend changes (debate `evidence_refs` already flow through the existing
  `resolveSimulationEvidence` endpoint).
- No round-level evidence aggregation (evidence stays per turn).
