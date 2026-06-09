# Simulation Token-Saving Tools Design

> Documentation-only MCP/API design. Do not change backend simulation code or MCP wiring in this pass because related files contain active WIP.

## Goal

Avoid sending full `simulation.json` to Claude Desktop by default. Provide compact, read-only tools that expose only the simulation slice needed for review:

- run summary
- graph deltas
- selected report section
- filtered event log
- selected evidence references

This design follows the schema v2 contract in `2026-06-08-simulation-result-schema.md` and the UI contract in `2026-06-08-simulation-ui.md`.

## Current Problem

`projectos_get_simulation(project_id)` currently reads `simulation.json` and returns the entire object as both text and structured content.

That is acceptable for explicit export/debug, but it is inefficient for normal Claude Desktop review because simulation payloads can include personas, timelines, reports, graph changes, and future event logs in one response.

## Tool Set

Keep `projectos_get_simulation` for explicit full export/debug, but make the default documented workflow use compact read-only tools.

Recommended MCP tools:

- `projectos_get_simulation_summary`
- `projectos_get_simulation_graph_delta`
- `projectos_get_simulation_report_section`
- `projectos_get_simulation_event_log`
- `projectos_get_simulation_evidence`

All tools are read-only and require an existing project plus `simulation.json`.

## Shared Parameters

All tools should accept:

```json
{
  "project_id": "project-id",
  "run_id": null
}
```

`run_id` is optional for the current single-file implementation. If omitted, tools read the latest `simulation.json`. Future multi-run storage can use `run_id` to select a specific run without changing the tool contract.

Error behavior:

- Missing project: same behavior as other MCP tools.
- Missing simulation file: `Simulation not run yet`.
- Unknown `run_id`: `Simulation run not found`.
- Legacy payload: return best-effort adapted compact views and include `schema_version: "legacy"` in structured content.

## `projectos_get_simulation_summary`

Purpose: session-safe overview after a simulation completes.

Parameters:

```json
{
  "project_id": "project-id",
  "run_id": null,
  "include_workflow": true,
  "max_steps": 12
}
```

Structured payload:

```json
{
  "kind": "simulation_summary",
  "read_only": true,
  "project_id": "project-id",
  "run_id": "sim_20260608_000000",
  "schema_version": "2.0",
  "status": "completed",
  "query": "user query",
  "started_at": "2026-06-08T00:00:00+00:00",
  "completed_at": "2026-06-08T00:01:00+00:00",
  "summary": {
    "title": "ProjectOS Simulation Report",
    "answer": "brief answer",
    "graph_delta_count": 3,
    "report_section_count": 4,
    "low_confidence_count": 1
  },
  "workflow_steps": [
    {
      "id": "build_personas",
      "label": "Build Personas",
      "status": "completed",
      "summary": "Built 5 persona agents."
    }
  ],
  "counts": {
    "personas": 5,
    "debate_turns": 9,
    "report_sections": 4,
    "graph_delta_nodes": 1,
    "graph_delta_edges": 2,
    "events": 20
  },
  "available_views": [
    "graph_delta",
    "report_sections",
    "event_log",
    "evidence"
  ]
}
```

Text response should be short: title, status, count summary, and next suggested compact tools.

Legacy adaptation:

- `summary.title` from `report.title`.
- `summary.answer` from `report.answer`.
- counts from legacy arrays.
- `workflow_steps` omitted or synthesized as `legacy_result_loaded`.

## `projectos_get_simulation_graph_delta`

Purpose: inspect graph changes without loading personas, debate, or report bodies.

Parameters:

```json
{
  "project_id": "project-id",
  "run_id": null,
  "status": null,
  "item_type": "all",
  "max_items": 20,
  "sort": "confidence_asc"
}
```

Allowed values:

- `status`: `proposed`, `applied`, `skipped`, `rejected`, or `null`.
- `item_type`: `all`, `nodes`, `edges`.
- `sort`: `confidence_asc`, `confidence_desc`, `status`, `operation`.

