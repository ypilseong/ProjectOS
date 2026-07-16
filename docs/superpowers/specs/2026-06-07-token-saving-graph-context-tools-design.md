# Token-Saving Graph Context Tools Design

> Follow-up to graph review workflow and citation validator. Keep the service and MCP tools read-only.

## Goal

Provide compact deterministic graph context payloads for Claude Desktop so agents can request a summary, one node neighborhood, or a bounded subgraph without sending the full graph JSON.

## Service API

`app/services/graph_context.py` exposes pure functions over a `networkx.DiGraph`:

- `summarize_graph_context(graph, *, max_hubs=10)`
- `get_node_context(graph, node_name, node_type=None, max_neighbors=20)`
- `get_subgraph_context(graph, node_name, node_type=None, depth=1, max_nodes=25)`

All functions return dictionaries with `read_only: true`, deterministic ordering, compact counts, limits, and match metadata where applicable.

## MCP Tools

`app/mcp_tools.py` exposes the service as compact read-only Claude Desktop tools:

- `projectos_get_graph_summary(project_id, max_hubs=10)`
- `projectos_get_node_context(project_id, node_name, node_type=None, max_neighbors=20)`
- `projectos_get_subgraph(project_id, node_name, node_type=None, depth=1, max_nodes=25)`

These tools require an existing project and built `graph.json`, return short text summaries plus structured payloads, and do not return full graph JSON.

## Matching

Node lookup matches either the graph node id or the node `name` attribute. Optional `node_type` filters by the node `type` attribute. When multiple nodes match, the payload marks the match as ambiguous and selects the first deterministic match by type, name, and id.

## Payload Shape

The summary payload includes node/edge counts, type counts, relation counts, source-file coverage, and limited hub summaries. Node context includes selected node data plus limited incoming and outgoing edge context. Subgraph context uses an undirected bounded neighborhood for discovery but returns original directed edges with relation labels.

## Safety

- No graph mutation.
- No filesystem, network, LLM, or MCP side effects.
- No full graph dump by default.
- `source_files` are preserved in node summaries.

## Non-Goals

- Graph patch generation or application.
- Simulation, Inbox, Google, or Obsidian UI changes.
