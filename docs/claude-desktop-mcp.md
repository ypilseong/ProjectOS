# Claude Desktop MCP Setup

ProjectOS exposes MCP tools through the backend HTTP endpoint `POST /mcp`.
Claude Desktop launches stdio subprocesses, so use the ProjectOS stdio bridge.
For macOS Claude Desktop with ProjectOS running on an SSH server, launch the
bridge over SSH.

## Prerequisite

Start the ProjectOS backend first:

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS/src/backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 14006
```

Check the backend MCP endpoint:

```bash
curl -s http://127.0.0.1:14006/mcp/tools
```

## Claude Desktop Config

For macOS Claude Desktop, edit `claude_desktop_config.json` and add this. Replace
`projectos-server` with your SSH host alias:

```json
{
  "mcpServers": {
    "projectos": {
      "command": "ssh",
      "args": [
        "projectos-server",
        "cd /raid/home/a202121010/workspace/projects/ProjectOS/src/backend && PROJECTOS_MCP_URL=http://127.0.0.1:14006/mcp PROJECTOS_MCP_LOG_DIR=/raid/home/a202121010/workspace/projects/ProjectOS/logs python3 projectos_mcp_stdio.py"
      ]
    }
  }
}
```

Restart Claude Desktop after editing the config.

To verify that Claude Desktop reached the server, check that `logs/mcp-stdio.jsonl`
and `logs/mcp.jsonl` are created after a ProjectOS request.

Claude Desktop sees only the curated core MCP tools by default. Detailed legacy,
debug, and section-specific tools remain callable by backend tests and internal
compatibility paths but are not advertised through `tools/list`.

For regular multipart upload API calls, pass `file_types` as a JSON object keyed
by uploaded filename, for example `{"cv.pdf":"cv","draft-paper.pdf":"paper"}`.

For remote deployments, prefer `projectos_get_upload_api` plus direct
multipart upload from the user's browser or terminal. This avoids sending file
bytes through Claude Desktop's MCP tool arguments and materially reduces Claude
context usage. Configure the public URL with:

```bash
BACKEND_PUBLIC_URL=http://your-projectos-server:14006
```

For personal remote-server workflows, a synced inbox folder is usually better
than uploading bytes through MCP. Configure:

```bash
INBOX_DIR=/raid/home/a202121010/workspace/projects/ProjectOS/project-inbox
INBOX_PREVIEW_CHARS=1500
```

Use device-specific subfolders under `project-inbox`, for example `Macbook/`
and `Windows/`. Claude Desktop should use `projectos_list_inbox` to inspect the
synced folder named by the user, such as `relative_path: "Macbook"` or
`relative_path: "Windows"`.
When the listing contains files, ProjectOS extracts a short server-side preview
and classifies each file with the local LLM using an English prompt. Claude
Desktop should ingest files with `projectos_ingest_inbox_files`; omit
`file_types` or use `auto` to reuse local classification.

## Initial Graph Build Workflow

Use this order from Claude Desktop:

1. `projectos_create_project`
2. Upload documents with one of:
   - `projectos_list_inbox` then `projectos_ingest_inbox_files` for synced server folders
   - `projectos_get_upload_api` + direct multipart upload for browser/curl uploads
3. Wait for the upload parse task with `projectos_get_task`
4. `projectos_build_ontology`
5. Wait for the ontology task with `projectos_get_task`
6. `projectos_build_graph`
7. Wait for the graph task with `projectos_get_task`
8. `projectos_get_graph_health`

For long-running tasks, do not repeatedly call `projectos_get_task` at short
intervals. Call it with `wait_seconds: 30`, plus the previous `status` and
`progress` when available. It returns when the task completes, fails, makes
meaningful progress, or the wait window expires.

After the graph is ready, Claude Desktop can:

- call `projectos_get_graph_summary` first to inspect compact graph counts, type/relation distribution, coverage, and hubs
- call `projectos_get_node_context` for specific entities that need local incoming/outgoing edge context
- use `projectos_query_career_graph` for graph/vault/chunk RAG
- use `projectos_apply_graph_patch` after review to persist graph corrections and rebuild the vault
- use `projectos_run_simulation`, wait with `projectos_get_task`, then start with `projectos_get_simulation_summary`
- use `projectos_google_sync`, wait with `projectos_get_task`, then query the graph again after Gmail/Drive material is imported

Do not request the full graph JSON as the default post-build context. Use
`projectos_get_graph_summary` first, then request `projectos_get_node_context`
only for entities needed for the current task.

Do not place the full simulation JSON into Claude Desktop's conversation context
by default. Use `projectos_get_simulation_summary`.

Do not synthesize a graph manually from attachment text. ProjectOS graph builds
must go through ontology extraction and graph build tasks.

## MCP Traffic Logs

Backend MCP traffic is written as JSONL:

```bash
tail -f /raid/home/a202121010/workspace/projects/ProjectOS/logs/mcp.jsonl
```

Claude Desktop stdio bridge traffic is written separately:

```bash
tail -f /raid/home/a202121010/workspace/projects/ProjectOS/logs/mcp-stdio.jsonl
```

Project-scoped MCP responses are also copied to:

```bash
logs/projects/<project_id>/mcp.jsonl
```

By default, large fields such as `content_base64` and `content_text` are logged
with length and preview only. Set `PROJECTOS_MCP_LOG_FULL_PAYLOADS=true` in the
backend and Claude Desktop bridge environment only when full raw payload capture
is required.

The bridge still reserves stdout for newline-delimited MCP JSON-RPC messages;
status messages go to stderr and JSONL traffic goes to the log files above.

## Google Gmail/Drive Sync

Configure OAuth credentials in `src/backend/.env` or the backend environment:

```bash
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://127.0.0.1:14006/api/google/oauth/callback
```

Then:

1. Call `projectos_google_auth_url`.
2. Open the returned URL in a browser and approve Gmail/Drive read access.
3. Let Google redirect to `/api/google/oauth/callback`; the backend stores `google_token.json`.
4. Call `projectos_google_sync` with a built `project_id`.
5. Wait for the Google sync task with `projectos_get_task`.

`projectos_google_sync` writes Gmail messages as `email` markdown files and Drive
documents as `note`/`paper`/`report` files under the project's `files/` folder.
It reparses changed files and runs an incremental graph build when the project
already has `chunks.json`, `ontology.json`, and `graph.json`.

For scheduled sync, set:

```bash
GOOGLE_SYNC_ENABLED=true
GOOGLE_SYNC_PROJECT_ID=<project_id>
GOOGLE_SYNC_POLL_SECONDS=3600
```

## Graph Patch Tool

After Claude Desktop reviews graph quality, corrections must be written back
through `projectos_apply_graph_patch`. Editing the graph only in Claude Desktop's
conversation context does not update ProjectOS storage.

Patch shape:

```json
{
  "nodes_add": [
    {
      "type": "Skill",
      "name": "Graph RAG",
      "description": "Graph retrieval augmented generation"
    }
  ],
  "nodes_update": [
    {
      "type": "Project",
      "name": "ProjectOS",
      "set": {
        "description": "Local career knowledge graph system"
      }
    }
  ],
  "nodes_delete": [
    {
      "type": "Skill",
      "name": "Duplicate Skill"
    }
  ],
  "edges_add": [
    {
      "source_type": "Project",
      "source_name": "ProjectOS",
      "target_type": "Skill",
      "target_name": "Graph RAG",
      "relation": "USES_SKILL",
      "confidence": 0.8,
      "evidence": "Reviewer-confirmed from uploaded docs"
    }
  ],
  "edges_delete": [
    {
      "source_type": "Project",
      "source_name": "ProjectOS",
      "target_type": "Skill",
      "target_name": "Wrong Skill",
      "relation": "USES_SKILL"
    }
  ]
}
```

Nodes can be addressed by `id`/`node_id` or by `type` + `name`. Edges can use
`source_id`/`target_id` or `source_type` + `source_name` and `target_type` +
`target_name`. The tool validates entity types/names, updates `graph.json`, and
regenerates the Obsidian vault for the project.

## Recommended Claude Desktop Project Instructions

Use the following as the ProjectOS project instruction text in Claude Desktop.

```text
Use ProjectOS through MCP.
Always answer the user in Korean.

