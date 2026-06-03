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
- `projectos_get_task`
- `projectos_build_ontology`
- `projectos_build_graph`
- `projectos_list_projects`
- `projectos_get_graph_health`
- `projectos_query_career_graph`
- `projectos_generate_digest`
- `projectos_list_digests`
- `projectos_get_digest`
- `projectos_get_vault_note`
- `projectos_read_traces`

`projectos_upload_file` accepts either `content_base64` for binary files such as
PDF/DOCX or `content_text` for plain text. Uploading a file starts the normal
ProjectOS parse task and returns a `task_id`.

## Initial Graph Build Workflow

Use this order from Claude Desktop:

1. `projectos_create_project`
2. `projectos_upload_file`
3. Poll `projectos_get_task` until the upload parse task is `completed`
4. `projectos_build_ontology`
5. Poll `projectos_get_task` until the ontology task is `completed`
6. `projectos_build_graph`
7. Poll `projectos_get_task` until the graph task is `completed`
8. `projectos_get_graph_health`

Do not synthesize a graph manually from attachment text. ProjectOS graph builds
must go through ontology extraction and graph build tasks.

The bridge writes logs to stderr only. stdout is reserved for newline-delimited
MCP JSON-RPC messages.