Structured payload:

```json
{
  "kind": "simulation_graph_delta",
  "read_only": true,
  "project_id": "project-id",
  "run_id": "sim_20260608_000000",
  "schema_version": "2.0",
  "filters": {
    "status": "skipped",
    "item_type": "all",
    "max_items": 20,
    "sort": "confidence_asc"
  },
  "summary": {
    "total": 3,
    "returned": 1,
    "proposed": 0,
    "applied": 0,
    "skipped": 1,
    "rejected": 0,
    "low_confidence": 1
  },
  "items": [
    {
      "delta_id": "delta_edge_001",
      "item_type": "edge",
      "operation": "add",
      "label": "User -USES_SKILL-> Example",
      "source": { "type": "Person", "name": "User", "node_id": "Person:User" },
      "target": { "type": "Skill", "name": "Example", "node_id": "Skill:Example" },
      "relation": "USES_SKILL",
      "confidence": 0.7,
      "status": "skipped",
      "status_reason": "Target node was not found.",
      "evidence_refs": ["chunk:cv.pdf#c1"],
      "source_event_ids": ["evt_011"],
      "source_report_section_ids": ["section_graph"]
    }
  ],
  "truncated": false
}
```

Text response should list only returned item labels and statuses.

Legacy adaptation:

- `graph_enhancements.nodes` become `item_type=node`, `operation=add`, `status=proposed`.
- `graph_enhancements.edges` become `item_type=edge`, `operation=add`, `status=proposed`.
- `applied_graph_changes` is included in summary, but does not provide item-level status.

## `projectos_get_simulation_report_section`

Purpose: inspect one report section body instead of the full report.

Parameters:

```json
{
  "project_id": "project-id",
  "run_id": null,
  "section_id": null,
  "kind": "executive_summary",
  "include_body": true
}
```

Selection rules:

1. If `section_id` is provided, select exact section id.
2. Else if `kind` is provided, select the first section of that kind.
3. Else select `executive_summary`.

Structured payload:

```json
{
  "kind": "simulation_report_section",
  "read_only": true,
  "project_id": "project-id",
  "run_id": "sim_20260608_000000",
  "schema_version": "2.0",
  "selected": {
    "section_id": "section_summary",
    "title": "Executive Summary",
    "kind": "executive_summary",
    "summary": "Brief section summary.",
    "body": "Rendered report text.",
    "evidence_refs": ["chunk:cv.pdf#c1"],
    "uncertainty": ["Outcome metrics are not fully sourced."],
    "related_delta_ids": ["delta_node_001"],
    "source_persona_ids": ["persona_1"]
  },
  "available_sections": [
    {
      "section_id": "section_summary",
      "title": "Executive Summary",
      "kind": "executive_summary",
      "summary": "Brief section summary."
    }
  ]
}
```

`include_body=false` should omit `body` and return only metadata plus summaries.

Legacy adaptation:

- `report.answer` maps to `section_id=legacy_report_answer`, `kind=executive_summary`.
- `report.recommendations` maps to `section_id=legacy_recommendations`, `kind=recommendations`.
- `cv_improvements` maps to `section_id=legacy_cv_improvements`, `kind=cv_improvements`.

## `projectos_get_simulation_event_log`

Purpose: inspect workflow trace without loading all outputs.

Parameters:

```json
{
  "project_id": "project-id",
  "run_id": null,
  "step_id": null,
  "event_type": null,
  "max_events": 50
}
```

Structured payload:

```json
{
  "kind": "simulation_event_log",
  "read_only": true,
  "project_id": "project-id",
  "run_id": "sim_20260608_000000",
  "schema_version": "2.0",
  "filters": {
    "step_id": "debate",
    "event_type": null,
    "max_events": 50
  },
  "events": [
    {
      "event_id": "evt_001",
      "step_id": "debate",
      "type": "debate_turn",
      "timestamp": "2026-06-08T00:00:30+00:00",
      "summary": "Persona 1 proposed adding outcome metrics.",
      "payload_ref": {
        "kind": "debate_turns",
        "ids": ["turn_001"]
      }
    }
  ],
  "truncated": false
}
```

