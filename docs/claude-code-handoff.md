# Claude Code Handoff

Last updated: 2026-06-19

This is the compact handoff. The previous file had grown into a long chronological log; detailed history remains in git commits and the superseded diff. Use this document as the current working snapshot for the next ProjectOS session.

## Current Snapshot

- Worktree is intentionally dirty and contains a broad 2026-06-10/11 update set across backend, frontend, MCP docs, and the Obsidian plugin.
- Backend default/public URLs and docs now target port `14006`.
- Runtime check on 2026-06-11 built project `21fc2ce5` from the current inbox with `LLM_TEMPERATURE=1.0`, `LLM_TOP_P=0.95`, `LLM_TOP_K=64`.
- Claude Desktop is expected to reach ProjectOS through the stdio bridge, usually over SSH on macOS.
- Web UI is now the primary simulation review surface.
- Obsidian plugin has been reduced to a thin vault-sync client: list projects, select project, sync generated vault export.
- Graph/simulation quality work is partially implemented from `docs/superpowers/specs/2026-06-10-graph-simulation-quality-assessment.md`.

## Implemented Recently

### Merge Candidate Review UI (2026-06-19)

- Full-stack review surface for `graph.graph["merge_candidates"]`. Users approve a candidate (applies a real `_merge_node` merge) or reject it (persisted so it never re-surfaces).
- Backend:
  - `app/utils/merge_denylist.py` — persists rejected pairs to `projects/{id}/merge_denylist.json` (`load_denylist`/`add_denied_pair`, keyed by `frozenset` of stable `Type:Name` node ids).
  - `collect_merge_candidates(graph, denylist=...)` now skips denied pairs; the build path passes `load_denylist(project_id)`.
  - `POST /api/projects/{id}/graph/merge-candidates/apply` — validates nodes exist (409 if stale), `_merge_node`, re-collects candidates, saves, returns `{merged, merge_candidates}`.
  - `POST /api/projects/{id}/graph/merge-candidates/reject` — records denylist, drops the pair from stored candidates, saves, returns `{rejected, merge_candidates}`.
- Frontend:
  - `src/lib/mergeCandidates.js` — pure `extractMergeCandidates(graphData)` (sorted, safe).
  - `src/components/MergeReviewPanel.vue` — candidate cards with 승인/거부; refetches graph on approve.
  - ProjectDetail "병합 검토" tab with a candidate-count badge.
- Verification (2026-06-19): backend `526 passed`; frontend `11 passed` + clean build.
- Spec: `docs/superpowers/specs/2026-06-19-merge-candidates-review-ui-design.md`; plan: `docs/superpowers/plans/2026-06-19-merge-candidates-review-ui.md`.

### MCP and Claude Desktop

- Added MCP traffic logging:
  - backend HTTP MCP: `logs/mcp.jsonl`
  - stdio bridge: `logs/mcp-stdio.jsonl`
  - project-scoped copies: `logs/projects/<project_id>/mcp.jsonl`
- Added `app/utils/mcp_logging.py`; large payload fields are previewed unless `PROJECTOS_MCP_LOG_FULL_PAYLOADS=true`.
- `projectos_mcp_stdio.py` logs stdio traffic and now defaults to the `14006` backend path through configuration.
- `projectos_get_task` supports server-side waiting with `wait_seconds`, `previous_status`, `previous_progress`, and `min_progress_delta`.
- `tools/list` now exposes a curated 19-tool Claude Desktop surface. Hidden legacy/debug tools remain callable through internal dispatch for compatibility.
- Added compact simulation MCP tools:
  - `projectos_get_simulation_summary`
  - `projectos_get_simulation_graph_delta`
  - `projectos_get_simulation_report_section`
  - `projectos_get_simulation_event_log`
  - `projectos_get_simulation_evidence`
- Updated `docs/claude-desktop-mcp.md` with SSH stdio bridge config, traffic log commands, compact graph/simulation workflow, and recommended Claude Desktop project instructions.

### Context-Aware Clip Ingest

- `projectos_ingest_clip` implements a `needs_context` contract for Obsidian Web Clipper material.
- Incomplete clip context returns questions without saving files or starting tasks.
- Complete context is saved in `projects/{id}/captures.json`, injected into graph extraction prompts, and represented by `Capture` meta nodes.
- `is_meta_node()` now treats `Category` and `Capture` as non-analytical helper nodes.

### Simulation Storage and Compact Read APIs

- Simulation runs now write latest `simulation.json` plus archived `projects/{id}/simulations/{run_id}.json`.
- `app/services/simulation_context.py` provides compact adapters for summary, graph delta, report sections, event log, and evidence resolution.
- Result schema v2 includes input graph snapshot and graph delta item statuses.

### Graph and Simulation Quality Fixes

