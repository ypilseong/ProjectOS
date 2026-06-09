# Claude Desktop MCP Instructions Update

> Documentation-only follow-up to token-saving graph context tools. Do not change backend, Inbox, Google, or Simulation code.

## Goal

Update the Claude Desktop MCP setup instructions so graph-ready workflows use compact graph context tools instead of loading the full graph JSON into Claude Desktop by default.

## Scope

- Add `projectos_get_graph_summary`, `projectos_get_node_context`, and `projectos_get_subgraph` to the exposed MCP tool list.
- Document the default post-graph workflow as summary first, then targeted node context or bounded subgraph requests.
- Limit `projectos_get_graph` to explicit full-export, debugging, graph patch preparation, or other complete-JSON needs.
- Document that full simulation JSON should not be added to Claude Desktop context by default.

## Updated Graph Context Workflow

After `projectos_build_graph` completes and `projectos_get_graph_health` has been checked, Claude Desktop should:

1. Call `projectos_get_graph_summary`.
2. Use the summary to identify relevant hubs, entity types, relations, and coverage gaps.
3. Call `projectos_get_node_context` for a specific entity's direct incoming/outgoing relationship context.
4. Call `projectos_get_subgraph` only when a bounded multi-hop neighborhood is needed.
5. Call `projectos_get_graph` only when complete graph JSON is explicitly required for export, debugging, or patch preparation.

This keeps routine Claude Desktop context small while preserving access to richer graph detail on demand.

## Simulation Guidance

Claude Desktop should not load the entire simulation payload by default after `projectos_run_simulation`. Because the current `projectos_get_simulation` tool may return a large report, use it only for short confirmation or when the user explicitly asks to inspect simulation output.

Future documentation should shift the default simulation workflow to delta or report-section tools once those MCP tools exist.

## Non-Goals

- No backend implementation changes.
- No Inbox, Google, or Simulation code changes.
- No graph context service redesign.
- No automated prompt generation for Claude Desktop.
