# ProjectOS

ProjectOS turns personal project files, resumes, and notes into a visual career knowledge graph. The backend parses uploaded documents, extracts typed entities and relations with an OpenAI-compatible LLM endpoint, writes project-specific logs, and exports an Obsidian-style vault. The frontend provides project management, graph visualization, progress tracking, and vault browsing.

## Stack

- Backend: FastAPI, NetworkX, OpenAI-compatible LLM API, pytest
- Frontend: Vue 3, Vite, Element Plus, D3
- Outputs: graph JSON, project logs, Obsidian markdown vault

## Local Run

Backend:

```bash
cd src/backend
python3 -m pip install -e '.[dev]'
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Frontend:

```bash
cd src/frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5174
```

Open `http://localhost:5174`.

## Configuration

Copy `.env.example` and configure the backend environment as needed. `LLM_API_KEY` may be empty for local OpenAI-compatible servers that do not require an API key. `LLM_BASE_URL` and `LLM_MODEL` select the LLM endpoint/model.

Project-specific runtime logs are written under:

```text
logs/projects/{project_id}/projectos.log
logs/projects/{project_id}/tasks.log
```

## MCP for Claude Desktop

ProjectOS exposes its project memory as MCP tools through the backend `/mcp`
endpoint. Claude Desktop local MCP configs should launch the stdio bridge:

```json
{
  "mcpServers": {
    "projectos": {
      "command": "python3",
      "args": ["src/backend/projectos_mcp_stdio.py"],
      "env": {
        "PROJECTOS_MCP_URL": "http://127.0.0.1:8003/mcp"
      }
    }
  }
}
```

Available tools include project creation/listing, file upload, graph health
checks, career graph queries, digest generation/reading, vault note reading, and
trace reading. See `docs/claude-desktop-mcp.md` for the full setup.

## Tests

```bash
cd src/backend
python3 -m pytest tests/ -q

cd src/frontend
npm run build
```