- Logging: graph extraction failures now include exception type and `exc_info=True`, so empty-message exceptions such as `TimeoutError()` are diagnosable.
- Analytical graph filters: `Category`/`Capture` meta nodes are excluded from simulation context, fallback persona selection, and fallback simulation evidence.
- `ISOLATED_REEXTRACT_ENABLED` config flag can skip the expensive isolated-node re-extraction pass when local LLM timeouts make initial builds impractical.
- Source layering: `app/utils/graph_promotion.py` classifies non-meta nodes into `career`, `publication`, or `knowledge`; career promotion requires direct career/profile/user-owned project evidence.
- Merge review: `app/utils/merge_review.py` records reviewable semantic merge candidates in `graph.graph["merge_candidates"]` without auto-merging. Merged aliases are preserved by `semantic_dedup`.
- Evidence anchoring: `app/utils/evidence_anchor.py` creates node/edge provenance anchors with source file, chunk, page/offset, quote, confidence, method, and directness.
- Simulation lineage: simulation result v2 now records legacy/multi-turn/fallback engine lineage, turn counts, fallback counts, context counts, synthesis model, and synthesis timestamp.
- Simulation evidence: simulation-promoted graph additions now use inferred evidence anchors instead of only plain strings.

### Web Frontend

- Simulation UI is wired into project detail and supports graph overlay modes, workflow/report/persona/debate/delta/evidence review, and graph refresh after simulation.
- `POST /projects/{id}/simulation/evidence` resolves simulation evidence refs through the same backend logic as MCP.
- Evidence UI now shows quote/source/page/directness/confidence, supports weak/strong filtering, and uses shared `EvidenceList.vue`.
- Report and Delta tabs now reuse the same resolved evidence cards instead of plain ref tags.
- Debate tab turns now render their evidence refs inline via the shared `EvidenceList.vue`, and the Debate tab auto-resolves quote/source on entry (matching Report/Delta). (2026-06-19; verified `npx vitest run` 7 passed + `npm run build` clean; browser visual verification not possible — no GTK libs.)
- Added Vitest and `src/frontend/src/lib/simulationViewModel.test.js` for evidence view-model helpers.

### Obsidian Plugin

- Plugin scope is intentionally narrowed:
  - list backend projects
  - select one project
  - sync generated vault export into a local Obsidian folder
- Removed plugin-side collect/runtime/query/analysis/simulation flows from the primary panel.
- Default backend URL is now `http://localhost:14006`.
- README documents SSH tunneling for remote server sync.

## Verification Recorded

- 2026-06-19 clean verification pass on the full uncommitted worktree (before committing the 06-10/06-11 update set):
  - `cd src/backend && python3 -m pytest tests/ -q` → `513 passed, 98 warnings`
  - `cd src/frontend && npx vitest run` → `5 passed`
  - `cd src/frontend && npm run build` → success (chunk-size advisory only)
  - `cd src/obsidian-plugin && npm run build` → success (exit 0, `main.js` regenerated)
  - `.gitignore` gained `src/backend/projects/**/*.npy` so runtime embedding artifacts (`embeddings/*.npy`) are no longer exposed as untracked; `projects/` now has zero non-ignored untracked files.
  - The update set was then committed along directory boundaries (gitignore / backend+docs / frontend / obsidian-plugin / handoff) and pushed.
  - The branch was renamed `hybrid-retrieval` -> `graph-simulation-quality` (local + remote; old remote branch deleted) because the hybrid-retrieval feature itself is already merged to `main` and the name was stale.
- Runtime inbox graph build on project `21fc2ce5`:
  - Ingested 7 real inbox documents; skipped `.DS_Store` and Syncthing metadata.
  - Parse completed with 34 chunks; ontology completed with 9 entity types.
  - First graph task reached isolated re-extraction and repeated `TimeoutError` on `최신 LLM 융합 트렌드 보고서.pdf`.
  - Retried with `ISOLATED_REEXTRACT_ENABLED=false`; completed with 269 nodes and 455 edges.
  - Health summary: isolated `0`, components `1`, duplicate candidates `0`, missing source nodes `0`, duplicate pages `10`.
- Backend full suite after simulation evidence REST/UI backend wiring:
  - `cd src/backend && pytest tests/ -q`
  - Result recorded: `513 passed`
- 2026-06-11 targeted checks after runtime skip flag:
  - `cd src/backend && python3 -m py_compile app/config.py app/api/graph.py`
  - `cd src/backend && python3 -m pytest tests/test_utils/test_isolated_reextract.py -q` → `9 passed`
  - `cd src/backend && python3 -m pytest tests/test_api/test_mcp_api.py::test_mcp_get_task_wait_returns_terminal_task -q` → `1 passed, 2 warnings`
- Frontend:
  - `cd src/frontend && npx vitest run`
  - Result recorded: `5 passed`
  - `cd src/frontend && npm run build`
  - Result recorded: success
