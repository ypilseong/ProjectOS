from app.models.graph import TextChunk, Ontology, EntityTypeDef, EdgeTypeDef
from app.utils.llm_client import LLMClient
from app.config import config
from app.utils.logger import get_logger

logger = get_logger(__name__)


class OntologyAgent:
    FIXED_ENTITY_TYPES = [
        "Person", "Project", "Skill", "Organization", "Publication",
        "Technology", "Role", "Achievement", "Event", "Institution",
    ]
    FIXED_EDGE_TYPES = [
        "WORKED_AT", "DEVELOPED", "USES_SKILL", "AUTHORED",
        "COLLABORATED_WITH", "ACHIEVED", "PARTICIPATED_IN",
        "PUBLISHED_AT", "MENTORED_BY", "LED_BY",
    ]

    def __init__(self):
        self._llm = LLMClient()

    async def run(self, chunks: list[TextChunk]) -> Ontology:
        sample = self._build_sample(chunks)
        logger.info(f"OntologyAgent: analysing {len(sample)} chars from {len(chunks)} chunks")
        prompt = self._build_prompt(sample)
        result = await self._llm.chat_json([{"role": "user", "content": prompt}])
        return self._parse_result(result)

    def _build_sample(self, chunks: list[TextChunk]) -> str:
        combined = "\n\n".join(c.text for c in chunks)
        return combined[:config.MAX_ONTOLOGY_SAMPLE_CHARS]

    def _build_prompt(self, sample: str) -> str:
        fixed_entities = ", ".join(self.FIXED_ENTITY_TYPES)
        fixed_edges = ", ".join(self.FIXED_EDGE_TYPES)
        return f"""다음 문서를 분석하여 커리어/프로젝트 지식 그래프를 위한 온톨로지를 정의하세요.

고정 엔티티 타입 (반드시 포함): {fixed_entities}
고정 관계 타입 (반드시 포함): {fixed_edges}

문서 내용:
{sample}

다음 JSON 형식으로 응답하세요:
{{
  "entity_types": [
    {{"name": "Person", "description": "개인/사람 엔티티", "examples": ["양필성", "김철수"]}}
  ],
  "edge_types": [
    {{"name": "WORKED_AT", "description": "근무 관계", "source_types": ["Person"], "target_types": ["Organization"]}}
  ],
  "analysis_summary": "문서 요약 및 도메인 특성 설명"
}}"""

    def _parse_result(self, result: dict) -> Ontology:
        entity_types = [
            EntityTypeDef(
                name=e["name"],
                description=e.get("description", ""),
                examples=e.get("examples", []),
            )
            for e in result.get("entity_types", [])
        ]
        edge_types = [
            EdgeTypeDef(
                name=e["name"],
                description=e.get("description", ""),
                source_types=e.get("source_types", []),
                target_types=e.get("target_types", []),
            )
            for e in result.get("edge_types", [])
        ]
        return Ontology(
            entity_types=entity_types,
            edge_types=edge_types,
            analysis_summary=result.get("analysis_summary", ""),
        )
