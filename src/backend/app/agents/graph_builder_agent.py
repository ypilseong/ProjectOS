import asyncio
import json
from pathlib import Path
from typing import Callable

import networkx as nx

from app.config import config
from app.models.graph import GraphStats, Ontology, TextChunk
from app.utils.entity_normalization import clean_entity_name
from app.utils.entity_resolver import EntityResolver
from app.utils.entity_validation import is_valid_entity, normalize_entity_type
from app.utils.llm_client import LLMClient
from app.utils.routing import Role
from app.utils.logger import get_logger
from app.utils.user_config import get_user_name_values, get_user_name_variants, load_user_config

logger = get_logger(__name__)

RELATION_TYPE_ALIASES = {
    "LEAD_BY": "LED_BY",
}


DOCUMENT_TYPE_RULES = {
    "cv": """Document-type rules for CV/resume:
- Treat bullet entries under Education, Experience, Projects, Publications, Awards, and Skills as profile evidence about the document owner unless another subject is explicit.
- Prefer Person -> Project/Role/Organization/Institution/Publication/Achievement relations and Project -> Skill relations.
- Extract formal roles, institutions, organizations, publications, awards, GPA, scholarships, and measurable results; avoid section headings such as "Experience" or "Skills" as entities.
- Skills listed without project context may connect to the document owner with USES_SKILL, but if the same chunk names a project, connect the Project to the Skill too.""",
    "paper": """Document-type rules for paper/publication:
- Prioritize Publication, Person, Institution, Organization, Project, Skill/method/model, Event/venue, and concrete contributions or results.
- Extract paper title, authors, venue/conference/journal, affiliations, datasets, methods, models, systems, and measured findings when present.
- Use Publication as the central node and connect it to authors, institutions, projects, methods/skills, venues/events, and achievements.
- Do not create entities for generic sections such as Abstract, Introduction, Related Work, Method, or Conclusion.""",
    "report": """Document-type rules for report:
- Prioritize Project, Organization, Person, Role, Event, Skill/method/tool, Achievement, and decisions or outcomes with evidence.
- Extract executive-summary claims only when they identify concrete entities, measurable outcomes, owners, risks, or recommendations.
- Connect projects to used skills/tools and involved organizations/people; connect recommendations or milestones only when they are concrete events or achievements.
- Do not create graph entities for headings, action-item labels, generic risks, or vague business phrases.""",
    "memo": """Document-type rules for memo/note:
- Notes and memos are often informal; extract only durable entities that should remain useful after the note is gone.
- Prioritize named projects, people, organizations, skills/tools, events, decisions, and follow-up achievements.
- Treat todo/checklist items as Event or Achievement only when they describe a concrete scheduled event, decision, deliverable, or completed result.
- Avoid transient thoughts, unassigned todos, generic reminders, and raw sentence fragments as entities.""",
    "email": """Document-type rules for email/message:
- Prioritize sender/recipient people, organizations, projects, events, commitments, deliverables, and dated decisions.
- Extract relationships only when the email gives evidence for collaboration, ownership, scheduling, delivery, or use of a skill/tool.
- Do not create entities for greetings, signatures, quoted thread fragments, boilerplate disclaimers, or generic message labels.
- If an attachment or linked document is mentioned, extract it only as Publication, Project, or Event when it is named and relevant.""",
}


DOCUMENT_TYPE_ALIASES = {
    "resume": "cv",
    "curriculum_vitae": "cv",
    "publication": "paper",
    "research_paper": "paper",
    "article": "paper",
    "memo": "memo",
    "note": "memo",
    "notes": "memo",
    "mail": "email",
    "message": "email",
}


