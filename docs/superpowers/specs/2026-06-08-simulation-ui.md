# Simulation UI Spec

> Documentation-only UI contract. Do not modify Obsidian plugin or backend code in this pass because simulation files contain active WIP.

## Goal

Redesign the Obsidian plugin simulation panel around the schema v2 result contract so users can inspect a simulation as a workflow, not just as a flat report.

The UI must make these questions easy to answer:

- What step is running, completed, failed, or waiting?
- Which persona produced which claim or proposal?
- What changed in the graph, with what confidence and evidence?
- Which report section answers the user query, and which parts are uncertain?
- What can Claude Desktop review without loading the full simulation payload?

## Current UI

`src/obsidian-plugin/src/sections/SimulationSection.svelte` currently renders:

- Query textarea.
- `Run simulation` and `Load result` buttons.
- Live progress text from `store.simulationLive`.
- Tabs: `Report`, `Agents`, `Timeline`, `CV`.
- Legacy data fields:
  - `report.title`, `report.answer`, `report.recommendations`
  - `personas`
  - `timeline`
  - `cv_improvements`
  - `applied_graph_changes`

This is a useful compatibility baseline, but it has no workflow block view, no event log inspection, no graph delta list, no report section navigation, and no selected evidence review path.

## Target Information Architecture

The first screen inside the Simulation section should remain the usable tool, not a landing page.

Recommended layout:

1. Query / action row.
2. Live run status and workflow strip.
3. Compact result summary.
4. Primary tabs:
   - `Report`
   - `Workflow`
   - `Agents`
   - `Debate`
   - `Graph Delta`
   - `Evidence`

`CV` should become a report section kind (`cv_improvements`) instead of a separate hard-coded legacy tab. During migration, keep the old `CV` tab only when the payload has legacy `cv_improvements` but no schema v2 `report_sections`.

## Data Contract

The UI should prefer schema v2 fields:

```ts
interface SimulationResultV2 {
  schema_version: "2.0";
  project_id?: string;
  run_id?: string;
  query?: string;
  status?: "running" | "completed" | "failed" | "partial";
  started_at?: string;
  completed_at?: string;
  summary?: SimulationSummary;
  workflow_steps?: SimulationWorkflowStep[];
  event_log?: SimulationEvent[];
  personas?: SimulationPersona[];
  environment?: SimulationEnvironment;
  debate?: SimulationDebate;
  graph_delta?: SimulationGraphDelta;
  report_sections?: SimulationReportSection[];
  legacy?: LegacySimulationResult;
}
```

Fallback behavior:

- If `schema_version !== "2.0"`, adapt the legacy result into a view model.
- If `report_sections` is empty, synthesize sections from legacy `report` and `cv_improvements`.
- If `debate.turns` is empty, synthesize debate turns from legacy `timeline`.
- If `graph_delta` is empty, show `applied_graph_changes` as a compact summary and mark details unavailable.

## View Model

Implement a small pure adapter before changing markup:

```ts
type SimulationViewModel = {
  isV2: boolean;
  title: string;
  status: string;
  query: string;
  summaryText: string;
  workflowSteps: WorkflowStepView[];
  reportSections: ReportSectionView[];
  personas: PersonaView[];
  debateRounds: DebateRoundView[];
  graphDeltaItems: GraphDeltaItemView[];
  evidenceRefs: EvidenceRefView[];
  legacyWarnings: string[];
};
```

This keeps Svelte components thin and protects the UI from backend migration churn.

## Query And Actions

Top controls:

- Query textarea with the current placeholder retained.
- Primary button: `Run simulation`.
- Secondary button: `Load result`.
- Optional toggle: `Apply graph changes` once backend supports explicit user control in the plugin UI.
- Optional toggle: `Update vault` once backend exposes it in the plugin UI.

The action row must fit narrow Obsidian side panes. Buttons can wrap to the next line, but text must not overflow.

## Workflow Strip

Render `workflow_steps` as a horizontal wrapping strip or vertical compact list depending on available width.

Each block shows:

- Step label.
- Status icon or color.
- Short summary.
- Duration when available.

Status mapping:

- `completed`: accent border, subdued success fill.
- `running`: animated accent indicator.
- `failed`: error color and error detail.
- `partial`: warning color.
- missing/waiting: muted.

Clicking a step opens the detail panel for that step:

- Step summary.
- Related events from `event_log`.
- Related personas, report sections, and graph deltas from `output_refs`.
- Error message if present.

The UI should preserve partial runs. A failed run still shows every completed step and its outputs.

## Report Tab

Render `report_sections` as section navigation plus detail.

Recommended behavior:

- First section defaults to `executive_summary`.
- Section list shows title, kind, short summary, and uncertainty count.
- Detail view shows body, evidence refs, related delta ids, and source persona ids.
- `recommendations` and `cv_improvements` kinds should be rendered as readable lists when body content is list-like.

