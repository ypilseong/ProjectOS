import json
from datetime import datetime, timezone

import networkx as nx

from app.models.graph import TextChunk
from app.utils.llm_client import LLMClient
from app.utils.routing import Role
from app.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_ANALYSIS_CHARS = 6000
_MAX_DRAFT_CHARS = 4000


class AnalysisAgent:
    def __init__(self):
        self._llm = LLMClient.for_role(Role.ANALYSIS)

    async def run(self, chunks: list[TextChunk], graph: nx.DiGraph | None = None) -> dict:
        if not chunks:
            raise ValueError("chunks must not be empty")
        full_text = "\n\n".join(c.text for c in chunks)
        graph_summary = self._graph_summary(graph)

        logger.info("AnalysisAgent: 약점 분석 시작")
        issues_result = await self._analyze_issues(full_text, graph_summary)

        logger.info("AnalysisAgent: 개선 초안 생성 시작")
        improved_draft = await self._generate_draft(full_text, issues_result.get("issues", []))

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": issues_result.get("summary", ""),
            "issues": issues_result.get("issues", []),
            "improved_draft": improved_draft,
        }

    def _graph_summary(self, graph: nx.DiGraph | None) -> str:
        if graph is None or graph.number_of_nodes() == 0:
            return "그래프 없음"
        type_counts: dict[str, int] = {}
        for _, data in graph.nodes(data=True):
            t = data.get("type", "Unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        parts = [f"{t}: {cnt}개" for t, cnt in type_counts.items()]
        return (
            f"총 {graph.number_of_nodes()}개 노드, "
            f"{graph.number_of_edges()}개 엣지. "
            + ", ".join(parts)
        )

    async def _analyze_issues(self, full_text: str, graph_summary: str) -> dict:
        if len(full_text) > _MAX_ANALYSIS_CHARS:
            logger.warning(
                f"Full text truncated from {len(full_text)} to {_MAX_ANALYSIS_CHARS} chars for analysis"
            )
        prompt = f"""다음 문서를 분석하여 약점과 개선 방향을 찾아주세요.

그래프 분석 요약: {graph_summary}

문서 내용:
{full_text[:_MAX_ANALYSIS_CHARS]}

JSON 형식으로 응답하세요 (한국어):
{{
  "summary": "전반적 평가 2~3문장",
  "issues": [
    {{
      "category": "카테고리명",
      "severity": "high|medium|low",
      "description": "구체적 문제 설명",
      "suggestion": "개선 제안"
    }}
  ]
}}"""
        try:
            return await self._llm.chat_json([{"role": "user", "content": prompt}])
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"AnalysisAgent: LLM JSON parse error: {e}")
            return {"summary": "", "issues": []}

    async def _generate_draft(self, full_text: str, issues: list[dict]) -> str:
        if len(full_text) > _MAX_DRAFT_CHARS:
            logger.warning(
                f"Full text truncated from {len(full_text)} to {_MAX_DRAFT_CHARS} chars for draft"
            )
        issues_text = "\n".join(
            f"- [{i.get('severity', 'medium')}] {i.get('category', '')}: {i.get('suggestion', '')}"
            for i in issues
        )
        prompt = f"""다음 원본 문서와 개선 제안을 바탕으로 개선된 문서 초안을 작성하세요.

개선 제안:
{issues_text}

원본 문서:
{full_text[:_MAX_DRAFT_CHARS]}

개선된 문서를 마크다운 형식으로 작성하세요. 원본 구조를 유지하되 제안된 개선사항을 반영하세요."""
        return await self._llm.chat([{"role": "user", "content": prompt}])
