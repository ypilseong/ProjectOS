from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import projects, graph, chat, tasks, user, settings, skills, digest, mcp, google
from app.services.watcher import WatcherService
from app.services.digest import DigestService
from app.services.google_connector import GoogleSyncService
from app.utils.logger import configure_logging

configure_logging()

_watcher = WatcherService()
_digest = DigestService()
_google_sync = GoogleSyncService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _watcher.start()
    _digest.start()
    _google_sync.start()
    try:
        yield
    finally:
        await _watcher.stop()
        await _digest.stop()
        await _google_sync.stop()


app = FastAPI(title="ProjectOS", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "app://obsidian.md",
        "capacitor://localhost",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user.router, prefix="/api/user", tags=["user"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(graph.router, prefix="/api/projects", tags=["graph"])
app.include_router(graph.global_router, prefix="/api/graph", tags=["graph"])
app.include_router(chat.router, prefix="/api/projects", tags=["chat"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
app.include_router(digest.router, prefix="/api/projects", tags=["digest"])
app.include_router(google.router, prefix="/api/google", tags=["google"])
app.include_router(mcp.router, prefix="/mcp", tags=["mcp"])


@app.get("/health")
async def health():
    return {"status": "ok"}
