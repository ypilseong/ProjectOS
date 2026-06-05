import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path

import networkx as nx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.config import config
from app.models.project import ProjectStatus, TaskStatus
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
            if "links" in data and "edges" not in data:
                data["edges"] = data.pop("links")
            graph = nx.node_link_graph(data)
            from app.utils.graph_normalization import normalize_graph_entity_types
            graph, _ = normalize_graph_entity_types(graph)
            data = nx.node_link_data(graph)
            nodes = data.get("nodes", [])
            links = data.get("links") or data.get("edges", [])

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
    project.status = ProjectStatus.ONTOLOGY
    project_store.save(project)
    task = task_manager.create(project_id, "ontology")
    asyncio.create_task(_run_ontology(task.task_id, project_id))
    return {"task_id": task.task_id}


@router.get("/{project_id}/ontology")
async def get_ontology(project_id: str):
    p = Path(config.PROJECTS_DIR) / project_id / "ontology.json"
    if not p.exists():
        raise HTTPException(404, "Ontology not built yet")
    data = json.loads(p.read_text(encoding="utf-8"))
    from app.models.graph import Ontology, EntityTypeDef, EdgeTypeDef
    from app.utils.graph_normalization import normalize_ontology_types
    ontology = Ontology(
        entity_types=[EntityTypeDef(**e) for e in data["entity_types"]],
        edge_types=[EdgeTypeDef(**e) for e in data["edge_types"]],
        analysis_summary=data["analysis_summary"],
    )
    return dataclasses.asdict(normalize_ontology_types(ontology))


@router.post("/{project_id}/graph")
async def run_graph(project_id: str):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    project.status = ProjectStatus.BUILDING
    project_store.save(project)
    task = task_manager.create(project_id, "graph")
    asyncio.create_task(_run_graph(task.task_id, project_id, incremental=False))
    return {"task_id": task.task_id}


@router.post("/{project_id}/graph/incremental")
async def run_graph_incremental(project_id: str):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    project.status = ProjectStatus.BUILDING
    project_store.save(project)
    task = task_manager.create(project_id, "graph_incremental")
    asyncio.create_task(_run_graph(task.task_id, project_id, incremental=True))
    return {"task_id": task.task_id}


@router.get("/{project_id}/graph")
async def get_graph(project_id: str):
    p = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    if not p.exists():
        raise HTTPException(404, "Graph not built yet")
    data = json.loads(p.read_text(encoding="utf-8"))
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    graph = nx.node_link_graph(data)
    from app.utils.graph_normalization import normalize_graph_entity_types
    from app.utils.graph_restructure import build_entity_details
    graph, _ = normalize_graph_entity_types(graph)
    graph, _ = build_entity_details(graph)
    normalized = nx.node_link_data(graph)
    if "edges" in normalized and "links" not in normalized:
        normalized["links"] = normalized.pop("edges")
    return normalized


@router.get("/{project_id}/graph/stats")
async def get_graph_stats(project_id: str):
    p = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    if not p.exists():
        raise HTTPException(404, "Graph not built yet")
    from app.agents.graph_builder_agent import GraphBuilderAgent
    data = json.loads(p.read_text(encoding="utf-8"))
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    graph = nx.node_link_graph(data)
    from app.utils.graph_normalization import normalize_graph_entity_types
    graph, _ = normalize_graph_entity_types(graph)
    agent = GraphBuilderAgent()
    stats = agent.get_stats(graph)
    return dataclasses.asdict(stats)


@router.get("/{project_id}/graph/health")
async def get_graph_health(project_id: str):
    from app.utils.graph_health import run_health_check
    proj_dir = Path(config.PROJECTS_DIR) / project_id
    graph_path = proj_dir / "graph.json"
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail="Graph not found")
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    graph = nx.node_link_graph(data)
    return run_health_check(graph, vault_path=str(Path(config.VAULT_DIR) / project_id))


@router.get("/{project_id}/traces")
async def get_traces(project_id: str):
    from app.utils.trace import read_traces

    return {"traces": read_traces(project_id)}


async def _run_ontology(task_id: str, project_id: str):
    from app.utils.logger import reset_log_project, set_log_project
    log_token = set_log_project(project_id)
    try:
        from app.agents.ontology_agent import OntologyAgent
        from app.models.graph import TextChunk

        task_manager.update(task_id, status=TaskStatus.RUNNING, message="온톨로지 분석 시작 (0/1)")
        chunks_path = Path(config.PROJECTS_DIR) / project_id / "chunks.json"
        if not chunks_path.exists():
            raise ValueError("chunks.json not found — upload files first")
        chunks_data = json.loads(chunks_path.read_text(encoding="utf-8"))
        chunks = [TextChunk(**c) for c in chunks_data]
        agent = OntologyAgent()
        task_manager.update(task_id, progress=30, message="LLM 온톨로지 생성 중... (1/1)")
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
        project = project_store.get(project_id)
        if project:
            project.status = ProjectStatus.FAILED
            project_store.save(project)
        task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))
    finally:
        reset_log_project(log_token)


