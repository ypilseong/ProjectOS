import asyncio
import dataclasses
import json
from pathlib import Path

import networkx as nx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.config import config
from app.models.project import TaskStatus
from app.services.project_store import project_store
from app.services.task_manager import task_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

global_router = APIRouter()

PROJECT_COLORS = [
    "#4A90D9", "#5BA85B", "#E8A838", "#9B59B6", "#E74C3C",
    "#1ABC9C", "#E67E22", "#27AE60", "#2980B9", "#8E44AD",
]


@global_router.get("/global")
async def get_global_graph():
    base = Path(config.PROJECTS_DIR)
    if not base.exists():
        return {"nodes": [], "links": [], "projects": []}

    all_nodes: list[dict] = []
    all_links: list[dict] = []
    projects_meta: list[dict] = []
    color_idx = 0

    for proj_dir in sorted(d for d in base.iterdir() if d.is_dir()):
        graph_path = proj_dir / "graph.json"
        meta_path = proj_dir / "meta.json"
        if not graph_path.exists() or not meta_path.exists():
            continue

        project_id = proj_dir.name
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            project_name = meta.get("name", project_id)
            color = PROJECT_COLORS[color_idx % len(PROJECT_COLORS)]
            color_idx += 1

            projects_meta.append({"id": project_id, "name": project_name, "color": color})

            data = json.loads(graph_path.read_text(encoding="utf-8"))
            nodes = data.get("nodes", [])
            links = data.get("links", [])

            id_map: dict[str, str] = {}
            for node in nodes:
                orig_id = node["id"]
                new_id = f"{project_id}::{orig_id}"
                id_map[orig_id] = new_id
                all_nodes.append({**node, "id": new_id, "project_id": project_id, "project_name": project_name})

            for lnk in links:
                src = lnk.get("source")
                tgt = lnk.get("target")
                if isinstance(src, dict):
                    src = src["id"]
                if isinstance(tgt, dict):
                    tgt = tgt["id"]
                all_links.append({
                    **lnk,
                    "source": id_map.get(src, f"{project_id}::{src}"),
                    "target": id_map.get(tgt, f"{project_id}::{tgt}"),
                })
        except Exception as e:
            logger.warning(f"Skipping project {project_id}: {e}")
            continue

    return {"nodes": all_nodes, "links": all_links, "projects": projects_meta}


@router.post("/{project_id}/ontology")
async def run_ontology(project_id: str):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    task = task_manager.create(project_id, "ontology")
    asyncio.create_task(_run_ontology(task.task_id, project_id))
    return {"task_id": task.task_id}


@router.get("/{project_id}/ontology")
async def get_ontology(project_id: str):
    p = Path(config.PROJECTS_DIR) / project_id / "ontology.json"
    if not p.exists():
        raise HTTPException(404, "Ontology not built yet")
    return json.loads(p.read_text(encoding="utf-8"))


@router.post("/{project_id}/graph")
async def run_graph(project_id: str):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    task = task_manager.create(project_id, "graph")
    asyncio.create_task(_run_graph(task.task_id, project_id, incremental=False))
    return {"task_id": task.task_id}


@router.post("/{project_id}/graph/incremental")
async def run_graph_incremental(project_id: str):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    task = task_manager.create(project_id, "graph_incremental")
    asyncio.create_task(_run_graph(task.task_id, project_id, incremental=True))
    return {"task_id": task.task_id}


@router.get("/{project_id}/graph")
async def get_graph(project_id: str):
    p = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    if not p.exists():
        raise HTTPException(404, "Graph not built yet")
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/{project_id}/graph/stats")
async def get_graph_stats(project_id: str):
    p = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    if not p.exists():
        raise HTTPException(404, "Graph not built yet")
    from app.agents.graph_builder_agent import GraphBuilderAgent
    data = json.loads(p.read_text(encoding="utf-8"))
    graph = nx.node_link_graph(data)
    agent = GraphBuilderAgent()
    stats = agent.get_stats(graph)
    return dataclasses.asdict(stats)


@router.get("/{project_id}/profiles")
async def get_profiles(project_id: str):
    p = Path(config.PROJECTS_DIR) / project_id / "profiles.json"
    if not p.exists():
        raise HTTPException(404, "Profiles not built yet")
    return json.loads(p.read_text(encoding="utf-8"))


async def _run_ontology(task_id: str, project_id: str):
    from app.agents.ontology_agent import OntologyAgent
    from app.models.graph import TextChunk
    try:
        task_manager.update(task_id, status=TaskStatus.RUNNING, message="온톨로지 분석 시작")
        chunks_path = Path(config.PROJECTS_DIR) / project_id / "chunks.json"
        if not chunks_path.exists():
            raise ValueError("chunks.json not found — upload files first")
        chunks_data = json.loads(chunks_path.read_text(encoding="utf-8"))
        chunks = [TextChunk(**c) for c in chunks_data]
        agent = OntologyAgent()
        task_manager.update(task_id, progress=30, message="LLM 온톨로지 생성 중...")
        ontology = await agent.run(chunks)
        out = Path(config.PROJECTS_DIR) / project_id / "ontology.json"
        out.write_text(
            json.dumps(dataclasses.asdict(ontology), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        task_manager.update(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=f"{len(ontology.entity_types)}개 엔티티 타입 생성 완료",
        )
    except Exception as e:
        task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))


async def _run_graph(task_id: str, project_id: str, incremental: bool):
    from app.agents.graph_builder_agent import GraphBuilderAgent
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent
    from app.agents.profile_agent import ProfileAgent
    from app.models.graph import EdgeTypeDef, EntityTypeDef, Ontology, TextChunk
    try:
        task_manager.update(task_id, status=TaskStatus.RUNNING, message="그래프 구축 시작", progress=10)
        proj_dir = Path(config.PROJECTS_DIR) / project_id
        chunks_data = json.loads((proj_dir / "chunks.json").read_text(encoding="utf-8"))
        chunks = [TextChunk(**c) for c in chunks_data]
        ont_data = json.loads((proj_dir / "ontology.json").read_text(encoding="utf-8"))
        ontology = Ontology(
            entity_types=[EntityTypeDef(**e) for e in ont_data["entity_types"]],
            edge_types=[EdgeTypeDef(**e) for e in ont_data["edge_types"]],
            analysis_summary=ont_data["analysis_summary"],
        )
        graph_path = str(proj_dir / "graph.json")
        graph_agent = GraphBuilderAgent()
        task_manager.update(task_id, message="엔티티/관계 추출 중...", progress=30)
        graph = await graph_agent.run(
            chunks, ontology, incremental=incremental, graph_path=graph_path
        )
        graph_agent.save(graph, graph_path)
        task_manager.update(task_id, message="프로필 생성 중...", progress=70)
        profile_agent = ProfileAgent()
        profiles = await profile_agent.run(graph)
        profiles_data = [dataclasses.asdict(p) for p in profiles]
        (proj_dir / "profiles.json").write_text(
            json.dumps(profiles_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        task_manager.update(task_id, message="Obsidian vault 작성 중...", progress=85)
        writer = ObsidianWriterAgent()
        writer.run(graph, profiles, vault_path=config.VAULT_DIR, delta=incremental)
        stats = graph_agent.get_stats(graph)
        task_manager.update(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=f"완료: 노드 {stats.total_nodes}개, 엣지 {stats.total_edges}개",
        )
    except Exception as e:
        task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))