Legacy adaptation:

- If no `event_log`, synthesize events from legacy `timeline` with type `debate_turn`.
- Use deterministic event ids like `legacy_turn_001`.

## `projectos_get_simulation_evidence`

Purpose: resolve selected compact evidence refs without dumping all chunks.

Parameters:

```json
{
  "project_id": "project-id",
  "run_id": null,
  "evidence_refs": ["chunk:cv.pdf#c1"],
  "max_chars_per_ref": 1200
}
```

Structured payload:

```json
{
  "kind": "simulation_evidence",
  "read_only": true,
  "project_id": "project-id",
  "run_id": "sim_20260608_000000",
  "refs": [
    {
      "ref": "chunk:cv.pdf#c1",
      "resolved": true,
      "kind": "chunk",
      "source_file": "cv.pdf",
      "chunk_id": "c1",
      "text": "short excerpt",
      "truncated": false
    }
  ],
  "unresolved_refs": []
}
```

Resolution rules:

- `chunk:<source_file>#<chunk_id>` reads from `chunks.json`.
- `node:<node_id>` reads from `graph.json` and returns compact node metadata.
- `edge:<source_id>-><target_id>:<relation>` reads from `graph.json` and returns compact edge metadata.
- `event:<event_id>` reads from simulation `event_log`.
- `report:<section_id>` reads from `report_sections`.

This tool can be implemented after the schema/delta/report-section tools. It has slightly broader file dependencies than the other compact tools.

## Service Layer

Before MCP wiring, implement a pure service module:

`app/services/simulation_context.py`

Suggested functions:

- `load_simulation_result(project_id, run_id=None)`
- `adapt_simulation_summary(simulation, project_id=None)`
- `adapt_simulation_graph_delta(simulation, status=None, item_type="all", max_items=20, sort="confidence_asc")`
- `adapt_simulation_report_section(simulation, section_id=None, kind="executive_summary", include_body=True)`
- `adapt_simulation_event_log(simulation, step_id=None, event_type=None, max_events=50)`
- `resolve_simulation_evidence(project_id, simulation, evidence_refs, max_chars_per_ref=1200)`

Keep adapter functions deterministic and side-effect free. File I/O should stay in loader/resolver boundaries.

## Testing Strategy

Service tests:

- v2 summary returns counts and limited workflow.
- legacy summary fallback.
- graph delta filters by status and item type.
- graph delta sorting is deterministic.
- report section selection by `section_id` and `kind`.
- report section `include_body=false` omits body.
- event log filters by step and type.
- legacy timeline synthesizes event log.
- evidence resolver handles chunk, node, report, unresolved refs.
- all payloads include `read_only: true`.

MCP API tests:

- tools/list includes compact simulation tools.
- each tool returns short text and structured content.
- missing simulation raises a clear error.
- `projectos_get_simulation` remains available for explicit full export.

## Claude Desktop Workflow

Recommended default flow:

1. `projectos_run_simulation(project_id, query=...)`.
2. Poll task until complete.
3. `projectos_get_simulation_summary(project_id)`.
4. If graph review is needed:
   - `projectos_get_simulation_graph_delta(project_id, status="skipped")`
   - `projectos_get_simulation_graph_delta(project_id, status="proposed")`
5. If report review is needed:
   - `projectos_get_simulation_report_section(project_id, kind="executive_summary")`
   - request specific additional sections only as needed.
6. Resolve only selected evidence:
   - `projectos_get_simulation_evidence(project_id, evidence_refs=[...])`

Avoid `projectos_get_simulation` unless the user explicitly asks for the full result, export, debugging, or migration inspection.

## Non-Goals

- No graph mutation.
- No automatic application or rejection of deltas.
- No full source chunk dump.
- No UI implementation.
- No backend implementation in this documentation pass.
