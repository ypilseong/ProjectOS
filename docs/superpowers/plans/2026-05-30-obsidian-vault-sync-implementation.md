# Obsidian Vault Sync Implementation Plan

> Spec: `docs/superpowers/specs/2026-05-30-obsidian-plugin-vault-sync-design.md`

## Goal

Implement vault sharing mode 1: ProjectOS keeps writing the server-side vault for the existing web app/RAG/health paths, while also exposing the same generated vault content as a JSON payload for an Obsidian plugin to write into the user's local vault.

## Phase 1 — Backend Payload Contract

- [x] Add `VaultNote`, `VaultFile`, and `VaultPayload` models under `src/backend/app/models/vault.py`.
- [x] Refactor `ObsidianWriterAgent` into:
  - `build_payload(graph, profiles=None, project_id=None, delta=False) -> VaultPayload`
  - `write_payload(payload, vault_path, delta=False, progress_callback=None) -> None`
  - `run(...)` as a compatibility wrapper calling both.
- [x] Preserve current behavior:
  - generated entity folders are cleared on full rebuild only
  - `.obsidian/app.json` and `.obsidian/graph.json` are written
  - delta mode merges existing notes instead of overwriting
  - `_index.md`, `_index.canvas`, and `log.md` are produced
  - existing web vault tree/file/download, QueryAgent, and graph health continue to read server-side files.

## Phase 2 — Export API

- [x] Add `GET /api/projects/{project_id}/vault/export` in `src/backend/app/api/projects.py`.
- [x] Load `graph.json`; return 404 if graph is not built yet.
- [x] Load `profiles.json` if present.
- [x] Return `ObsidianWriterAgent().build_payload(...)` as JSON.
- [x] Keep existing `/vault`, `/vault/file`, and `/vault/download` unchanged.

## Phase 3 — Backend Tests

- [x] Extend `test_obsidian_writer_agent.py`:
  - payload contains notes/canvas/index/log entry
  - `run()` still writes the same key files
  - delta mode still preserves custom note content
- [x] Add API tests for `/vault/export`:
  - returns 404 when graph is missing
  - returns expected payload structure when graph exists

## Phase 4 — Obsidian Plugin Scaffold

- [x] Create `src/obsidian-plugin/` with standard Obsidian TypeScript scaffold.
- [x] Add settings for Base URL, auto-managed project id, and target folder.
- [x] Add project create/list/select flow so users do not need to remember backend ids.
- [x] Implement payload-to-vault write mapping.
- [x] Implement side panel:
  - sync from `/vault/export`
  - upload files and trigger graph build
  - run/load document analysis
  - stream task/chat responses.
- [x] Add plugin build verification once plugin dependencies are installed.
- [x] Add plugin unit tests for payload-to-vault mapping.
- [x] Add Mac/Obsidian manual install documentation.
- [x] Build installable plugin folder under `dist/obsidian-plugin-projectos-vault-sync`.
- [x] Add Obsidian CSS styling for project cards, analysis, and query output.

## Current Next Step

Phase 1-4 implementation is in place. Backend tests pass, plugin unit tests pass, and the Obsidian plugin production build succeeds. Manual Obsidian runtime validation remains.

## Phase 5 — Claude Code Only Fallback

- [x] Add `GRAPH_BUILD_MODE=chunk|claude_task`.
- [x] Add isolated `ClaudeTaskRunner`.
  - task workspace is outside the repo under `CLAUDE_TASKS_DIR`
  - task-specific `CLAUDE.md`, `input.json`, `schema.json`, `output.json`
  - task `CLAUDE.md` is passed as `--system-prompt`
  - process cwd is the isolated task workspace, not the ProjectOS repo
  - existing repo `CLAUDE.md` files are not merged into the task
- [x] Add `ClaudeTaskGraphBuilderAgent` for local-LLM-unavailable environments.
- [x] Add config:
  - `CLAUDE_CODE_MODEL`
  - `CLAUDE_TASKS_DIR`
  - `CLAUDE_TASK_BARE`
  - `CLAUDE_TASK_TIMEOUT`
- [x] Verify `--bare` is not default in this environment because Claude OAuth/keychain auth fails with `--bare`.
- [x] Add unit tests for task isolation, command construction, schema required-key validation, and task graph extraction.
- [x] Run Claude task smoke test with `claude-haiku-4-5`.
- [x] Run real file graph extraction smoke test with `ClaudeTaskGraphBuilderAgent`.

Claude task smoke result:

- result: `{"ok": true, "value": "ProjectOS"}`
- usage: 1 call, cost `$0.0447438`

Claude task graph smoke result:

- result: 4 nodes / 3 edges
- usage: 1 call, cost `$0.0263992`
