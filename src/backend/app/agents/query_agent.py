from pathlib import Path

import networkx as nx

from app.models.graph import TextChunk
from app.agents.obsidian_writer_agent import TYPE_TO_FOLDER, _safe_filename
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
        vault_path: str | None = None,
    ):
        """Async generator that yields LLM response tokens."""
        context = self._search_graph(graph, question)
        relevant_chunks = self._find_relevant_chunks(chunks, question)
        wiki_context = self._load_wiki_context(vault_path, question, context)
        prompt = self._build_prompt(question, context, relevant_chunks, wiki_context)
        logger.info(f"QueryAgent: streaming answer for '{question[:50]}'")
        async for token in self._llm.stream([{"role": "user", "content": prompt}]):
            yield token

    def _search_graph(self, graph: nx.DiGraph, query: str) -> dict:
        query_lower = query.lower()
        query_tokens = [t for t in query_lower.split() if len(t) > 1]

        scored: list[tuple[float, dict]] = []
        for node_id, data in graph.nodes(data=True):
            name = data.get("name", "")
            desc = data.get("description", "") or ""
            name_lower = name.lower()
            desc_lower = desc.lower()

            name_score = sum(2.0 for t in query_tokens if t in name_lower)
            desc_score = sum(1.0 for t in query_tokens if t in desc_lower)
            total = name_score + desc_score
            if total > 0:
                scored.append((total, {
                    "id": node_id,
                    "type": data.get("type"),
                    "name": name,
                    "description": desc,
                }))

        scored.sort(key=lambda x: -x[0])
        matched_nodes = [item for _, item in scored[:10]]

        node_ids = {n["id"] for n in matched_nodes}
        connected_edges = []
        for u, v, edata in graph.edges(data=True):
            if u in node_ids or v in node_ids:
                connected_edges.append({
                    "source": graph.nodes[u].get("name", u),
                    "target": graph.nodes[v].get("name", v),
                    "relation": edata.get("relation", ""),
                })

        bfs_nodes = []
        seen_bfs = set(node_ids)
        for node_id in list(node_ids)[:3]:
            for neighbor in list(graph.successors(node_id)) + list(graph.predecessors(node_id)):
                if neighbor not in seen_bfs:
                    seen_bfs.add(neighbor)
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

    def _load_wiki_context(self, vault_path: str | None, query: str, context: dict) -> dict:
        if not vault_path:
            return {"index": "", "pages": []}

        vault = Path(vault_path)
        index_text = self._read_limited(vault / "_index.md", 4000)
        log_text = self._read_recent(vault / "log.md", 3000)
        pages = self._find_relevant_pages(vault, query, context)
        return {"index": index_text, "log": log_text, "pages": pages}

    def _find_relevant_pages(self, vault: Path, query: str, context: dict) -> list[dict]:
        query_lower = query.lower()
        query_tokens = [t for t in query_lower.split() if len(t) > 1]
        candidates: list[Path] = []

        for node in context.get("nodes", [])[:6]:
            page = self._node_page_path(vault, node)
            if page and page.exists():
                candidates.append(page)

        if not candidates:
            for page in vault.glob("*/*.md"):
                text_key = f"{page.stem} {page.parent.name}".lower()
                if any(t in text_key for t in query_tokens):
                    candidates.append(page)

        pages = []
        seen = set()
        for page in candidates:
            if page in seen:
                continue
            seen.add(page)
            content = self._read_limited(page, 2500)
            if content:
                pages.append({
                    "path": str(page.relative_to(vault)),
                    "content": content,
                })
            if len(pages) >= 3:
                break
        return pages

    def _node_page_path(self, vault: Path, node: dict) -> Path | None:
        ntype = node.get("type")
        name = node.get("name")
        if not ntype or not name:
            return None
        folder = TYPE_TO_FOLDER.get(ntype, "Misc")
        return vault / folder / f"{_safe_filename(name)}.md"

    @staticmethod
    def _read_limited(path: Path, limit: int) -> str:
        if not path.exists() or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")[:limit]

    @staticmethod
    def _read_recent(path: Path, limit: int) -> str:
        if not path.exists() or not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8")
        return text[-limit:]

    def _build_prompt(
        self, question: str, context: dict, chunks: list[str], wiki_context: dict | None = None
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
        wiki_context = wiki_context or {"index": "", "pages": []}
        wiki_index_str = wiki_context.get("index") or "(wiki index 없음)"
        wiki_log_str = wiki_context.get("log") or "(wiki log 없음)"
        wiki_pages = wiki_context.get("pages") or []
        wiki_pages_str = "\n\n".join(
            f"### {page['path']}\n{page['content']}"
            for page in wiki_pages
        ) or "(관련 wiki page 없음)"

        return f"""다음 wiki, 지식 그래프 컨텍스트와 원본 문서를 바탕으로 질문에 답하세요.

## Wiki Index
{wiki_index_str}

## 최근 Wiki Log
{wiki_log_str}

## 관련 Wiki Pages
{wiki_pages_str}

## 관련 노드
{nodes_str}

## 관련 관계
{edges_str}

## 원본 문서 발췌
{chunks_str}

## 질문
{question}

한국어로 상세히 답변하세요. 그래프의 관계를 활용하여 연결된 정보를 포함하세요.
가능하면 Wiki Pages의 Sources 섹션이나 원본 문서 발췌에 근거해 출처 파일/청크를 함께 언급하세요."""
