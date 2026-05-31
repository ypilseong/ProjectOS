# LLM Wiki-Inspired ProjectOS Improvements

> Based on Andrej Karpathy's LLM Wiki pattern: compile raw sources into a durable wiki layer, use indexes/logs/lints, and avoid repeatedly reinterpreting raw chunks for every downstream task.

## Goal

Adapt ProjectOS from a purely graph-first pipeline into a hybrid graph + wiki knowledge system:

- Use fast local LLMs for bulk extraction.
- Use Claude Code only for high-value synthesis/review tasks.
- Make the Obsidian vault a durable, queryable knowledge layer, not only an export artifact.
- Add provenance and linting so graph/vault quality can be inspected and improved over time.

## Task 1 — Split Local LLM and Claude Responsibilities

- [x] Bulk graph extraction must always use the local OpenAI-compatible backend.
- [x] `isolated_reextract` should also use local backend because it is chunk/context extraction.
- [x] LLM dedup inside graph build should use local backend by default to avoid slow Claude loops.
- [x] Claude Code remains available for single-shot/high-value tasks such as ontology, profile, analysis, chat, and later wiki synthesis/lint.
- [x] UI copy should make the split clear.
- [x] Add tests proving GraphBuilderAgent and LLM dedup default to local even when global settings are Claude.

## Task 2 — Make Vault Wiki the First-Class Query Layer

- [x] QueryAgent should load `vault/_index.md` before graph search.
- [x] QueryAgent should retrieve relevant entity pages from the vault and include them in prompt context.
- [x] Keep graph search as structured relation context.
- [x] Add tests for index/page-backed query prompts.

## Task 3 — Add `log.md`

- [x] ObsidianWriterAgent should append ingest/build events to `log.md`.
- [x] Include source files, node/edge counts, and changed pages.
- [x] Include project id in log entries.
- [x] QueryAgent should optionally include recent log entries for temporal context.

## Task 4 — Extend Graph Health into Wiki/Graph Lint

- [x] Detect graph nodes without vault pages.
- [x] Detect vault pages without graph nodes.
- [x] Detect orphan pages and orphan graph nodes.
- [x] Detect duplicate page/entity names.
- [x] Detect missing source/provenance metadata.

## Task 5 — Strengthen Provenance

- [x] Preserve source file and chunk ids on nodes and edges.
- [x] Render source provenance in vault notes.
- [x] Make QueryAgent cite source files/pages in answers when possible.

## Notes

- Claude Code CLI is too slow for 39-chunk graph extraction because ProjectOS currently launches a separate `claude -p` subprocess per chunk.
- The practical policy is: local LLM for loops, Claude for summaries/reviews/final synthesis.
