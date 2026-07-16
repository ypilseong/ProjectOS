# Graph and Simulation Quality Assessment

Date: 2026-06-10
Project sample: `cb98c8c7`

## Current State

The simulation visualization is now reachable and useful, but the visible UI should not be confused with data quality. The current system can render graph and simulation output, yet the underlying graph still mixes career evidence, paper/report concepts, generated topic nodes, and UI navigation helpers in one analytical surface.

Observed sample graph size after paper-author cleanup:

- Nodes: 286
- Edges: 507
- Person nodes: 2
- Project nodes: 55
- Skill nodes: 132
- Publication nodes: 48
- Category nodes: 10

The exact duplicate count by `type:name` is currently 0. This only means exact string duplicates were removed or avoided. It does not prove semantic deduplication quality.

## Critical Issues

### 1. The Graph Is Too Broad and Shallow

The graph contains too many candidate nodes for a personal career graph. In particular, 132 `Skill` nodes and 55 `Project` nodes indicate that source documents are promoting many mentioned concepts into first-class career entities.

This weakens downstream behavior because the system cannot reliably distinguish:

- Skills the user actually has.
- Topics discussed in papers or reports.
- Methods mentioned as background.
- Project ideas or speculative future directions.
- Real projects with user ownership.

The graph needs a stronger promotion policy. A node should become part of the primary career graph only when there is sufficient source-backed evidence that it represents the user's experience, role, output, or durable expertise.

### 2. Category Hub Nodes Distort Analysis

Category nodes are still present in the graph data. In the sample graph:

- `Category:Skills` has degree 132.
- `Category:Projects` has degree 55.
- `Category:Publications` has degree 49.

These nodes are useful for browsing, but harmful for analytical graph operations. They dominate centrality, neighborhood expansion, and persona context selection. Hiding them in the visualization is only a UI mitigation; the analytical graph still sees them.

The system should separate:

- Analytical graph: evidence-bearing entities and relations only.
- Navigation graph: category/grouping nodes for UI exploration.

### 3. Skill Nodes Have Mixed Semantics

The `Skill` type currently mixes multiple conceptual levels:

- Concrete technical abilities.
- Research areas.
- Model families.
- Methods.
- Benchmarks.
- Paper/report keywords.
- Broad umbrella concepts.

For example, a broad concept like `Large Language Model` can become highly connected and appear important, but this does not necessarily mean it is a verified skill attributable to the user. The system needs subtyping or stricter criteria for `Skill` promotion.

Recommended distinction:

- `Skill`: user has direct evidence of practical use.
- `ResearchTopic`: paper/report subject or research area.
- `Method`: algorithmic or methodological concept.
- `Tool`: concrete tool, library, platform, or framework.
- `Keyword`: weak extraction candidate not yet promoted.

### 4. Paper and Report Content Can Still Pollute the Career Graph

Paper author cleanup addressed one visible problem: external authors should not become graph `Person` nodes unless they already match existing people. However, paper/report extraction can still promote many non-career entities into the primary graph.

The remaining risk is that papers and reports generate:

- Topic-like `Skill` nodes.
- Project-like speculative concepts.
- Institution or organization nodes without user relationship evidence.
- Publication-adjacent concepts treated as user expertise.

This suggests the system needs source-aware graph layers:

- Career layer: CV, profile, direct work evidence.
- Publication layer: papers and bibliographic metadata.
- Knowledge layer: paper/report topics, methods, background concepts.
- Simulation layer: proposed nodes and edges before acceptance.

Cross-layer promotion should be explicit, not automatic.

### 5. Semantic Duplicate Risk Remains

Exact duplicate detection is not enough. The graph can still contain semantic variants with different names, casing, plurality, abbreviations, or Korean/English translations.

Examples of likely duplicate families:

- `LLM`, `Large Language Model`, `Large Language Models`.
- `RAG`, `Retrieval-Augmented Generation`.
- Korean and English variants of the same institution, project, or topic.

