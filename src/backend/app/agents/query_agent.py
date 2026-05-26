import networkx as nx

from app.models.graph import TextChunk
from app.utils.llm_client import LLMClient
from app.utils.logger import get_logger

logger = get_logger(__name__)


class QueryAgent:
    def __init__(self):
        self._llm = LLMClient()

    async def stream(
        self,
        question: str,
        graph: nx.DiGraph,
        chunks: list[TextChunk],
    ):
        """Async generator that yields LLM response tokens."""
        context = self._search_graph(graph, question)
        relevant_chunks = self._find_relevant_chunks(chunks, question)
        prompt = self._build_prompt(question, context, relevant_chunks)
        logger.info(f"QueryAgent: streaming answer for '{question[:50]}'")
        async for token in self._llm.stream([{"role": "user", "content": prompt}]):
            yield token

    def _search_graph(self, graph: nx.DiGraph, query: str) -> dict:
        query_words = set(query.lower().split()) if query.strip() else set()
        matched_nodes = []

        for node_id, data in graph.nodes(data=True):
            name = data.get("name", "").lower()
            desc = data.get("description", "").lower()
            if query_words and any(w in name or w in desc for w in query_words):
                matched_nodes.append({
                    "id": node_id,
                    "type": data.get("type"),
                    "name": data.get("name"),
                    "description": data.get("description"),
                })

        node_ids = {n["id"] for n in matched_nodes}
        connected_edges = []
        for u, v, data in graph.edges(data=True):
            if u in node_ids or v in node_ids:
                connected_edges.append({
                    "source": graph.nodes[u].get("name", u),
                    "target": graph.nodes[v].get("name", v),
                    "relation": data.get("relation", ""),
                })

        bfs_nodes = []
        for node_id in list(node_ids)[:3]:
            for neighbor in list(graph.successors(node_id)) + list(graph.predecessors(node_id)):
                if neighbor not in node_ids:
                    ndata = graph.nodes[neighbor]
                    bfs_nodes.append({
                        "type": ndata.get("type"),
                        "name": ndata.get("name"),
                    })

        return {"nodes": matched_nodes, "edges": connected_edges, "related": bfs_nodes}

    def _find_relevant_chunks(self, chunks: list[TextChunk], query: str) -> list[str]:
        if not query.strip():
            return []
        query_words = [w.lower() for w in query.split()]
        scored = []
        for chunk in chunks:
            text_lower = chunk.text.lower()
            score = sum(1 for w in query_words if w in text_lower)
            if score > 0:
                scored.append((score, chunk.text))
        scored.sort(reverse=True)
        return [text for _, text in scored[:3]]

    def _build_prompt(
        self, question: str, context: dict, chunks: list[str]
    ) -> str:
        nodes_str = "\n".join(
            f"- [{n['type']}] {n['name']}: {n['description'] or ''}"
            for n in context["nodes"]
        ) or "(관련 노드 없음)"

        edges_str = "\n".join(
            f"- {e['source']} --{e['relation']}--> {e['target']}"
            for e in context["edges"]
        ) or "(관련 관계 없음)"

        chunks_str = "\n\n".join(chunks) or "(관련 문서 없음)"

        return f"""다음 지식 그래프 컨텍스트와 원본 문서를 바탕으로 질문에 답하세요.

## 관련 노드
{nodes_str}

## 관련 관계
{edges_str}

## 원본 문서 발췌
{chunks_str}

## 질문
{question}

한국어로 상세히 답변하세요. 그래프의 관계를 활용하여 연결된 정보를 포함하세요."""
