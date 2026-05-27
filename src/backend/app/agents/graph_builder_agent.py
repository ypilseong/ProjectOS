import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

import networkx as nx

from app.config import config
from app.models.graph import GraphStats, Ontology, TextChunk
from app.utils.entity_validation import is_valid_entity
from app.utils.llm_client import LLMClient
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GraphBuilderAgent:
    def __init__(self):
        self._llm = LLMClient()
        self._fuzzy_threshold = config.FUZZY_MATCH_THRESHOLD
        self._user_context = self._load_user_context()

    @staticmethod
    def _load_user_context() -> str:
        """Build a prompt snippet from user.json (name + display_name)."""
        try:
            data = json.loads(Path(config.USER_CONFIG_PATH).read_text(encoding="utf-8"))
        except Exception:
            return ""
        names = [v.strip() for k in ("name", "display_name") if (v := data.get(k, ""))]
        if not names:
            return ""
        names_str = " / ".join(names)
        return (
            f"Document owner: {names_str}. "
            "When the subject of an item is not explicitly stated "
            "(e.g. bullet-list entries in a CV or resume), "
            f"treat {names_str} as the implicit subject and extract relations accordingly."
        )

    async def run(
        self,
        chunks: list[TextChunk],
        ontology: Ontology,
        incremental: bool = False,
        graph_path: str | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> nx.DiGraph:
        graph = nx.DiGraph()
        if incremental and graph_path and Path(graph_path).exists():
            data = json.loads(Path(graph_path).read_text())
            # normalize legacy 'links' key back to 'edges' for nx.node_link_graph compatibility
            if "links" in data and "edges" not in data:
                data["edges"] = data.pop("links")
            graph = nx.node_link_graph(data)
            logger.info(f"Loaded existing graph: {graph.number_of_nodes()} nodes")

        entity_types = [e.name for e in ontology.entity_types]
        edge_types = [e.name for e in ontology.edge_types]

        total = len(chunks)
        allowed_edge_set = set(edge_types)
        for i, chunk in enumerate(chunks, start=1):
            logger.info(f"Processing chunk {i}/{total}")
            try:
                result = await self._extract_from_chunk(chunk, entity_types, edge_types)
                self._merge_into_graph(graph, result, chunk, allowed_edge_set)
            except Exception as e:
                logger.error(f"Chunk {chunk.chunk_id} failed: {e}")
            if progress_callback:
                progress_callback(i, total)

        return graph

    async def _extract_from_chunk(
        self, chunk: TextChunk, entity_types: list[str], edge_types: list[str]
    ) -> dict:
        user_ctx = f"\n{self._user_context}\n" if self._user_context else ""
        prompt = f"""Extract entities and relations from the text below.
{user_ctx}
Allowed entity types: {', '.join(entity_types)}
Allowed relation types: {', '.join(edge_types)}

Extraction rules:
- Do not create entities for chunks, pages, sections, or raw text snippets.
- Extract important skills, technologies, tools, projects, organizations, publications, roles, events, institutions, and concrete achievements so the UI graph shows meaningful key items.
- Do not create Keyword or Concept entities. If a term looks like an important keyword, classify it using the most specific allowed type.
- Examples: "LLM", "NetworkX", "Vue", "D3.js" -> Skill or Technology.
- Examples: "ProjectOS", "MiroFish" -> Project.
- Examples: "그래프 시각화 기능 구현", "30% performance improvement" -> Achievement when the outcome is concrete.
- Avoid vague generic nouns, broad topics, isolated sentence fragments, and duplicate entities.
- Use Person only for real, identifiable human names explicitly present in the text.
- Do not create Person entities for pronouns, the author/user, anonymous people, role titles, departments, fields, or generic descriptions such as "I", "me", "저", "나", "author", "user", "student", "panelists", or "researcher".
- Role is ONLY for formal job titles or academic positions that could appear on a resume or business card. Examples: "Research Engineer", "PhD Student", "Professor", "Team Lead", "Software Engineer", "Undergraduate Researcher". Do NOT classify as Role: activity descriptions ("데이터 검수", "reviewing model evaluation frameworks"), participant labels ("발표자", "사회자", "패널", "moderator"), generic descriptions ("지역 주민", "기업", "약 1년간 근무"), or any phrase that is not a named position. If an item describes a concrete outcome or result → Achievement. If it describes participation in an event → Event. Vague or generic descriptions → do not extract at all.
- Entity type values and relation values must come from the allowed lists.
- Entity names may preserve the source language and can be Korean, English, or mixed Korean/English.

Text:
{chunk.text}

Return only valid JSON in this exact shape:
{{
  "entities": [
    {{"type": "Person", "name": "양필성", "description": "ML researcher"}}
  ],
  "relations": [
    {{"source": "양필성", "source_type": "Person",
      "target": "Python", "target_type": "Skill",
      "relation": "USES_SKILL", "confidence": 0.9}}
  ]
}}"""
        return await self._llm.chat_json([{"role": "user", "content": prompt}])

    def _merge_into_graph(
        self, graph: nx.DiGraph, result: dict, chunk: TextChunk, allowed_edge_set: set[str] | None = None
    ):
        node_map: dict[str, str] = {}

        for entity in result.get("entities", []):
            etype = entity.get("type", "").strip()
            name = entity.get("name", "").strip()
            if not is_valid_entity(etype, name):
                logger.info(f"Skipping invalid entity: {etype}:{name}")
                continue

            existing = self._find_existing_node(graph, etype, name)
            if existing:
                node_id = existing
                sources = set(graph.nodes[node_id].get("source_files", []))
                sources.add(chunk.source_file)
                graph.nodes[node_id]["source_files"] = list(sources)
            else:
                node_id = f"{etype}:{name}"
                graph.add_node(
                    node_id,
                    type=etype,
                    name=name,
                    description=entity.get("description", ""),
                    source_files=[chunk.source_file],
                    attributes={},
                )
            node_map[name] = node_id

        for rel in result.get("relations", []):
            src_name = rel.get("source", "")
            tgt_name = rel.get("target", "")
            relation = rel.get("relation", "")
            if not src_name or not tgt_name or not relation:
                continue
            if allowed_edge_set and relation not in allowed_edge_set:
                logger.info(f"Skipping invalid relation: {relation}")
                continue
            src_id = node_map.get(src_name)
            tgt_id = node_map.get(tgt_name)
            if src_id and tgt_id and src_id in graph and tgt_id in graph:
                graph.add_edge(
                    src_id,
                    tgt_id,
                    relation=relation,
                    confidence=rel.get("confidence", 1.0),
                    source_chunk_id=chunk.chunk_id,
                )

    def _find_existing_node(
        self, graph: nx.DiGraph, entity_type: str, name: str
    ) -> str | None:
        for node_id in graph.nodes:
            node = graph.nodes[node_id]
            if node.get("type") == entity_type:
                if self._fuzzy_match(node.get("name", ""), name):
                    return node_id
        return None

    def _fuzzy_match(self, a: str, b: str) -> bool:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= self._fuzzy_threshold

    async def reextract_with_context(
        self,
        context_text: str,
        source_file: str,
        graph: nx.DiGraph,
        entity_types: list[str],
        edge_types: list[str],
    ) -> int:
        """Re-extract relations from combined context text and add new edges to graph.

        Only adds edges between nodes that ALREADY exist in the graph.
        Never creates new nodes — this prevents the node explosion problem.
        Returns the number of new edges added.
        """
        from app.models.graph import TextChunk
        synthetic = TextChunk(
            chunk_id=f"reextract_{hash(context_text) & 0xFFFFFF:06x}",
            text=context_text,
            source_file=source_file,
            file_type="txt",
            page_num=None,
            char_offset=0,
        )
        edges_before = graph.number_of_edges()
        try:
            result = await self._extract_from_chunk(synthetic, entity_types, edge_types)
            self._merge_edges_only(graph, result, synthetic, set(edge_types))
        except Exception as e:
            logger.warning(f"reextract_with_context failed ({source_file}): {e}")
        return graph.number_of_edges() - edges_before

    def _merge_edges_only(
        self,
        graph: nx.DiGraph,
        result: dict,
        chunk: "TextChunk",
        allowed_edge_set: set[str] | None = None,
    ) -> None:
        """Add edges between existing nodes only — never creates new nodes."""
        node_map: dict[str, str] = {}
        for entity in result.get("entities", []):
            etype = entity.get("type", "").strip()
            name = entity.get("name", "").strip()
            existing = self._find_existing_node(graph, etype, name)
            if existing:
                node_map[name] = existing

        for rel in result.get("relations", []):
            src_name = rel.get("source", "")
            tgt_name = rel.get("target", "")
            relation = rel.get("relation", "")
            if not src_name or not tgt_name or not relation:
                continue
            if allowed_edge_set and relation not in allowed_edge_set:
                continue
            src_id = node_map.get(src_name)
            tgt_id = node_map.get(tgt_name)
            if src_id and tgt_id and not graph.has_edge(src_id, tgt_id):
                graph.add_edge(
                    src_id,
                    tgt_id,
                    relation=relation,
                    confidence=rel.get("confidence", 1.0),
                    source_chunk_id=chunk.chunk_id,
                )

    def save(self, graph: nx.DiGraph, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(graph)
        # NetworkX 3.x uses 'edges' key; normalize to 'links' for frontend compatibility
        if "edges" in data and "links" not in data:
            data["links"] = data.pop("edges")
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def get_stats(self, graph: nx.DiGraph) -> GraphStats:
        nodes_by_type: dict[str, int] = {}
        for n in graph.nodes:
            t = graph.nodes[n].get("type", "Unknown")
            nodes_by_type[t] = nodes_by_type.get(t, 0) + 1

        edges_by_type: dict[str, int] = {}
        for u, v, data in graph.edges(data=True):
            r = data.get("relation", "UNKNOWN")
            edges_by_type[r] = edges_by_type.get(r, 0) + 1

        return GraphStats(
            total_nodes=graph.number_of_nodes(),
            total_edges=graph.number_of_edges(),
            nodes_by_type=nodes_by_type,
            edges_by_type=edges_by_type,
        )