Principles:
- Treat ProjectOS files, chunks, graphs, vault notes, sync state, simulations, and reports as the source of truth.
- Graph edits discussed only in conversation are not persisted. Say a graph change was saved only after the ProjectOS MCP mutation succeeds.
- Do not invent facts, relations, or source evidence.
- Do not paste full JSON payloads or large logs unless the user explicitly asks.

Initial build:
- Create a new project unless the user clearly refers to an existing project.
- When using the server inbox, use inbox-relative paths only. Example: `Macbook/CV`.
- If the user asks to use a whole folder, list the folder first and ingest only files. Exclude `.DS_Store`, hidden files, and temporary files.
- For long-running tasks, call `projectos_get_task` with `wait_seconds: 30` and the previous `status`/`progress`; do not make rapid repeated status calls.
- Report intermediate progress only when the user asks or when a task fails.
- After graph build, check node count, edge count, and graph health.

Graph review:
- After every initial graph build, review graph quality before calling it final.
- Check duplicate nodes, wrong types, missing relations, noisy or isolated nodes, and claims without source evidence.
- Apply only clear, evidence-backed corrections. Put uncertain items under "Needs confirmation".

Reporting:
- Distinguish persisted ProjectOS state from Claude's review judgment.
- When a limitation or uncertainty exists, state it explicitly.
```
