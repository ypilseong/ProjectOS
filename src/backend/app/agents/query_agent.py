from pathlib import Path
import re

import networkx as nx

from app.models.graph import TextChunk
from app.agents.obsidian_writer_agent import TYPE_TO_FOLDER, _safe_filename
from app.utils.llm_client import LLMClient
from app.utils.routing import Role
from app.utils.logger import get_logger
from app.utils.hybrid_retrieval import hybrid_search

logger = get_logger(__name__)


CITATION_LABEL_RE = re.compile(r"\[[^\[\]\n]+\]")


class QueryAgent:
    def __init__(self):
        self._llm = LLMClient.for_role(Role.QUERY)

    async def stream(
        self,
        question: str,
        graph: nx.DiGraph,
        chunks: list[TextChunk],
        vault_path: str | None = None,
    ):
        """Async generator that yields LLM response tokens."""
        project_id = Path(vault_path).name if vault_path else None
        context = await self._search_graph(graph, question, project_id=project_id)
        relevant_chunks = await self._find_relevant_chunks(
            chunks, question, project_id=project_id)
        wiki_context = self._load_wiki_context(vault_path, question, context)
        prompt = self._build_prompt(question, context, relevant_chunks, wiki_context)
        logger.info(f"QueryAgent: streaming answer for '{question[:50]}'")
        async for token in self._llm.stream([{"role": "user", "content": prompt}]):
            yield token

    async def _generate(self, prompt: str) -> str:
        """Non-streaming single-shot generation. Test seam for enforcement loop."""
        return await self._llm.chat([{"role": "user", "content": prompt}])

    async def answer_with_enforced_citations(
        self,
        question: str,
        graph: nx.DiGraph,
        chunks: list[TextChunk],
        vault_path: str | None = None,
        max_retries: int = 1,
    ) -> dict:
        """Generate an answer and regenerate on citation-validation failure.

        Builds context/allowed-labels once, then generates non-streaming. If the
        deterministic citation validator rejects the answer, re-prompts the model
        with the specific problems up to ``max_retries`` times. Returns the final
        answer with its citation report and the number of generation attempts.
        """
        from app.services.citation_validator import validate_citations

        project_id = Path(vault_path).name if vault_path else None
        context = await self._search_graph(graph, question, project_id=project_id)
        relevant_chunks = await self._find_relevant_chunks(
            chunks, question, project_id=project_id)
        wiki_context = self._load_wiki_context(vault_path, question, context)
        allowed_labels = self.collect_allowed_citation_labels(
            context, relevant_chunks, wiki_context)
        base_prompt = self._build_prompt(question, context, relevant_chunks, wiki_context)

        prompt = base_prompt
        answer = ""
        report: dict = {}
        attempts = 0
        max_attempts = max(1, max_retries + 1)
        while attempts < max_attempts:
            attempts += 1
            answer = await self._generate(prompt)
            report = validate_citations(answer, allowed_labels)
            if report["valid"] or attempts >= max_attempts:
                break
            prompt = self._build_citation_correction_prompt(
                base_prompt, answer, report, allowed_labels)

        return {
            "answer": answer,
            "citation_report": report,
            "allowed_citation_labels": allowed_labels,
            "attempts": attempts,
        }

    def _build_citation_correction_prompt(
        self,
        base_prompt: str,
        previous_answer: str,
        report: dict,
        allowed_labels: list[str],
    ) -> str:
        problems: list[str] = []
        unknown = report.get("unknown_labels") or []
        if unknown:
            problems.append(
                "- 제공되지 않은 출처 라벨을 사용했습니다: "
                + ", ".join(unknown)
                + '. 이 라벨을 제거하고 허용된 라벨로 교체하거나 "출처 불명"으로 표시하세요.'
            )
        missing = report.get("missing_citation_sentences") or []
        if missing:
            problems.append(
                '- 다음 문장에는 출처 인용이 없습니다. 허용된 라벨을 붙이거나 "출처 불명"으로 표시하세요:\n'
                + "\n".join(f"  · {sentence}" for sentence in missing[:5])
            )
        problems_str = "\n".join(problems) or "- citation 규칙을 다시 확인하세요."
        allowed_str = ", ".join(allowed_labels) or "(없음)"
        return f"""{base_prompt}

## 이전 답변 (citation 규칙 위반)
{previous_answer}

## 수정 지시
이전 답변은 citation 규칙을 위반했습니다. 아래 문제를 모두 고쳐 답변을 다시 작성하세요.
{problems_str}

허용된 출처 라벨: {allowed_str}
허용된 라벨만 사용하고, 근거가 없으면 "출처 불명"으로 표시하세요."""

    async def _search_graph(self, graph: nx.DiGraph, query: str, project_id=None) -> dict:
        if not query.strip():
            return {"nodes": [], "edges": [], "related": []}
        items = {
            node_id: f"{data.get('name', '')} {data.get('name', '')} "
                     f"{data.get('description', '') or ''}"
            for node_id, data in graph.nodes(data=True)
        }
        ranked_ids = await hybrid_search(
            query, project_id, "nodes", items, top_n=10)
        matched_nodes = [
            {
                "id": node_id,
                "type": graph.nodes[node_id].get("type"),
                "name": graph.nodes[node_id].get("name", ""),
                "description": graph.nodes[node_id].get("description", "") or "",
                "source_files": graph.nodes[node_id].get("source_files", []) or [],
            }
            for node_id in ranked_ids if node_id in graph
        ]

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
                        "source_files": ndata.get("source_files", []) or [],
                    })

        return {"nodes": matched_nodes, "edges": connected_edges, "related": bfs_nodes}

    async def _find_relevant_chunks(self, chunks: list[TextChunk], query: str, project_id=None) -> list[str]:
        if not query.strip():
            return []
        items = {c.chunk_id: c.text for c in chunks}
        ranked_ids = await hybrid_search(
            query, project_id, "chunks", items, top_n=3)
        chunk_by_id = {c.chunk_id: c for c in chunks}
        return [
            f"{self._chunk_source_label(chunk_by_id[cid])}\n{chunk_by_id[cid].text}"
            for cid in ranked_ids if cid in chunk_by_id
        ]

    @staticmethod
    def _chunk_source_label(chunk: TextChunk) -> str:
        source_file = chunk.source_file or "unknown"
        parts = [f"{source_file}#{chunk.chunk_id}"]
        if chunk.page_num is not None:
            parts.append(f"p.{chunk.page_num}")
        if chunk.char_offset is not None:
            parts.append(f"char:{chunk.char_offset}")
        return f"[{' '.join(parts)}]"

    def collect_allowed_citation_labels(
        self,
        context: dict,
        chunks: list[str],
        wiki_context: dict | None = None,
    ) -> list[str]:
        labels: set[str] = set()
        for node in context.get("nodes", []) + context.get("related", []):
            labels.update(self._node_source_labels(node))
        for chunk in chunks:
            labels.update(CITATION_LABEL_RE.findall(chunk))
        wiki_context = wiki_context or {}
        labels.update(CITATION_LABEL_RE.findall(wiki_context.get("index") or ""))
        labels.update(CITATION_LABEL_RE.findall(wiki_context.get("log") or ""))
        for page in wiki_context.get("pages") or []:
            content = page.get("content") or ""
            labels.update(CITATION_LABEL_RE.findall(content))
            labels.update(self._wiki_source_labels(content))
        labels.discard("[출처 불명]")
        return sorted(labels)

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
            f"- [{n['type']}] {n['name']} {self._node_source_label(n)}: "
            f"{n['description'] or ''}"
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
모든 사실 주장에는 제공된 출처 라벨을 인용하세요. 원본 문서 발췌는 대괄호 라벨(예: [file#chunk p.1 char:0])을 그대로 사용하고, 관련 노드는 노드에 표시된 source_files 라벨을 사용하세요.
Wiki Pages의 Sources 섹션에만 근거가 있으면 해당 source 파일명을 인용하세요.
제공된 컨텍스트로 뒷받침되지 않는 내용은 추측하지 말고 "출처 불명"이라고 명시하세요."""

    @staticmethod
    def _node_source_label(node: dict) -> str:
        labels = QueryAgent._node_source_labels(node)
        if not labels:
            return "[출처 불명]"
        return ", ".join(labels)

    @staticmethod
    def _node_source_labels(node: dict) -> list[str]:
        source_files = node.get("source_files") or []
        if isinstance(source_files, str):
            source_files = [source_files]
        return sorted(f"[{source}]" for source in source_files if source)

    @staticmethod
    def _wiki_source_labels(content: str) -> list[str]:
        labels: set[str] = set()
        in_sources = False
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if line.startswith("#"):
                in_sources = "source" in line.lower() or "출처" in line
                continue
            if not in_sources or not line:
                continue
            if line.startswith(("-", "*")):
                value = line.lstrip("-* ").strip()
                value = value.split(":", 1)[-1].strip() if ":" in value else value
                if value and not value.startswith("["):
                    labels.add(f"[{value}]")
        return sorted(labels)
