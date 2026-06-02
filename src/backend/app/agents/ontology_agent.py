from app.models.graph import TextChunk, Ontology, EntityTypeDef, EdgeTypeDef
from app.config import config
from app.utils.llm_client import LLMClient
from app.utils.routing import Role
from app.utils.logger import get_logger

logger = get_logger(__name__)


class OntologyAgent:
    FIXED_ENTITY_TYPES = [
        "Person", "Project", "Skill", "Organization", "Publication",
        "Role", "Achievement", "Event", "Institution",
    ]
    FIXED_EDGE_TYPES = [
        "WORKED_AT", "DEVELOPED", "USES_SKILL", "AUTHORED",
        "COLLABORATED_WITH", "ACHIEVED", "PARTICIPATED_IN",
        "PUBLISHED_AT", "MENTORED_BY", "LED_BY", "HAS_ROLE",
    ]

    def __init__(self):
        self._llm = LLMClient.for_role(Role.ONTOLOGY)

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
        return f"""You are designing an ontology for a career/project knowledge graph.

Allowed entity types (use ONLY these, do not add any others): {fixed_entities}
Allowed relation types (use ONLY these, do not add any others): {fixed_edges}

Entity type rules:
- Return exactly the entity types and relation types listed above — no additions, no substitutions.
- Do not introduce Topic, Concept, Keyword, Location, or any other unlisted types.
- If an item looks like an important keyword, classify it using the most specific existing type.
- Skill includes programming languages, frameworks, methods, tools, technical keywords, and platform/model names. Do not create a separate Technology type.
- Examples: Python, Vue, NetworkX, LLM, GPT, Gemini -> Skill; ProjectOS -> Project; papers/documents -> Publication; awards, metrics, or concrete outcomes -> Achievement.
- Entities shown in the UI should be meaningful career/project objects, not chunks, vague topics, sentence fragments, or generic nouns.
- Entity type names and relation type names must be English.
- Extracted entity names may preserve the source language and can be Korean, English, or mixed Korean/English.

Document:
{sample}

Return only valid JSON in this exact shape:
{{
  "entity_types": [
    {{"name": "Person", "description": "individual people", "examples": ["양필성", "John Kim"]}}
  ],
  "edge_types": [
    {{"name": "WORKED_AT", "description": "employment or affiliation relation", "source_types": ["Person"], "target_types": ["Organization"]}}
  ],
  "analysis_summary": "summary of the document domain and ontology design"
}}"""

    def _parse_result(self, result: dict) -> Ontology:
        allowed_entity_set = set(self.FIXED_ENTITY_TYPES)
        allowed_edge_set = set(self.FIXED_EDGE_TYPES)
        entity_types = [
            EntityTypeDef(
                name=e["name"],
                description=e.get("description", ""),
                examples=e.get("examples", []),
            )
            for e in result.get("entity_types", [])
            if e.get("name") in allowed_entity_set
        ]
        if not entity_types:
            entity_types = [EntityTypeDef(name=n, description="", examples=[]) for n in self.FIXED_ENTITY_TYPES]
        edge_types = [
            EdgeTypeDef(
                name=e["name"],
                description=e.get("description", ""),
                source_types=e.get("source_types", []),
                target_types=e.get("target_types", []),
            )
            for e in result.get("edge_types", [])
            if e.get("name") in allowed_edge_set
        ]
        if not edge_types:
            edge_types = [EdgeTypeDef(name=n, description="", source_types=[], target_types=[]) for n in self.FIXED_EDGE_TYPES]
        return Ontology(
            entity_types=entity_types,
            edge_types=edge_types,
            analysis_summary=result.get("analysis_summary", ""),
        )