async def _run_graph(task_id: str, project_id: str, incremental: bool, trigger: str = "manual"):
    from app.utils.logger import reset_log_project, set_log_project
    log_token = set_log_project(project_id)
    try:
        from app.agents.graph_builder_agent import GraphBuilderAgent
        from app.agents.obsidian_writer_agent import ObsidianWriterAgent
        from app.models.graph import EdgeTypeDef, EntityTypeDef, Ontology, TextChunk

        task_manager.update(task_id, status=TaskStatus.RUNNING, message="그래프 구축 시작", progress=10)
        from app.utils.llm_client import get_llm_usage
        from app.utils.trace import record_trace
        from app.utils.routing import Role, route

        usage_before = get_llm_usage().get("total_cost_usd", 0.0)
        proj_dir = Path(config.PROJECTS_DIR) / project_id
        chunks_data = json.loads((proj_dir / "chunks.json").read_text(encoding="utf-8"))
        chunks = [TextChunk(**c) for c in chunks_data]
        ont_data = json.loads((proj_dir / "ontology.json").read_text(encoding="utf-8"))
        ontology = Ontology(
            entity_types=[EntityTypeDef(**e) for e in ont_data["entity_types"]],
            edge_types=[EdgeTypeDef(**e) for e in ont_data["edge_types"]],
            analysis_summary=ont_data["analysis_summary"],
        )
        from app.utils.graph_normalization import normalize_graph_entity_types, normalize_ontology_types
        ontology = normalize_ontology_types(ontology)
        from app.agents.ontology_agent import OntologyAgent
        existing_edges = {edge.name for edge in ontology.edge_types}
        for edge_name in OntologyAgent.FIXED_EDGE_TYPES:
            if edge_name not in existing_edges:
                ontology.edge_types.append(
                    EdgeTypeDef(
                        name=edge_name,
                        description="fixed relation type",
                        source_types=[],
                        target_types=[],
                    )
                )
                existing_edges.add(edge_name)

        # --- Hash tracking ---
        from app.services.document_hash_store import DocumentHashStore
        proj_files_dir = proj_dir / "files"
        hash_store = DocumentHashStore(proj_dir)

        source_files = list({c.source_file for c in chunks})
        for fname in source_files:
            fpath = proj_files_dir / fname
            if fpath.exists():
                digest = hashlib.md5(fpath.read_bytes()).hexdigest()
                hash_store.update(fname, digest)

        ont_hash = hashlib.md5(json.dumps(ont_data, sort_keys=True).encode()).hexdigest()
        hash_store.update_ontology(ont_hash)

        if incremental:
            changed_files = set(hash_store.get_changed_files(source_files))
            original_count = len(chunks)
            chunks = [c for c in chunks if c.source_file in changed_files]
            skipped = original_count - len(chunks)
            if skipped:
                logger.info(f"Incremental: skipping {skipped} chunks from {len(source_files) - len(changed_files)} unchanged files")
                task_manager.update(task_id, message=f"증분 처리: {skipped}청크 스킵, {len(chunks)}청크 재처리", progress=25)
        # --- End hash tracking ---

        graph_path = str(proj_dir / "graph.json")
        if config.GRAPH_BUILD_MODE == "claude_task":
            from app.agents.claude_task_graph_builder_agent import ClaudeTaskGraphBuilderAgent
            graph_agent = ClaudeTaskGraphBuilderAgent()
        else:
            graph_agent = GraphBuilderAgent()
        total_chunks = len(chunks)
        task_manager.update(
            task_id,
            message=f"엔티티/관계 추출 중... (0/{total_chunks})",
            progress=30,
        )

        def on_chunk_progress(current: int, total: int):
            ratio = current / total if total else 1
            task_manager.update(
                task_id,
                message=f"엔티티/관계 추출 중... ({current}/{total})",
                progress=30 + int(ratio * 40),
            )

        if config.GRAPH_BUILD_MODE == "claude_task":
            file_paths = [
                proj_files_dir / source_file
                for source_file in sorted({chunk.source_file for chunk in chunks})
                if (proj_files_dir / source_file).exists()
            ]
            graph = await graph_agent.run(
                chunks,
                ontology,
                file_paths=file_paths,
                progress_callback=on_chunk_progress,
            )
        else:
            graph = await graph_agent.run(
                chunks,
                ontology,
                incremental=incremental,
                graph_path=graph_path,
                progress_callback=on_chunk_progress,
            )

        task_manager.update(task_id, message="의미 중복 노드 병합 중...", progress=71)
        from app.utils.semantic_dedup import merge_user_persons, semantic_dedup
        graph, normalized_count = normalize_graph_entity_types(graph)
        if normalized_count:
            logger.info(f"Entity type normalization: {normalized_count} node(s)")
        graph, user_merged = merge_user_persons(graph)
        if user_merged:
            logger.info(f"User person merge: {user_merged} node(s)")
        graph, merged_count = await semantic_dedup(graph)
        if merged_count:
            logger.info(f"Merged {merged_count} duplicate nodes")

        task_manager.update(task_id, message="LLM 중복 노드 검토 중...", progress=73)
        from app.utils.llm_dedup import llm_dedup
        graph, llm_merged = await llm_dedup(graph)
        if llm_merged:
            logger.info(f"LLM dedup: merged {llm_merged} node(s)")

        task_manager.update(task_id, message="엔티티 이름 정규화 중...", progress=74)
        from app.utils.entity_canonicalization import canonicalize_entity_names
        graph, canonicalized = await canonicalize_entity_names(graph)
        if canonicalized:
            logger.info(f"Entity canonicalization: changed {canonicalized} node(s)")

        task_manager.update(task_id, message="Achievement 노드 타입 검수 중...", progress=74)
        from app.utils.achievement_refinement import refine_achievement_nodes
        graph, achievement_refined = await refine_achievement_nodes(graph)
        if achievement_refined:
            logger.info(f"Achievement refinement: changed {achievement_refined} node(s)")

        from app.utils.isolated_reextract import reextract_isolated_nodes
        isolated_before = sum(1 for n in graph.nodes if graph.degree(n) == 0)
        if isolated_before:
            task_manager.update(
                task_id,
                message=f"고립 노드 재추출 중... (0/{isolated_before})",
                progress=72,
            )

            def on_reextract_progress(step: int, total: int, name: str):
                task_manager.update(
                    task_id,
                    message=f"고립 노드 재추출 중... ({step}/{total}) {name[:20]}",
                    progress=72 + int(step / total * 8),
                )

            graph, reconnected = await reextract_isolated_nodes(
                graph, chunks, graph_agent, ontology,
                progress_callback=on_reextract_progress,
            )
            logger.info(f"Isolated re-extraction: {reconnected}/{isolated_before} connected")

            task_manager.update(task_id, message="재추출 후 LLM 중복 노드 재검토 중...", progress=81)
            graph, post_reextract_llm_merged = await llm_dedup(graph)
            if post_reextract_llm_merged:
                logger.info(
                    "Post re-extraction LLM dedup: "
                    f"merged {post_reextract_llm_merged} node(s)"
                )

        from app.utils.graph_restructure import (
            add_category_hubs,
            build_entity_details,
            demote_project_context_nodes,
        )
        graph, context_demoted = demote_project_context_nodes(graph)
        if context_demoted:
            logger.info(f"Project context nodes demoted: {context_demoted}")
        graph, hubs_added = add_category_hubs(graph)
        if hubs_added:
            logger.info(f"Category hubs added: {hubs_added}")
        graph, details_added = build_entity_details(graph)
        if details_added:
            logger.info(f"Entity details generated: {details_added}")

        graph_agent.save(graph, graph_path)
        hash_store.save()

        try:
            from app.services.retrieval_index import build_node_index, build_chunk_index
            await build_node_index(project_id)
            await build_chunk_index(project_id)
        except Exception as e:
            logger.warning(f"retrieval index build skipped: {e}")

        total_nodes = graph.number_of_nodes()
        writable_nodes = sum(
            1 for _, data in graph.nodes(data=True) if data.get("type") != "Category"
        )
        task_manager.update(
            task_id,
            message=f"Obsidian vault 작성 중... (0/{writable_nodes})",
            progress=72,
        )
        writer = ObsidianWriterAgent()
        vault_path = str(Path(config.VAULT_DIR) / project_id)

        def on_vault_progress(current: int, total: int, name: str):
            ratio = current / total if total else 1
            task_manager.update(
                task_id,
                message=f"Obsidian vault 작성 중... ({current}/{total}) {name}",
                progress=72 + int(ratio * 25),
            )

        writer.run(
            graph,
            vault_path=vault_path,
            delta=incremental,
            project_id=project_id,
            progress_callback=on_vault_progress,
        )
        stats = graph_agent.get_stats(graph)
        project = project_store.get(project_id)
        if project:
            project.status = ProjectStatus.READY
            project.stats = dataclasses.asdict(stats)
            project_store.save(project)
        try:
            cost_delta = get_llm_usage().get("total_cost_usd", 0.0) - usage_before
            record_trace(
                project_id,
                "graph_build",
                backend=route(Role.CHUNK_EXTRACTION),
                incremental=incremental,
                nodes=stats.total_nodes,
                edges=stats.total_edges,
                cost_usd=round(cost_delta, 6),
                trigger=trigger,
            )
        except Exception:
            pass  # trace is best-effort; never fail a successful build on logging
        task_manager.update(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=f"완료: 노드 {stats.total_nodes}개, 엣지 {stats.total_edges}개",
        )
    except Exception as e:
        project = project_store.get(project_id)
        if project:
            project.status = ProjectStatus.FAILED
            project_store.save(project)
        task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))
    finally:
        reset_log_project(log_token)
