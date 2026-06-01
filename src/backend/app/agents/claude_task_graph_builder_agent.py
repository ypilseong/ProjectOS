from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import networkx as nx

from app.agents.graph_builder_agent import GraphBuilderAgent
from app.models.graph import Ontology, TextChunk
from app.utils.claude_task_runner import ClaudeTaskRunner
from app.utils.entity_validation import normalize_entity_type
from app.utils.logger import get_logger

logger = get_logger(__name__)


GRAPH_EXTRACTION_TASK_CLAUDE_MD = """# ProjectOS Isolated Graph Extraction Task

You are extracting a profile knowledge graph for ProjectOS.

Isolation rules:
- This task is independent from any repository CLAUDE.md.
- Read only ./input.json, ./schema.json, and the file paths explicitly listed in input.json.
- Do not inspect unrelated files.
- Do not modify files.

Extraction rules:
- Return JSON only. No markdown, no explanation.
- Do not invent facts. Every entity and relation must be grounded in listed source files.
- Use English canonical names for general concepts, methods, skills, and roles.
- Preserve proper nouns and official names.
- Preserve source-language names when an official English name is uncertain.
- Use Achievement only for GPA/grades, honors, awards, scholarships, competition placements, accepted publications, or formally measured academic/professional results.
- Certificates and exam names should be Skill when useful, not Achievement.
- Avoid chunks, pages, sections, vague topics, raw snippets, duplicate entities, and generic nouns.
- Prefer expanded labels over acronyms when both appear.
- Keep graph nodes to independent primary entities. Do not create entities for project features, outputs, or implementation phrases such as "graph JSON generation", "Obsidian export", "user-centered visualization", "FastAPI backend architecture", or "Vue/D3 frontend implementation".
- When such a phrase contains a real skill/tool, extract only the skill/tool as a Skill and connect the Project to it with USES_SKILL.

Allowed entity types and relation types are provided in input.json.
Output must match schema.json.
"""


GRAPH_EXTRACTION_SCHEMA = {
    "type": "object",
    "required": ["entities", "relations"],
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["type", "name"],
                "properties": {
                    "type": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "evidence": {"type": "array"},
                },
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["source", "source_type", "target", "target_type", "relation"],
                "properties": {
                    "source": {"type": "string"},
                    "source_type": {"type": "string"},
                    "target": {"type": "string"},
                    "target_type": {"type": "string"},
                    "relation": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "array"},
                },
            },
        },
    },
}


class ClaudeTaskGraphBuilderAgent:
    """Graph extraction strategy for environments without a local LLM."""

    def __init__(self, runner: ClaudeTaskRunner | None = None):
        self._runner = runner or ClaudeTaskRunner()
        self._graph_builder = GraphBuilderAgent()

    async def run(
        self,
        chunks: list[TextChunk],
        ontology: Ontology,
        file_paths: list[str | Path],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> nx.DiGraph:
        entity_types = []
        for entity in ontology.entity_types:
            normalized = normalize_entity_type(entity.name)
            if normalized not in entity_types:
                entity_types.append(normalized)
        edge_types = [edge.name for edge in ontology.edge_types]

        input_data = {
            "task": "extract_profile_graph",
            "source_files": [str(Path(path).resolve()) for path in file_paths],
            "allowed_entity_types": entity_types,
            "allowed_relation_types": edge_types,
            "document_chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "source_file": chunk.source_file,
                    "file_type": chunk.file_type,
                    "text_preview": chunk.text[:1200],
                }
                for chunk in chunks[:20]
            ],
        }
        prompt = (
            "Read input.json. Inspect the source_files listed there as needed. "
            "Extract entities and relations for a profile knowledge graph. "
            "Return JSON only with top-level entities and relations arrays."
        )
        result = await self._runner.run_task(
            "graph-extraction",
            GRAPH_EXTRACTION_TASK_CLAUDE_MD,
            input_data,
            GRAPH_EXTRACTION_SCHEMA,
            allowed_paths=file_paths,
            prompt=prompt,
        )

        graph = nx.DiGraph()
        source_file = ",".join(sorted({chunk.source_file for chunk in chunks})) or "claude_task"
        synthetic_chunk = TextChunk(
            chunk_id="claude_task_graph_extraction",
            text=json.dumps(result, ensure_ascii=False)[:4000],
            source_file=source_file,
            file_type="claude_task",
            page_num=None,
            char_offset=0,
        )
        await self._graph_builder._merge_into_graph(
            graph,
            result,
            synthetic_chunk,
            allowed_edge_set=set(edge_types),
        )
        if progress_callback:
            progress_callback(1, 1)
        logger.info(
            "Claude task graph extraction: "
            f"{graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges"
        )
        return graph

    def save(self, graph: nx.DiGraph, path: str):
        return self._graph_builder.save(graph, path)

    def get_stats(self, graph: nx.DiGraph):
        return self._graph_builder.get_stats(graph)

    async def reextract_with_context(
        self,
        context_text: str,
        source_file: str,
        graph: nx.DiGraph,
        entity_types: list[str],
        edge_types: list[str],
    ) -> int:
        return await self._graph_builder.reextract_with_context(
            context_text,
            source_file,
            graph,
            entity_types,
            edge_types,
        )
