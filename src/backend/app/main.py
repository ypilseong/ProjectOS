from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import projects, graph, chat, tasks

app = FastAPI(title="ProjectOS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(graph.router, prefix="/api/projects", tags=["graph"])
app.include_router(graph.global_router, prefix="/api/graph", tags=["graph"])
app.include_router(chat.router, prefix="/api/projects", tags=["chat"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])


@app.get("/health")
async def health():
    return {"status": "ok"}
