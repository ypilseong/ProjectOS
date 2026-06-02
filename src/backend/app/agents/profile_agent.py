from typing import Callable

import networkx as nx

from app.models.graph import CareerProfile
from app.utils.entity_validation import is_valid_person_name
from app.utils.llm_client import LLMClient
from app.utils.routing import Role
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ProfileAgent:
    def __init__(self):
        self._llm = LLMClient.for_role(Role.PROFILE)

    async def run(
        self,
        graph: nx.DiGraph,
        person_ids: list[str] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[CareerProfile]:
        all_person_nodes = [
            (nid, data)
            for nid, data in graph.nodes(data=True)
            if data.get("type") == "Person"
            and is_valid_person_name(str(data.get("name", "")))
        ]
        if person_ids is not None:
            id_set = set(person_ids)
            person_nodes = [(nid, data) for nid, data in all_person_nodes if nid in id_set]
        else:
            person_nodes = all_person_nodes

        profiles = []
        total = len(person_nodes)
        for i, (node_id, node_data) in enumerate(person_nodes, start=1):
            name = node_data["name"]
            logger.info(f"ProfileAgent: building profile for {name}")
            context = self._collect_context(graph, node_id)
            profile = await self._generate_profile(name, context)
            profiles.append(profile)
            if progress_callback:
                progress_callback(i, total, name)
        return profiles

    def _collect_context(self, graph: nx.DiGraph, person_id: str) -> dict:
        context: dict[str, list] = {
            "skills": [],
            "projects": [],
            "organizations": [],
            "publications": [],
            "achievements": [],
            "roles": [],
        }
        type_map = {
            "Skill": "skills",
            "Project": "projects",
            "Organization": "organizations",
            "Publication": "publications",
            "Achievement": "achievements",
            "Role": "roles",
        }
        visited = {person_id}
        queue = list(graph.successors(person_id)) + list(graph.predecessors(person_id))
        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            ntype = graph.nodes[nid].get("type", "")
            name = graph.nodes[nid].get("name", "")
            key = type_map.get(ntype)
            if key and name and name not in context[key]:
                context[key].append(name)
            if len(visited) < 50:
                queue.extend(graph.successors(nid))
                queue.extend(graph.predecessors(nid))
        return context

    async def _generate_profile(self, name: str, context: dict) -> CareerProfile:
        prompt = f"""다음 커리어 정보를 바탕으로 종합적인 커리어 프로필을 생성하세요.

이름: {name}
기술 스택: {', '.join(context['skills']) or '없음'}
주요 프로젝트: {', '.join(context['projects']) or '없음'}
소속 기관: {', '.join(context['organizations']) or '없음'}
논문/출판물: {', '.join(context['publications']) or '없음'}
성과: {', '.join(context['achievements']) or '없음'}

JSON 형식으로 응답 (한국어 중심):
{{
  "expertise": ["주요 전문 분야 목록"],
  "skills": ["기술 스택 목록"],
  "projects": ["프로젝트 목록"],
  "organizations": ["기관 목록"],
  "publications": ["논문 목록"],
  "achievements": ["성과 목록"],
  "persona_summary": "2000자 내외 종합 커리어 요약 (한국어)",
  "timeline": [{{"year": 2020, "event": "사건"}}]
}}"""
        result = await self._llm.chat_json([{"role": "user", "content": prompt}])
        return CareerProfile(
            name=name,
            expertise=result.get("expertise", []),
            skills=result.get("skills", context["skills"]),
            projects=result.get("projects", context["projects"]),
            organizations=result.get("organizations", context["organizations"]),
            publications=result.get("publications", context["publications"]),
            achievements=result.get("achievements", context["achievements"]),
            persona_summary=result.get("persona_summary", ""),
            timeline=result.get("timeline", []),
        )