class GraphBuilderAgent:
    def __init__(self):
        # Graph extraction is normally a bulk per-chunk loop, so keep it local.
        # GRAPH_EXTRACTION_BACKEND allows explicit Claude Code E2E quality tests.
        self._llm = LLMClient.for_role(
            Role.CHUNK_EXTRACTION,
            disable_plugins=config.CLAUDE_GRAPH_DISABLE_PLUGINS,
        )
        self._fuzzy_threshold = config.FUZZY_MATCH_THRESHOLD
        self._resolver = EntityResolver(fuzzy_threshold=self._fuzzy_threshold)
        self._user_context = self._load_user_context()

    @staticmethod
    def _load_user_context() -> str:
        """Build a prompt snippet from user.json names and aliases."""
        names = get_user_name_values(load_user_config())
        if not names:
            return ""
        names_str = " / ".join(names)
        return (
            f"Document owner: {names_str}. "
            "When the subject of an item is not explicitly stated "
            "(e.g. bullet-list entries in a CV or resume), "
            f"treat {names_str} as the implicit subject and extract relations accordingly."
        )

    @staticmethod
    def _load_user_name_variants() -> tuple[str, set[str]]:
        data = load_user_config()
        canonical = (data.get("name") or data.get("display_name") or "").strip()
        variants = set(get_user_name_variants(data))
        return canonical, variants

    def _normalize_entity_name(self, entity_type: str, name: str) -> str:
        cleaned = clean_entity_name(name)
        if entity_type != "Person":
            return cleaned

        canonical, variants = self._load_user_name_variants()
        if not canonical or not variants:
            return cleaned

        lowered = cleaned.lower()
        if lowered in variants:
            return canonical

        parts = [part.strip().lower() for part in cleaned.replace("\\", "/").split("/")]
        if any(part in variants for part in parts):
            return canonical

        if all(variant in lowered for variant in variants):
            return canonical

        return cleaned

    @staticmethod
    def _normalize_relation_type(relation: str) -> str:
        cleaned = (relation or "").strip().upper()
        return RELATION_TYPE_ALIASES.get(cleaned, cleaned)

    def _normalize_relation(
        self,
        relation: str,
        src_type: str,
        src_name: str,
        tgt_type: str,
        tgt_name: str,
    ) -> tuple[str, str, str, str, str]:
        normalized = self._normalize_relation_type(relation)
        if normalized == "USED_IN" and src_type == "Skill" and tgt_type == "Project":
            return "USES_SKILL", tgt_type, tgt_name, src_type, src_name
        if normalized == "APPLIED_TO" and src_type == "Skill" and tgt_type == "Project":
            return "USES_SKILL", tgt_type, tgt_name, src_type, src_name
        if normalized == "APPLIED_TO" and src_type == "Project" and tgt_type == "Skill":
            return "USES_SKILL", src_type, src_name, tgt_type, tgt_name
        return normalized, src_type, src_name, tgt_type, tgt_name

    @staticmethod
    def _document_type_rules(file_type: str) -> str:
        normalized = (file_type or "").strip().lower().replace("-", "_").replace(" ", "_")
        normalized = DOCUMENT_TYPE_ALIASES.get(normalized, normalized)
        return DOCUMENT_TYPE_RULES.get(normalized, "")

    async def run(
        self,
        chunks: list[TextChunk],
        ontology: Ontology,
        incremental: bool = False,
        graph_path: str | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        capture_context: dict[str, dict] | None = None,
    ) -> nx.DiGraph:
        graph = nx.DiGraph()
        self._capture_context = capture_context or {}
        if incremental and graph_path and Path(graph_path).exists():
            data = json.loads(Path(graph_path).read_text())
            # normalize legacy 'links' key back to 'edges' for nx.node_link_graph compatibility
            if "links" in data and "edges" not in data:
                data["edges"] = data.pop("links")
            graph = nx.node_link_graph(data)
            logger.info(f"Loaded existing graph: {graph.number_of_nodes()} nodes")

        entity_types = []
        for entity in ontology.entity_types:
            normalized = normalize_entity_type(entity.name)
            if normalized not in entity_types:
                entity_types.append(normalized)
        edge_types = [e.name for e in ontology.edge_types]

        total = len(chunks)
        allowed_edge_set = set(edge_types)
        workers = max(1, int(config.GRAPH_BUILD_WORKERS or 1))
        if workers == 1 or total <= 1:
            for i, chunk in enumerate(chunks, start=1):
                logger.info(f"Processing chunk {i}/{total}")
                try:
                    result = await self._extract_from_chunk(chunk, entity_types, edge_types)
                    await self._merge_into_graph(graph, result, chunk, allowed_edge_set)
                except Exception as e:
                    logger.error(f"Chunk {chunk.chunk_id} failed: {e}")
                if progress_callback:
                    progress_callback(i, total)
            return graph

        results: list[dict | None] = [None] * total
        completed = 0
        semaphore = asyncio.Semaphore(workers)

        async def extract_one(index: int, chunk: TextChunk) -> None:
            nonlocal completed
            async with semaphore:
                logger.info(f"Processing chunk {index + 1}/{total}")
                try:
                    results[index] = await self._extract_from_chunk(chunk, entity_types, edge_types)
                except Exception as e:
                    logger.error(f"Chunk {chunk.chunk_id} failed: {e}")
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

        await asyncio.gather(*(extract_one(index, chunk) for index, chunk in enumerate(chunks)))
        for chunk, result in zip(chunks, results):
            if result is not None:
                await self._merge_into_graph(graph, result, chunk, allowed_edge_set)

        return graph

    async def _extract_from_chunk(
        self, chunk: TextChunk, entity_types: list[str], edge_types: list[str]
    ) -> dict:
        user_ctx = f"\n{self._user_context}\n" if self._user_context else ""
        doc_rules = self._document_type_rules(chunk.file_type)
        doc_rules_block = f"\n{doc_rules}\n" if doc_rules else ""
        capture = getattr(self, "_capture_context", {}).get(chunk.source_file)
        capture_block = ""
        if capture:
            capture_block = (
                "\nCapture intent for this source:\n"
                f"- Reason captured: {capture.get('capture_reason', '')}\n"
                f"- User is currently working on: {capture.get('current_focus', '')}\n"
                f"- Desired reflection: {capture.get('reflection_intent', '')}\n"
                "Prioritize entities and relations relevant to this intent. "
                "Do not invent entities unrelated to the source text.\n"
            )
        prompt = f"""Extract entities and relations from the text below.
{capture_block}{user_ctx}
Allowed entity types: {', '.join(entity_types)}
Allowed relation types: {', '.join(edge_types)}

Extraction rules:
- Do not create entities for chunks, pages, sections, or raw text snippets.
- Extract important skills, tools, methods, model names, projects, organizations, publications, roles, events, institutions, and concrete achievements so the UI graph shows meaningful key items.
- Use Achievement only for official or record-like profile accomplishments: GPA/grades, honors, scholarships, awards, competition placements, accepted publications, or formally measured academic/professional results. Do not use Achievement for certificates/exam names, insights, motivations, interests, lessons learned, effort, responsibilities, or ordinary project activities; classify certificates/exams as Skill when useful.
- Do not create Keyword or Concept entities. If a term looks like an important keyword, classify it using the most specific allowed type.
- Do not create Technology entities. Technical terms, tools, model names, platforms, frameworks, libraries, and methods must be Skill.
- Examples: "LLM", "GPT", "Gemini", "NetworkX", "Vue", "D3.js" -> Skill.
- Examples: "ProjectOS", "MiroFish" -> Project.
- Examples: "Total GPA 4.35/4.50", "Sanho Scholarship Recipient", "Smart Tourism Big Data Hackathon Encouragement Award" -> Achievement.
- Tool/model names alone are not Projects. Classify them as Skill unless the text names a concrete project, product, paper, or system.
- When a project uses a skill/tool/method/model, extract a Project -> Skill relation using USES_SKILL. Examples: "ProjectOS used Vue and NetworkX" -> ProjectOS USES_SKILL Vue, ProjectOS USES_SKILL NetworkX.
- Keep the graph focused on independent primary entities. Do not create graph entities for project features, outputs, implementation details, or descriptive phrases such as "graph JSON generation", "Obsidian export", "user-centered visualization", "FastAPI backend architecture", or "Vue/D3 frontend implementation".
- If a descriptive project phrase contains a real skill/tool, extract the skill/tool as its own Skill entity and connect the Project to it with USES_SKILL. Put the descriptive feature/output phrase in the Project description instead of making it a node.
- Use HAS_ROLE only for Person -> Role when the role is a formal title or academic position.
- When a person built, led, participated in, or achieved something through a project, also connect the Person to the Project and the Project to its Skills. Do not leave key skills connected only to the Person if a project context is present.
- Avoid vague generic nouns, broad topics, isolated sentence fragments, and duplicate entities.
- Use Person only for real, identifiable human names explicitly present in the text.
- Do not create Person entities for pronouns, the author/user, anonymous people, role titles, departments, fields, or generic descriptions such as "I", "me", "저", "나", "author", "user", "student", "panelists", or "researcher".
- Role is ONLY for formal job titles or academic positions that could appear on a resume or business card. Examples: "Research Engineer", "PhD Student", "Professor", "Team Lead", "Software Engineer", "Undergraduate Researcher". Do NOT classify as Role: activity descriptions ("데이터 검수", "reviewing model evaluation frameworks"), participant labels ("발표자", "사회자", "패널", "moderator"), generic descriptions ("지역 주민", "기업", "약 1년간 근무"), or any phrase that is not a named position. If an item describes a concrete outcome or result → Achievement. If it describes participation in an event → Event. Vague or generic descriptions → do not extract at all.
- Entity type values and relation values must come from the allowed lists.
- Entity names may preserve the source language and can be Korean, English, or mixed Korean/English.
- Prefer one stable label for the same concept within a chunk. When both an acronym and expanded label are present, use the expanded label as the entity name.
{doc_rules_block}

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

    async def _merge_into_graph(
        self, graph: nx.DiGraph, result: dict, chunk: TextChunk, allowed_edge_set: set[str] | None = None
    ):
        node_map: dict[str, str] = {}

        for entity in result.get("entities", []):
            etype = normalize_entity_type(entity.get("type", ""))
            name = self._normalize_entity_name(etype, entity.get("name", ""))
            if not is_valid_entity(etype, name):
                logger.info(f"Skipping invalid entity: {etype}:{name}")
                continue

            existing = await self._resolver.find_existing_node_async(graph, etype, name)
            if existing:
                node_id = existing
                sources = set(graph.nodes[node_id].get("source_files", []))
                sources.add(chunk.source_file)
                graph.nodes[node_id]["source_files"] = list(sources)
                chunk_ids = set(graph.nodes[node_id].get("source_chunk_ids", []))
                chunk_ids.add(chunk.chunk_id)
                graph.nodes[node_id]["source_chunk_ids"] = list(chunk_ids)
            else:
                node_id = f"{etype}:{name}"
                graph.add_node(
                    node_id,
                    type=etype,
                    name=name,
                    description=entity.get("description", ""),
                    source_files=[chunk.source_file],
                    source_chunk_ids=[chunk.chunk_id],
                    attributes={},
                )
            node_map[name] = node_id

        for rel in result.get("relations", []):
            src_type = normalize_entity_type(rel.get("source_type", ""))
            tgt_type = normalize_entity_type(rel.get("target_type", ""))
            src_name = self._normalize_entity_name(src_type, rel.get("source", ""))
            tgt_name = self._normalize_entity_name(tgt_type, rel.get("target", ""))
            relation, src_type, src_name, tgt_type, tgt_name = self._normalize_relation(
                rel.get("relation", ""), src_type, src_name, tgt_type, tgt_name
            )
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
        return self._resolver.find_existing_node(graph, entity_type, name)

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
            etype = normalize_entity_type(entity.get("type", ""))
            name = self._normalize_entity_name(etype, entity.get("name", ""))
            existing = self._find_existing_node(graph, etype, name)
            if existing:
                node_map[name] = existing

        for rel in result.get("relations", []):
            src_type = normalize_entity_type(rel.get("source_type", ""))
            tgt_type = normalize_entity_type(rel.get("target_type", ""))
            src_name = self._normalize_entity_name(src_type, rel.get("source", ""))
            tgt_name = self._normalize_entity_name(tgt_type, rel.get("target", ""))
            relation, src_type, src_name, tgt_type, tgt_name = self._normalize_relation(
                rel.get("relation", ""), src_type, src_name, tgt_type, tgt_name
            )
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