Avoid showing the full raw JSON in the primary report UI.

## Workflow Tab

The `Workflow` tab expands on the workflow strip:

- Full step list.
- Event log filtered by selected step.
- Event type badges.
- Payload reference links.

Event log rows should be compact. Long payload text should not be embedded in the row; link to report section, graph delta, persona, or evidence view instead.

## Agents Tab

Render `personas` as compact repeated items:

- Name and role.
- Stance.
- Focus areas.
- Key points.
- Source node ids.

Clicking a persona filters:

- Debate turns by `speaker_id`.
- Report sections by `source_persona_ids`.
- Graph deltas by `source_event_ids` or related section ids when available.

During migration, legacy personas should still render with `agent_id`, `goals`, and `knowledge`.

## Debate Tab

Render `debate.turns` grouped by `round`.

Each turn shows:

- Persona name.
- Stance.
- Claim.
- Proposal.
- Evidence refs.
- Unresolved questions.

Use the current round grouping as the visual baseline, but replace `observation/proposal` with the richer v2 fields.

The tab should also show:

- Agreements.
- Disagreements.
- Unresolved questions.

## Graph Delta Tab

Graph delta is the most important review surface for Claude Desktop handoff.

Render combined node and edge deltas with:

- Operation (`add`, `update`, `delete`).
- Target node or edge label.
- Relation for edges.
- Confidence.
- Status (`proposed`, `applied`, `skipped`, `rejected`).
- Status reason.
- Evidence refs.
- Related report section ids.

Controls:

- Segmented filter by status: `All`, `Proposed`, `Applied`, `Skipped`, `Rejected`.
- Segmented filter by item type: `All`, `Nodes`, `Edges`.
- Sort by confidence ascending/descending.

Low-confidence or skipped deltas should be easy to scan. They are the likely candidates for Claude Desktop review.

## Evidence Tab

The evidence tab should list evidence refs gathered from:

- Report sections.
- Debate turns.
- Graph deltas.
- Persona source nodes.

For now, evidence refs are unresolved compact labels. Once selected-evidence MCP/API tools exist, clicking a ref can load a short source excerpt.

The UI should never inline all source chunks into the simulation panel by default.

## Graph Visualization Integration

Longer term, graph visualization should support simulation context:

- `full graph`
- `simulation delta only`
- `before/after diff`

The Simulation panel does not need to own the full graph canvas in the first implementation. It can publish selected `delta_id`, `node_id`, or edge identifiers to a shared graph view when that integration exists.

Minimum first-pass graph UI:

- A compact graph delta list in the Simulation panel.
- Clear labels for nodes and edges.
- Evidence and confidence visible before applying or reviewing a change.

## Empty And Error States

Empty states should be operational, not explanatory marketing copy:

- No result loaded: show query/actions only.
- No report sections: show `No report sections.` and legacy report fallback if available.
- No graph deltas: show `No graph deltas proposed.`
- Failed run: show failed workflow step, error, and any completed outputs.
- Legacy payload: show a small compatibility note only in details, not as a prominent warning.

## Responsive Constraints

The Obsidian side panel can be narrow. The UI must:

- Avoid nested cards.
- Let tabs and workflow blocks wrap.
- Keep buttons and badges from resizing the layout on hover.
- Use stable dimensions for status indicators and icon buttons.
- Wrap long node ids, source refs, and file names with `overflow-wrap: anywhere`.
- Avoid hero-sized type and large decorative panels.

## Styling Direction

Use the existing Obsidian plugin visual system:

- Obsidian CSS variables for colors.
- Existing `Tabs`, `Button`, and section styles where possible.
- Tight repeated items with 6-8px border radius.
- Restrained status colors, not a single-hue palette.
- No decorative background graphics.

Suggested new CSS families:

- `.pos-workflow-strip`
- `.pos-workflow-step`
- `.pos-report-section`
- `.pos-delta-list`
- `.pos-delta-item`
- `.pos-evidence-ref`

## Implementation Sequence

1. Add TypeScript interfaces for schema v2 and legacy result.
2. Add a pure `simulationViewModel` adapter with legacy fallback.
3. Add focused tests for the adapter if the plugin test setup can run TS pure modules.
4. Update `SimulationSection.svelte` to read the view model.
5. Add workflow strip and report section rendering.
6. Add graph delta and evidence tabs.
7. Preserve legacy `Report / Agents / Timeline / CV` behavior through the adapter.
8. Build the Obsidian plugin.
9. Verify in Obsidian manually because server-side screenshot validation is not available for the plugin.

## Non-Goals

- No backend schema implementation in this UI spec.
- No MCP token-saving tool implementation.
- No full graph canvas implementation in the first UI pass.
- No automatic graph delta approval workflow.
- No removal of legacy simulation rendering until backend writes schema v2 consistently.
