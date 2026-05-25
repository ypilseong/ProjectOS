import json
from difflib import SequenceMatcher
from pathlib import Path

import networkx as nx

from app.config import config
from app.models.graph import GraphStats, Ontology, TextChunk
from app.utils.llm_client import LLMClient
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GraphBuilderAgent:
    def __init__(self):
        self._llm = LLMClient()
        self._fuzzy_threshold = config.FUZZY_MATCH_THRESHOLD

    async def run(
        self,
        chunks: list[TextChunk],
        ontology: Ontology,
        incremental: bool = False,
        graph_path: str | None = None,
    ) -> nx.DiGraph:
        graph = nx.DiGraph()
        if incremental and graph_path and Path(graph_path).exists():
            data = json.loads(Path(graph_path).read_text())
            graph = nx.node_link_graph(data)
            logger.info(f"Loaded existing graph: {graph.number_of_nodes()} nodes")

        entity_types = [e.name for e in ontology.entity_types]
        edge_types = [e.name for e in ontology.edge_types]

        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i + 1}/{len(chunks)}")
            try:
                result = await self._extract_from_chunk(chunk, entity_types, edge_types)
                self._merge_into_graph(graph, result, chunk)
            except Exception as e:
                logger.error(f"Chunk {chunk.chunk_id} failed: {e}")

        return graph

    async def _extract_from_chunk(
        self, chunk: TextChunk, entity_types: list[str], edge_types: list[str]
    ) -> dict:
        prompt = f"""다음 텍스트에서 엔티티와 관계를 추출하세요.

엔티티 타입: {', '.join(entity_types)}
관계 타입: {', '.join(edge_types)}

텍스트:
{chunk.text}

JSON 형식으로 응답:
{{
  "entities": [
    {{"type": "Person", "name": "이름", "description": "설명"}}
  ],
  "relations": [
    {{"source": "이름", "source_type": "Person",
      "target": "대상", "target_type": "Skill",
      "relation": "USES_SKILL", "confidence": 0.9}}
  ]
}}"""
        return await self._llm.chat_json([{"role": "user", "content": prompt}])

    def _merge_into_graph(self, graph: nx.DiGraph, result: dict, chunk: TextChunk):
        node_map: dict[str, str] = {}

        for entity in result.get("entities", []):
            etype = entity.get("type", "").strip()
            name = entity.get("name", "").strip()
            if not etype or not name:
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

    def save(self, graph: nx.DiGraph, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(graph)
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
