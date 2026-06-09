# Simulation Result Schema Redesign

> Documentation-only schema contract. Do not change Simulation, Inbox, Google, or UI code in this pass because related files contain active WIP.

## Goal

Redefine `simulation.json` so ProjectOS can render simulation progress, persona outputs, debate results, report sections, and graph deltas without sending the entire simulation payload to Claude Desktop by default.

The new result must support:

- UI workflow blocks with clickable step details.
- Compact Claude Desktop review of selected graph deltas or report sections.
- Backward-compatible reads for the current Obsidian plugin simulation panel.
- Failed or partial runs that still preserve completed step outputs.

## Current Shape

The current backend writes a flat legacy result:

```json
{
  "generated_at": "2026-06-08T00:00:00+00:00",
  "query": "user query",
  "personas": [],
  "environment": {},
  "timeline": [],
  "graph_enhancements": { "nodes": [], "edges": [] },
  "cv_improvements": {},
  "report": {},
  "applied_graph_changes": { "nodes_added": 0, "edges_added": 0 }
}
```

This is usable for one report view, but it does not preserve workflow state, event trace, report section boundaries, per-delta evidence, or partial failure details.

## Proposed Top-Level Contract

`simulation.json` should move to a versioned envelope:

```json
{
  "schema_version": "2.0",
  "project_id": "project-id",
  "run_id": "sim_20260608_000000",
  "query": "user query",
  "status": "completed",
  "started_at": "2026-06-08T00:00:00+00:00",
  "completed_at": "2026-06-08T00:01:00+00:00",
  "summary": {
    "title": "ProjectOS Simulation Report",
    "answer": "brief answer",
    "graph_delta_count": 3,
    "report_section_count": 4,
    "low_confidence_count": 1
  },
  "workflow_steps": [],
  "event_log": [],
  "personas": [],
  "environment": {},
  "debate": {},
  "graph_delta": {},
  "report_sections": [],
  "legacy": {}
}
```

`status` values: `running`, `completed`, `failed`, `partial`.

The `legacy` object should keep fields needed by existing clients during migration: `timeline`, `graph_enhancements`, `cv_improvements`, `report`, and `applied_graph_changes`.

## Workflow Steps

`workflow_steps` is the UI navigation model. Each step is small enough to render in a timeline or block strip.

```json
{
  "id": "build_personas",
  "label": "Build Personas",
  "status": "completed",
  "started_at": "2026-06-08T00:00:05+00:00",
  "completed_at": "2026-06-08T00:00:12+00:00",
  "summary": "Built 5 persona agents.",
  "output_refs": {
    "personas": ["persona_1", "persona_2"],
    "events": ["evt_001"]
  },
  "error": null
}
```

Canonical step ids:

- `load_context`
- `build_personas`
- `build_environment`
- `persona_analysis`
- `debate`
- `graph_delta_draft`
- `final_report`
- `apply_graph_changes`
- `update_vault`
- `complete`

## Event Log

`event_log` preserves partial progress and makes streaming/SSE updates align with persisted output.

```json
{
  "event_id": "evt_001",
  "step_id": "build_personas",
  "type": "step_completed",
  "timestamp": "2026-06-08T00:00:12+00:00",
  "summary": "Persona generation completed.",
  "payload_ref": {
    "kind": "personas",
    "ids": ["persona_1", "persona_2"]
  }
}
```

Event `type` values:

- `step_started`
- `step_result`
- `step_completed`
- `step_failed`
- `persona_output`
- `debate_turn`
- `graph_delta_proposed`
- `graph_delta_applied`
- `graph_delta_skipped`
- `report_section_completed`

Events should avoid embedding large prompt/completion bodies. Store references and short summaries in the event log; keep detailed text in report sections or evidence fields.

## Personas

Personas remain visible to users, but need stable ids and structured review fields.

```json
{
  "id": "persona_1",
  "name": "Applicant Profile Reviewer",
  "role": "Person perspective",
  "stance": "evidence-first career narrative review",
  "assumptions": ["Only use graph or source-backed facts."],
  "focus_areas": ["project impact", "skills evidence"],
  "goals": ["Find missing strengths."],
  "knowledge": ["Graph node Person:..."],
  "source_node_ids": ["Person:..."],
  "key_points": ["The CV needs stronger outcome metrics."]
}
```

Migration from current `PersonaAgentSpec`:

- `agent_id` maps to `id`.
- `source_nodes` maps to `source_node_ids`.
- `communication_style` maps to `stance` when no explicit stance exists.

## Environment

The environment should describe why the simulation judged outputs the way it did.

```json
{
  "objective": "Strengthen the graph and answer the query.",
  "rules": ["Use source-backed evidence."],
  "constraints": ["Do not invent facts."],
  "evaluation_criteria": ["evidence quality", "graph usefulness"],
  "risks": ["weak source coverage"],
  "rounds": 3,
  "success_criteria": ["actionable graph deltas"]
}
```

## Debate

The old `timeline` should become structured debate output.