The current graph quality cannot be judged by exact duplicate count alone. Semantic deduplication should use canonical labels, aliases, normalized identifiers, and reviewable merge candidates.

### 6. Evidence Tracking Is Too Weak

Many downstream decisions are only as reliable as their evidence trail. The current output commonly relies on string references such as node IDs, file names, or short evidence labels. This is not enough for auditability.

The system should preserve:

- Source file.
- Chunk ID.
- Character range or page number when available.
- Extracted quote or compact evidence text.
- Confidence and extraction method.
- Whether the relation is direct evidence or inferred.

Without stronger evidence anchoring, graph cleanup and simulation review become subjective.

### 7. Simulation Debate Is Structurally Improved but Still Needs Quality Controls

The simulation agent now runs sequential persona turns and then synthesizes the result. This is a better structure than generating a full timeline in one call. However, the quality still depends on controls that are not yet strong enough.

Remaining risks:

- Debate turns may still converge too quickly without real disagreement.
- Personas may repeat generic advice rather than challenge assumptions.
- Synthesis may introduce claims that are not grounded in the debate.
- Partial turn failures fall back silently into generic statements.
- The UI does not clearly distinguish old stored simulations from new multi-turn simulations.

The result schema should include execution metadata:

- Debate engine version.
- Number of actual turn calls.
- Number of fallback turns.
- Synthesis model and timestamp.
- Whether each turn had previous-turn context.

### 8. Stored Simulation Results Can Be Misleading

Existing stored simulation runs may have been generated by older logic. The UI can display them correctly, but users may assume they were generated by the current multi-turn debate engine.

This is a product issue and a data lineage issue. The simulation page should show whether a result was produced by:

- Legacy single-call timeline generation.
- Multi-turn persona debate.
- Fallback simulation.

Without this, old results and new results are visually indistinguishable.

### 9. PDF/Report Re-Extraction Stability Is Suspect

Recent logs showed repeated `reextract_with_context failed` warnings for `최신 LLM 융합 트렌드 보고서.pdf`. The current server is healthy, but that historical pattern indicates that document-specific re-extraction can fail repeatedly without a clear user-facing diagnosis.

The graph builder should report:

- Which file failed.
- Which stage failed.
- Whether the failure was timeout, model error, parsing issue, or invalid JSON.
- Whether the graph was built with degraded extraction.

This matters because graph quality issues may come from partial extraction, not only ontology design.

## Recommended Priorities

### Priority 1: Split Graph Layers

Separate the primary career graph from paper/report knowledge and UI navigation data. Category nodes should not participate in analysis. Paper/report topics should not become user career facts without explicit promotion.

### Priority 2: Add Promotion Rules

Require direct evidence before a node is promoted into the career layer. For example:

- `Skill` requires CV/profile/project evidence of use.
- `Project` requires user role, ownership, or output evidence.
- `Organization` requires affiliation, employment, education, collaboration, or publication relationship.
- `Publication` can exist in the publication layer, but its authors/topics should not automatically become user entities.

### Priority 3: Improve Canonicalization and Merge Review

Add semantic duplicate candidate generation with aliases and confidence. Do not auto-merge aggressively; present reviewable merge candidates first.

### Priority 4: Strengthen Evidence Anchoring

Every promoted node and edge should carry source-backed provenance. Simulation proposals should reference evidence anchors, not only names.

### Priority 5: Add Simulation Lineage

Add metadata that makes it clear whether a simulation result came from the legacy engine, the multi-turn debate engine, or a fallback path. The UI should display this compactly.

## Bottom Line

The current system has crossed the threshold from "not visible" to "visible and interactive." The next quality bottleneck is not UI rendering; it is graph semantics. The highest-impact fix is source-aware graph layering with explicit promotion rules. Without that, simulation will continue to reason over a graph that is too noisy, too flat, and too permissive.
