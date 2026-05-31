import json
from pathlib import Path

import networkx as nx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.config import config
from app.models.graph import TextChunk

router = APIRouter()


@router.post("/{project_id}/chat")
async def chat(project_id: str, body: dict):
    question = body.get("question", "").strip()
    if not question:
        raise HTTPException(400, "question is required")

    proj_dir = Path(config.PROJECTS_DIR) / project_id
    graph_path = proj_dir / "graph.json"
    chunks_path = proj_dir / "chunks.json"

    if not graph_path.exists():
        raise HTTPException(404, "Graph not built yet — run graph build first")

    graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
    graph = nx.node_link_graph(graph_data)

    chunks: list[TextChunk] = []
    if chunks_path.exists():
        chunks_data = json.loads(chunks_path.read_text(encoding="utf-8"))
        chunks = [TextChunk(**c) for c in chunks_data]

    from app.agents.query_agent import QueryAgent
    agent = QueryAgent()

    async def generate():
        vault_path = str(Path(config.VAULT_DIR) / project_id)
        async for token in agent.stream(question, graph, chunks, vault_path=vault_path):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
