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
- `projectos_list_projects`
- `projectos_get_graph_health`
- `projectos_query_career_graph`
- `projectos_generate_digest`
- `projectos_list_digests`
- `projectos_get_digest`
- `projectos_get_vault_note`
- `projectos_read_traces`

The bridge writes logs to stderr only. stdout is reserved for newline-delimited
MCP JSON-RPC messages.