- MCP traffic logging:
  - `python3 -m pytest src/backend/tests/test_mcp_stdio.py src/backend/tests/test_api/test_mcp_api.py -q`
  - Result recorded: `49 passed, 44 warnings`
- Compact simulation tools:
  - `python3 -m pytest src/backend/tests/test_services/test_simulation_context.py src/backend/tests/test_api/test_mcp_api.py -q`
  - Result recorded: `52 passed`
  - `python3 -m pytest src/backend/tests/ -q`
  - Earlier result recorded: `472 passed, 93 warnings`
- Browser screenshot verification was not run because the server environment lacks GTK libraries for Playwright/Puppeteer.

## Graph Quality Assessment

- Project `21fc2ce5` is a usable initial inbox map, but not yet a fully curated knowledge graph.
- Structural integrity is good:
  - `269` nodes, `455` links, project status `ready`.
  - self-loop `0`, missing endpoints `0`, exact duplicate links `0`.
  - isolated nodes `0`; component count `1`.
  - evidence/source/chunk coverage is `260/269` nodes; the remaining 9 are `Category` helper nodes.
- Semantic quality still needs cleanup:
  - `Skill` dominates the graph with `137/269` nodes.
  - `USES_SKILL` (`197`) and `INCLUDES` (`175`) account for most links, so category/skill structure is carrying much of the connectivity.
  - `Category` hubs such as `Skills`, `Projects`, and `Publications` make the graph navigable, but can overstate meaningful analytical connectedness.
  - Vault export has 10 duplicate page names, including `SpeakerLM`, `TeachMaster`, `LASEV`, and `ESG-Bench`.
- Runtime caveat:
  - The successful build used `ISOLATED_REEXTRACT_ENABLED=false` after the first graph task stalled on repeated LLM `TimeoutError` during isolated-node re-extraction.
  - Health is clean after the successful retry, but weak/under-connected node improvement from re-extraction was not exercised.

## Known Gaps

- The 06-10/06-11 update set is committed (2026-06-19) along directory boundaries and pushed. The branch was renamed `hybrid-retrieval` -> `graph-simulation-quality`; it contains all of `main` plus the simulation/clip/MCP-quality work and can fast-forward `main`.
- `docs/claude-desktop-mcp.md` and the MCP exposed tool list should be rechecked together before commit, because hidden-vs-exposed tool behavior is intentional.
- Frontend browser behavior is build-tested but not visually verified in this environment. This now includes the new "병합 검토" tab — apply/reject flows are covered by backend tests but the UI itself was not exercised in a browser here.
- Layer labels (`career`/`publication`/`knowledge`) are produced, but downstream ranking and simulation context can still be improved to prefer `career` explicitly.
- The quality assessment's broader Skill subtype cleanup remains open: `Skill` still mixes concrete skills, methods, tools, models, benchmarks, and research topics.
- Initial graph quality is structurally sound but semantically noisy; skill/category hub overuse and duplicate vault pages are the main cleanup targets.
- MCP/Claude Desktop connectivity should be verified with real Claude Desktop traffic by checking that `logs/mcp-stdio.jsonl` and `logs/mcp.jsonl` are created.

## Recommended Next Work

1. Run a clean full verification pass from repo root:
   - `cd src/backend && pytest tests/ -q`
   - `cd src/frontend && npm test && npm run build`
   - `cd src/obsidian-plugin && npm run build`
2. Validate Claude Desktop connection against port `14006` and confirm MCP JSONL logs are created.
3. Visually verify the new "병합 검토" tab in a browser (approve/reject round-trips), and consider an undo UI to clear entries from `merge_denylist.json`.
4. Make simulation/query context prefer `career` layer nodes before `publication`/`knowledge`.
5. Decide whether to introduce `ResearchTopic`/`Method`/`Tool` subtypes or stricter Skill promotion rules.
7. Fix isolated-node re-extraction timeout behavior, then rerun project `21fc2ce5` with `ISOLATED_REEXTRACT_ENABLED=true` for a stricter quality check.

## Files To Inspect First

- `docs/claude-desktop-mcp.md`
- `docs/superpowers/specs/2026-06-10-graph-simulation-quality-assessment.md`
- `src/backend/app/mcp_tools.py`
- `src/backend/app/services/simulation_context.py`
- `src/backend/app/agents/simulation_agent.py`
- `src/backend/app/agents/graph_builder_agent.py`
- `src/backend/app/utils/graph_promotion.py`
- `src/backend/app/utils/merge_review.py`
- `src/backend/app/utils/evidence_anchor.py`
- `src/frontend/src/components/SimulationPanel.vue`
- `src/frontend/src/components/EvidenceList.vue`
- `src/frontend/src/lib/simulationViewModel.js`
- `src/obsidian-plugin/src/App.svelte`
- `src/obsidian-plugin/src/store/appStore.svelte.ts`
