# NetworkX vs Graphify Assessment

**Date:** 2026-06-10  
**Status:** Recommendation  
**Scope:** ProjectOS graph engine and possible Graphify adoption

## Summary

ProjectOS should keep **NetworkX** as the core graph engine.

Graphify is useful, but it is not a direct replacement for NetworkX in this project. NetworkX is a graph data structure and algorithm library. Graphify is an external knowledge-graph generation pipeline for AI coding assistants that can read folders, extract code/document structure, cluster graph communities, and export graph artifacts. In fact, Graphify itself builds on NetworkX.

The best position is:

- Keep NetworkX for ProjectOS runtime graph storage, manipulation, serialization, and graph-aware services.
- Evaluate Graphify as an optional ingestion/audit tool, especially for codebase analysis or imported project folders.
- Do not replace the existing ProjectOS graph model with Graphify without a schema migration and benchmark.

## Current ProjectOS Usage

ProjectOS currently treats NetworkX as part of the product architecture:

- `README.md` lists NetworkX as a backend stack component.
- `src/backend/pyproject.toml` depends on `networkx>=3.3`.
- The approved design spec defines the pipeline as local files -> LLM entity/relation extraction -> NetworkX graph -> Obsidian vault.
- `GraphBuilderAgent` constructs an `nx.DiGraph`, loads existing graphs with `nx.node_link_graph`, and saves graph JSON with `nx.node_link_data`.
- Graph context, health checks, auto-research candidates, Obsidian writing, patching, and MCP tooling operate directly over NetworkX graph objects.

This means NetworkX is not only an implementation detail. It is part of the internal contract between backend services, JSON storage, and frontend graph rendering.

## NetworkX Strengths

NetworkX fits ProjectOS well because ProjectOS needs a controllable in-process graph model:

- It supports directed graphs, which match ProjectOS relations such as `Project -> Skill`, `Person -> Project`, and `Publication -> Organization`.
- It allows arbitrary node and edge attributes, which ProjectOS uses for `type`, `name`, `description`, `source_files`, `source_chunk_ids`, `relation`, `confidence`, and evidence metadata.
- It has mature graph traversal and analysis APIs for degree counts, predecessors, successors, connected components, relabeling, and serialization.
- It keeps the graph local and inspectable, which matches ProjectOS's local-first design.
- It is simple to test because graph objects can be built directly in unit tests.

For the current scale and product shape, NetworkX gives the right level of control.

## NetworkX Weaknesses

NetworkX also has real limits:

- It is mostly pure Python, so very large graphs can become slow or memory-heavy.
- It is not a persistent graph database. Indexing, query optimization, transactions, and concurrency control are application responsibilities.
- Serialization compatibility is manual. ProjectOS already has to normalize NetworkX 3.x `edges` data into frontend-compatible `links`.
- It does not generate semantic graph content by itself. Entity extraction, ontology constraints, deduplication, graph health checks, and audit reports must be implemented separately.

These weaknesses are manageable for ProjectOS today, but they should drive future guardrails and benchmarks.

## Graphify Strengths

Graphify is stronger than NetworkX when the goal is to quickly build an assistant-readable graph from a folder:

- It combines Tree-sitter static analysis with LLM-driven semantic extraction.
- It supports mixed inputs such as code, Markdown, PDFs, diagrams, images, and media.
- It exports interactive HTML, JSON graph artifacts, and a plain-language graph report.
- It includes assistant integrations for tools such as Claude Code, Codex, and OpenCode.
- It provides useful code-intelligence features such as AST-derived structure, community detection, central node detection, and surprising connection reports.

Graphify is therefore attractive for codebase understanding and one-shot graph generation.

## Graphify Weaknesses

Graphify is not a clean replacement for ProjectOS's graph layer:

- Its primary domain is codebase and corpus understanding, not ProjectOS's career/project ontology.
- Its schema and artifact conventions are external to ProjectOS's `Person`, `Project`, `Skill`, `Achievement`, `Organization`, and Obsidian rendering contracts.
- It adds CLI/tooling dependency risk to a runtime path that is currently simple Python.
- It is a fast-moving young tool. Version behavior, output schema, and assistant hook behavior may change more often than NetworkX APIs.
- It would not automatically replace ProjectOS features such as source chunk evidence, profile generation, vault reconciliation, graph patching, MCP project tools, and user-specific career summaries.

Adopting it as the core graph engine would likely increase integration complexity instead of reducing it.

## Decision

Use **NetworkX as the ProjectOS graph engine**.

Use **Graphify only as an optional auxiliary pipeline** unless a future benchmark shows that it can improve a specific ingestion or analysis workflow without breaking ProjectOS's graph contract.

## Recommended Remaining Work

1. Define a graph boundary module.
   Centralize graph load/save compatibility, especially `edges` vs `links`, so NetworkX serialization behavior does not leak across services.

2. Add graph scale benchmarks.
   Measure graph build, context query, health check, vault rendering, and frontend load time at realistic node/edge counts.

3. Pilot Graphify as an import source.
   Run Graphify on a representative code/document folder and inspect `graphify-out/graph.json`, `GRAPH_REPORT.md`, and `graph.html`.

4. Design a Graphify-to-ProjectOS adapter only if the pilot is useful.
   Map Graphify nodes and edges into ProjectOS entity types and relation types. Reject ambiguous mappings rather than forcing them into the career ontology.

5. Compare output quality.
   Compare ProjectOS extraction vs Graphify-assisted import on precision, duplicate rate, source evidence quality, relation usefulness, and token/cost impact.

6. Keep Graphify out of the critical runtime path until proven.
   Prefer a manual or optional background import flow before adding it to normal graph build execution.

7. Prepare a fallback path for large graphs.
   If NetworkX becomes a bottleneck, evaluate a dedicated graph backend or faster graph library. Do this based on measured bottlenecks, not tool popularity.

## Sources

- NetworkX documentation: https://networkx.org/documentation/stable/reference/introduction.html
- NetworkX graph types: https://networkx.org/documentation/latest/reference/classes/index.html
- NetworkX PyPI: https://pypi.org/project/networkx/
- Graphify website: https://graphify.net/zh/
- Graphify PyPI package: https://pypi.org/project/graphifyy/0.5.4/