```json
{
  "turns": [
    {
      "turn_id": "turn_001",
      "round": 1,
      "speaker_id": "persona_1",
      "stance": "support",
      "claim": "The project impact is under-specified.",
      "evidence_refs": ["chunk:cv.pdf#c1", "node:Project:..."],
      "proposal": "Add outcome metrics to the project description.",
      "unresolved_questions": []
    }
  ],
  "agreements": ["Evidence-backed claims should be preferred."],
  "disagreements": [],
  "unresolved_questions": []
}
```

Legacy `timeline` can be reconstructed from `turns` using `round`, `speaker_id`, `claim`, and `proposal`.

## Graph Delta

Graph changes should be represented as proposed deltas before application. This lets Claude Desktop review only selected deltas.

```json
{
  "summary": {
    "proposed_nodes": 1,
    "proposed_edges": 2,
    "applied_nodes": 1,
    "applied_edges": 1,
    "skipped": 1
  },
  "nodes": [
    {
      "delta_id": "delta_node_001",
      "operation": "add",
      "node_id": "Skill:Example",
      "type": "Skill",
      "name": "Example",
      "description": "Source-backed description.",
      "confidence": 0.72,
      "evidence_refs": ["chunk:cv.pdf#c1"],
      "source_event_ids": ["evt_010"],
      "source_report_section_ids": ["section_graph"],
      "status": "applied"
    }
  ],
  "edges": [
    {
      "delta_id": "delta_edge_001",
      "operation": "add",
      "source": { "type": "Person", "name": "User", "node_id": "Person:User" },
      "target": { "type": "Skill", "name": "Example", "node_id": "Skill:Example" },
      "relation": "USES_SKILL",
      "confidence": 0.7,
      "evidence_refs": ["chunk:cv.pdf#c1"],
      "source_event_ids": ["evt_011"],
      "source_report_section_ids": ["section_graph"],
      "status": "skipped",
      "status_reason": "Target node was not found."
    }
  ]
}
```

`operation` values: `add`, `update`, `delete`.

`status` values: `proposed`, `applied`, `skipped`, `rejected`.

For current behavior, legacy `graph_enhancements.nodes` and `graph_enhancements.edges` should map to proposed node and edge deltas. `applied_graph_changes` should be computed from delta statuses, not stored as the only change detail.

## Report Sections

The final report should be divided into addressable sections for compact MCP access and UI tabs.

```json
{
  "section_id": "section_summary",
  "title": "Executive Summary",
  "kind": "executive_summary",
  "summary": "Brief section summary.",
  "body": "Rendered report text.",
  "evidence_refs": ["chunk:cv.pdf#c1"],
  "uncertainty": ["Outcome metrics are not fully sourced."],
  "related_delta_ids": ["delta_node_001"],
  "source_persona_ids": ["persona_1"]
}
```

Suggested `kind` values:

- `executive_summary`
- `persona_findings`
- `debate_summary`
- `graph_delta`
- `cv_improvements`
- `recommendations`
- `uncertainties`

Legacy `report.answer` should map to an `executive_summary` section. Legacy `report.recommendations` should map to `recommendations`. Legacy `cv_improvements` should map to `cv_improvements`.

## Evidence References

Use compact, typed references:

- `chunk:<source_file>#<chunk_id>`
- `node:<node_id>`
- `edge:<source_id>-><target_id>:<relation>`
- `event:<event_id>`
- `report:<section_id>`

Do not store full source chunk text in every reference. A future selected-evidence tool can resolve refs only when requested.

## Compact Views For Claude Desktop

The schema should enable future token-saving tools:

- `projectos_get_simulation_summary(project_id, run_id=None)`
- `projectos_get_simulation_graph_delta(project_id, run_id=None, status=None, max_items=20)`
- `projectos_get_simulation_report_section(project_id, section_id, run_id=None)`
- `projectos_get_simulation_event_log(project_id, run_id=None, step_id=None, max_events=50)`

These tools should return short text plus structured payloads. They should not return `legacy`, full debate turns, or all report bodies unless explicitly requested.

## UI Rendering Contract

The Obsidian simulation section should eventually render:

- Workflow blocks from `workflow_steps`.
- Agent cards from `personas`.
- Debate timeline from `debate.turns`.
- Report tabs from `report_sections`.
- Graph changes from `graph_delta.nodes` and `graph_delta.edges`.

During migration, UI can continue reading legacy fields while backend writes both schema v2 fields and `legacy`.

## Migration Plan

1. Add a pure normalization function that converts the current raw LLM result into schema v2.
2. Keep top-level legacy fields or `legacy` during the first compatibility window.
3. Update tests to assert `schema_version`, workflow steps, event log, report sections, and graph delta status.
4. Add compact MCP read tools after the schema is stable.
5. Move Obsidian UI reads from legacy fields to schema v2 fields.
6. Remove direct full-payload Claude Desktop usage from documentation after compact tools exist.

## Non-Goals

- No simulation code changes in this documentation pass.
- No new MCP tools in this pass.
- No UI implementation in this pass.
- No graph patch application behavior change.
- No LLM prompt rewrite beyond future implementation guidance.
