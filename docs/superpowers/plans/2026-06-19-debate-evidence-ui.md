# Debate Turn Evidence UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render each simulation debate turn's evidence refs inline beneath the turn, reusing the shared `EvidenceList.vue`, and auto-resolve quote/source when the user opens the Debate tab — matching the existing Report/Delta behavior.

**Architecture:** Template-only change in `SimulationPanel.vue` plus one extra tab name in the auto-resolve watch. The view-model already populates `turn.evidenceRefs` (`buildDebateRounds`) and folds them into the global `vm.evidenceRefs` (`buildEvidenceRefs`), and `refsToEvidence()` already resolves any ref list. No changes to `simulationViewModel.js`, `EvidenceList.vue`, or the backend. Spec: `docs/superpowers/specs/2026-06-19-debate-evidence-ui-design.md`.

**Tech Stack:** Vue 3 (`<script setup>`), Element Plus, Vitest.

---

### Task 1: Lock the view-model data contract with a test

The template change depends on two guarantees: debate-turn `evidence_refs` surface at `vm.debateRounds[].turns[].evidenceRefs`, and they also appear in the global `vm.evidenceRefs` (so auto-resolve fetches them). This test pins that contract. It should PASS against current code (no view-model change is planned) — it is a regression guard, written first per TDD.

**Files:**
- Modify: `src/frontend/src/lib/simulationViewModel.test.js`

- [ ] **Step 1: Add the import for `buildSimulationViewModel`**

The test file currently imports only three helpers. Replace the import block (lines 2-6) with:

```js
import {
  buildSimulationViewModel,
  indexResolvedEvidence,
  normalizeResolvedEvidence,
  resolveEvidenceRefList,
} from './simulationViewModel.js'
```

- [ ] **Step 2: Append the failing test (new `describe` block at end of file)**

```js
describe('buildSimulationViewModel — debate turn evidence', () => {
  const result = {
    debate: {
      turns: [
        {
          id: 'turn_1',
          round: 1,
          speaker_id: 'p1',
          claim: 'Python is the core skill.',
          proposal: 'Lead with backend work.',
          evidence_refs: ['node:Skill:Python', 'chunk:cv.pdf#c1'],
        },
      ],
    },
    personas: [{ id: 'p1', name: 'Backend Advocate', role: 'engineer' }],
  }

  it('exposes turn evidence refs at vm.debateRounds[].turns[].evidenceRefs', () => {
    const vm = buildSimulationViewModel(result)
    const turn = vm.debateRounds[0].turns[0]
    expect(turn.evidenceRefs).toEqual(['node:Skill:Python', 'chunk:cv.pdf#c1'])
  })

  it('folds turn evidence refs into the global vm.evidenceRefs', () => {
    const vm = buildSimulationViewModel(result)
    const ids = vm.evidenceRefs.map(ref => ref.id)
    expect(ids).toContain('node:Skill:Python')
    expect(ids).toContain('chunk:cv.pdf#c1')
  })
})
```

- [ ] **Step 3: Run the test**

Run: `cd src/frontend && npx vitest run src/lib/simulationViewModel.test.js`
Expected: PASS (the contract already holds). If it FAILS, stop — the design assumption is wrong and the template change must be reconsidered before proceeding.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/src/lib/simulationViewModel.test.js
git commit -m "test(simulation): lock debate-turn evidence view-model contract"
```

---

### Task 2: Render evidence inline in each debate turn + auto-resolve on Debate tab

**Files:**
- Modify: `src/frontend/src/components/SimulationPanel.vue` (turn-item template ~lines 167-169; activeTab watch line 271)

- [ ] **Step 1: Add `EvidenceList` inside the debate turn-item**

In the `turn-item` block, the `unresolvedQuestions` list currently ends the turn (lines 167-169). Add an `EvidenceList` immediately after the closing `</ul>`, mirroring the Delta tab (`:196`). Change:

```vue
                <ul v-if="turn.unresolvedQuestions.length" class="turn-questions">
                  <li v-for="question in turn.unresolvedQuestions" :key="question">{{ question }}</li>
                </ul>
              </div>
```

to:

```vue
                <ul v-if="turn.unresolvedQuestions.length" class="turn-questions">
                  <li v-for="question in turn.unresolvedQuestions" :key="question">{{ question }}</li>
                </ul>
                <EvidenceList v-if="turn.evidenceRefs.length" :items="refsToEvidence(turn.evidenceRefs)" />
              </div>
```

- [ ] **Step 2: Add `'debate'` to the auto-resolve watch**

Line 271 currently reads:

```js
  if (['evidence', 'report', 'delta'].includes(tab) && !resolvedEvidence.value.length && vm.value?.evidenceRefs.length) {
```

Change the array to include `'debate'`:

```js
  if (['evidence', 'report', 'delta', 'debate'].includes(tab) && !resolvedEvidence.value.length && vm.value?.evidenceRefs.length) {
```

- [ ] **Step 3: Verify the full test suite still passes**

Run: `cd src/frontend && npx vitest run`
Expected: PASS (all existing tests + the two from Task 1).

- [ ] **Step 4: Verify the production build succeeds**

Run: `cd src/frontend && npm run build`
Expected: build completes with no errors. (Browser visual verification is NOT possible in this server environment — no GTK libs for Playwright/Puppeteer. State this limitation explicitly rather than claiming visual verification.)

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/components/SimulationPanel.vue
git commit -m "feat(simulation): render debate turn evidence inline"
```

---

### Task 3: Update the handoff doc

**Files:**
- Modify: `docs/claude-code-handoff.md`

- [ ] **Step 1: Record the change**

Add a dated entry (2026-06-19) noting: debate-turn evidence refs now render inline via the shared `EvidenceList.vue` and auto-resolve on Debate tab entry; verification = `npx vitest run` (all pass) + `npm run build` (clean); browser visual verification not possible (no GTK). Remove the now-closed "debate turn evidence refs are not yet rendered" gap note.

- [ ] **Step 2: Commit**

```bash
git add docs/claude-code-handoff.md
git commit -m "docs(handoff): debate turn evidence UI wired"
```

---

## Self-Review

**Spec coverage:**
- Spec §Design item 1 (inline `EvidenceList` per turn) → Task 2 Step 1. ✓
- Spec §Design item 2 (`'debate'` in activeTab watch) → Task 2 Step 2. ✓
- Spec §Testing (TDD data-path test in `simulationViewModel.test.js`) → Task 1. ✓
- Spec §Testing (verify `npx vitest run` + `npm run build`, no browser) → Task 2 Steps 3-4. ✓
- Spec §Non-goals (no view-model/EvidenceList/backend changes) → honored; no task touches those. ✓
- CLAUDE.md rule (update handoff after work) → Task 3. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; all code shown in full. ✓

**Type consistency:** `turn.evidenceRefs` (array of strings), `refsToEvidence(refIds)` → `resolveEvidenceRefList`, global `vm.evidenceRefs` items shaped `{ id, source }` — all match `simulationViewModel.js`. ✓
