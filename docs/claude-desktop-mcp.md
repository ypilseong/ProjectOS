# Claude Desktop MCP Setup

ProjectOS exposes MCP tools through the backend HTTP endpoint `POST /mcp`.
Claude Desktop local MCP config launches stdio subprocesses, so use the stdio
bridge at `src/backend/projectos_mcp_stdio.py`.

## Prerequisite

Start the ProjectOS backend first:

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS/src/backend
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

Check the backend MCP endpoint:

```bash
curl -s http://127.0.0.1:8002/mcp/tools
```

## Claude Desktop Config

Edit `claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "projectos": {
      "command": "python3",
      "args": [
        "/raid/home/a202121010/workspace/projects/ProjectOS/src/backend/projectos_mcp_stdio.py"
      ],
      "env": {
        "PROJECTOS_MCP_URL": "http://127.0.0.1:8002/mcp"
      }
    }
  }
}
```

Restart Claude Desktop after editing the config.

## Exposed Tools

- `projectos_create_project`
- `projectos_upload_file`
- `projectos_get_upload_api`
- `projectos_list_inbox`
- `projectos_preview_inbox_file`
- `projectos_ingest_inbox_file`
- `projectos_ingest_inbox_files`
- `projectos_get_task`
- `projectos_build_ontology`
- `projectos_build_graph`
- `projectos_list_projects`
- `projectos_get_graph_health`
- `projectos_get_hot_context`
- `projectos_get_research_candidates`
- `projectos_review_graph`
- `projectos_get_ontology`
- `projectos_get_graph`
- `projectos_get_graph_summary`
- `projectos_get_node_context`
- `projectos_get_subgraph`
- `projectos_apply_graph_patch`
- `projectos_reconcile_vault`
- `projectos_query_career_graph`
- `projectos_run_analysis`
- `projectos_get_analysis`
- `projectos_run_profiles`
- `projectos_get_profiles`
- `projectos_run_simulation`
- `projectos_get_simulation`
- `projectos_generate_digest`
- `projectos_list_digests`
- `projectos_get_digest`
- `projectos_get_vault_note`
- `projectos_read_traces`
- `projectos_google_status`
- `projectos_google_auth_url`
- `projectos_google_sync`

`projectos_upload_file` accepts either `content_base64` for binary files such as
PDF/DOCX or `content_text` for plain text. Uploading a file starts the normal
ProjectOS parse task and returns a `task_id`.

Set `file_type` on every `projectos_upload_file` call so ProjectOS can apply
the right extraction prompt later. Supported document-oriented values include
`cv`, `paper`, `report`, `memo`, `email`, and `note`. For the regular
multipart upload API, pass `file_types` as a JSON object keyed by uploaded
filename, for example `{"cv.pdf":"cv","draft-paper.pdf":"paper"}`.

For remote deployments, prefer `projectos_get_upload_api` plus direct
multipart upload from the user's browser or terminal. This avoids sending file
bytes through Claude Desktop's MCP tool arguments and materially reduces Claude
context usage. Configure the public URL with:

```bash
BACKEND_PUBLIC_URL=https://your-projectos-server.example.com
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
Desktop should use the returned `suggested_file_type` unless the user explicitly
overrides it. Ingest files with `projectos_ingest_inbox_file` or
`projectos_ingest_inbox_files`; use `file_type: "auto"` to reuse local
classification.

## Initial Graph Build Workflow

Use this order from Claude Desktop:

1. `projectos_create_project`
2. Upload documents with one of:
   - `projectos_list_inbox` then `projectos_ingest_inbox_file(s)` for synced server folders
   - `projectos_get_upload_api` + direct multipart upload for browser/curl uploads
   - `projectos_upload_file` only for small text files
3. Poll `projectos_get_task` until the upload parse task is `completed`
4. `projectos_build_ontology`
5. Poll `projectos_get_task` until the ontology task is `completed`
6. `projectos_build_graph`
7. Poll `projectos_get_task` until the graph task is `completed`
8. `projectos_get_graph_health`

After the graph is ready, Claude Desktop can:

- call `projectos_get_hot_context` for a compact session-entry primer
- call `projectos_get_graph_summary` first to inspect compact graph counts, type/relation distribution, coverage, and hubs
- call `projectos_get_node_context` for specific entities that need local incoming/outgoing edge context
- call `projectos_get_subgraph` for a bounded neighborhood when a question needs multi-hop context
- use `projectos_get_research_candidates` or `projectos_review_graph` for targeted graph quality review before asking for broad context
- use `projectos_query_career_graph` for graph/vault/chunk RAG
- use `projectos_apply_graph_patch` after review to persist graph corrections and rebuild the vault
- use `projectos_reconcile_vault` to inspect or apply graph changes implied by manual Obsidian vault edits
- use `projectos_run_analysis` then `projectos_get_analysis` for document analysis
- use `projectos_run_profiles` then `projectos_get_profiles` for profile summaries
- use `projectos_run_simulation`, poll `projectos_get_task`, then call `projectos_get_simulation` only for a short status check or when the user explicitly asks to inspect the simulation report
- use `projectos_generate_digest`, `projectos_list_digests`, and `projectos_get_digest` for daily digest files
- use `projectos_google_sync`, poll `projectos_get_task`, then query the graph again after Gmail/Drive material is imported

Do not request the full graph JSON as the default post-build context. Use
`projectos_get_graph_summary` first, then request `projectos_get_node_context`
or `projectos_get_subgraph` only for the entities or neighborhoods needed for
the current task. Reserve `projectos_get_graph` for explicit export, debugging,
patch preparation, or other cases where the complete graph JSON is materially
required.

Do not place the full simulation JSON into Claude Desktop's conversation context
by default. The current `projectos_get_simulation` tool can return a large report,
so use it only for brief confirmation or explicit user-requested inspection.
Future MCP guidance should prefer delta or report-section simulation tools once
they exist.

Do not synthesize a graph manually from attachment text. ProjectOS graph builds
must go through ontology extraction and graph build tasks.

The bridge writes logs to stderr only. stdout is reserved for newline-delimited
MCP JSON-RPC messages.

## Google Gmail/Drive Sync

Configure OAuth credentials in `src/backend/.env` or the backend environment:

```bash
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://127.0.0.1:8002/api/google/oauth/callback
```

Then:

1. Call `projectos_google_auth_url`.
2. Open the returned URL in a browser and approve Gmail/Drive read access.
3. Let Google redirect to `/api/google/oauth/callback`; the backend stores `google_token.json`.
4. Call `projectos_google_sync` with a built `project_id`.
5. Poll `projectos_get_task` until the Google sync task is `completed`.

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
