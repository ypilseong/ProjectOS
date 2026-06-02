import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import networkx as nx

from app.models.graph import TextChunk
from app.utils.llm_client import LLMClient
from app.utils.routing import Role
from app.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_CONTEXT_CHARS = 18000
_MAX_DOC_CHARS = 10000


@dataclass
class PersonaAgentSpec:
    agent_id: str
    name: str
    role: str
    goals: list[str] = field(default_factory=list)
    knowledge: list[str] = field(default_factory=list)
    communication_style: str = ""
    source_nodes: list[str] = field(default_factory=list)


@dataclass
class EnvironmentSpec:
    objective: str
    rules: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    rounds: int = 3
    success_criteria: list[str] = field(default_factory=list)


class PersonaSimulationAgent:
    """Builds ProjectOS-native persona agents from graph nodes and documents."""

    def __init__(self, llm: LLMClient | None = None):
        self._llm = llm or LLMClient.for_role(Role.SIMULATION)

    async def run(
        self,
        graph: nx.DiGraph,
        chunks: list[TextChunk],
        query: str = "",
        max_agents: int = 8,
    ) -> list[PersonaAgentSpec]:
        context = build_simulation_context(graph, chunks, query)
        prompt = f"""ProjectOS의 기존 그래프와 문서를 기반으로 시뮬레이션에 참여할 페르소나 agent를 설계하세요.

요구사항:
- Person 노드가 있으면 우선 사용하세요.
- Person이 부족하면 중요한 Project, Skill, Organization, Achievement를 대표하는 관점 agent를 만드세요.
- 각 agent는 CV/프로필/그래프 강화에 기여할 수 있는 고유 관점을 가져야 합니다.
- 최대 {max_agents}개만 생성하세요.

컨텍스트:
{context}

사용자 쿼리:
{query or "(없음)"}

JSON만 응답하세요:
{{
  "personas": [
    {{
      "agent_id": "agent_1",
      "name": "이름",
      "role": "역할",
      "goals": ["목표"],
      "knowledge": ["근거 지식"],
      "communication_style": "말투/판단 방식",
      "source_nodes": ["그래프 노드 id"]
    }}
  ]
}}"""
        try:
            result = await self._llm.chat_json([{"role": "user", "content": prompt}])
            personas = result.get("personas", [])
            parsed = [self._parse_persona(item, idx) for idx, item in enumerate(personas[:max_agents])]
            return [p for p in parsed if p.name]
        except Exception as exc:
            logger.warning(f"PersonaSimulationAgent failed, using fallback: {exc}")
            return self._fallback_personas(graph, max_agents)

    def _parse_persona(self, item: dict[str, Any], idx: int) -> PersonaAgentSpec:
        return PersonaAgentSpec(
            agent_id=str(item.get("agent_id") or f"agent_{idx + 1}"),
            name=str(item.get("name") or ""),
            role=str(item.get("role") or "Reviewer"),
            goals=[str(v) for v in item.get("goals", []) if v],
            knowledge=[str(v) for v in item.get("knowledge", []) if v],
            communication_style=str(item.get("communication_style") or ""),
            source_nodes=[str(v) for v in item.get("source_nodes", []) if v],
        )

    def _fallback_personas(self, graph: nx.DiGraph, max_agents: int) -> list[PersonaAgentSpec]:
        candidates = sorted(
            graph.nodes(data=True),
            key=lambda item: (item[1].get("type") != "Person", -graph.degree(item[0])),
        )
        personas = []
        for idx, (node_id, data) in enumerate(candidates[:max_agents]):
            ntype = data.get("type", "Entity")
            name = data.get("name", node_id)
            personas.append(
                PersonaAgentSpec(
                    agent_id=f"agent_{idx + 1}",
                    name=name,
                    role=f"{ntype} perspective",
                    goals=[f"{name}와 연결된 근거를 바탕으로 누락된 강점과 리스크를 찾는다."],
                    knowledge=[data.get("description", "") or f"{ntype} node"],
                    communication_style="근거 중심, 간결한 제안",
                    source_nodes=[node_id],
                )
            )
        return personas


class EnvironmentRulesAgent:
    """Builds simulation rules and constraints from the user goal and graph state."""

    def __init__(self, llm: LLMClient | None = None):
        self._llm = llm or LLMClient.for_role(Role.SIMULATION)

    async def run(
        self,
        graph: nx.DiGraph,
        chunks: list[TextChunk],
        personas: list[PersonaAgentSpec],
        query: str = "",
    ) -> EnvironmentSpec:
        context = build_simulation_context(graph, chunks, query)
        persona_summary = "\n".join(f"- {p.agent_id}: {p.name} ({p.role})" for p in personas)
        prompt = f"""ProjectOS 시뮬레이션 환경과 규칙을 설계하세요.

목표:
- 그래프의 누락 노드/관계를 찾고 강화합니다.
- CV 문서가 있으면 더 설득력 있는 개선 방향을 만듭니다.
- 사용자 쿼리가 있으면 최종 리포트가 그 질문에 답하도록 합니다.

페르소나:
{persona_summary}

컨텍스트:
{context}

사용자 쿼리:
{query or "(없음)"}

JSON만 응답하세요:
{{
  "objective": "시뮬레이션 목표",
  "rules": ["규칙"],
  "constraints": ["제약"],
  "rounds": 3,
  "success_criteria": ["성공 기준"]
}}"""
        try:
            result = await self._llm.chat_json([{"role": "user", "content": prompt}])
            return EnvironmentSpec(
                objective=str(result.get("objective") or "강점과 근거를 검토한다."),
                rules=[str(v) for v in result.get("rules", []) if v],
                constraints=[str(v) for v in result.get("constraints", []) if v],
                rounds=max(1, min(int(result.get("rounds", 3)), 8)),
                success_criteria=[str(v) for v in result.get("success_criteria", []) if v],
            )
        except Exception as exc:
            logger.warning(f"EnvironmentRulesAgent failed, using fallback: {exc}")
            return EnvironmentSpec(
                objective=query or "ProjectOS 그래프와 CV를 강화한다.",
                rules=[
                    "모든 제안은 그래프 노드, 관계, 원문 청크 중 하나 이상의 근거를 가져야 한다.",
                    "추측은 명시하고 그래프에 바로 반영하지 않는다.",
                    "CV 개선은 성과, 맥락, 역할, 수치를 우선한다.",
                ],
                constraints=["새 사실을 날조하지 않는다.", "불확실한 관계는 낮은 confidence로 표시한다."],
                rounds=3,
                success_criteria=["그래프 강화 후보 도출", "CV 개선 초안 또는 쿼리 리포트 생성"],
            )


class ProjectSimulationAgent:
    """Runs a lightweight multi-agent simulation over a ProjectOS graph."""

    def __init__(
        self,
        persona_agent: PersonaSimulationAgent | None = None,
        environment_agent: EnvironmentRulesAgent | None = None,
        llm: LLMClient | None = None,
    ):
        self._llm = llm or LLMClient.for_role(Role.SIMULATION)
        self._persona_agent = persona_agent or PersonaSimulationAgent(self._llm)
        self._environment_agent = environment_agent or EnvironmentRulesAgent(self._llm)

    async def run(
        self,
        graph: nx.DiGraph,
        chunks: list[TextChunk],
        query: str = "",
        cv_text: str = "",
        apply_graph: bool = True,
    ) -> dict[str, Any]:
        personas = await self._persona_agent.run(graph, chunks, query=query)
        environment = await self._environment_agent.run(graph, chunks, personas, query=query)
        raw_result = await self._simulate(graph, chunks, personas, environment, query, cv_text)
        result = self._normalize_result(raw_result, personas, environment, query)

        applied = {"nodes_added": 0, "edges_added": 0}
        if apply_graph:
            applied = apply_graph_enhancements(graph, result.get("graph_enhancements", {}))

        result["applied_graph_changes"] = applied
        return result

    async def _simulate(
        self,
        graph: nx.DiGraph,
        chunks: list[TextChunk],
        personas: list[PersonaAgentSpec],
        environment: EnvironmentSpec,
        query: str,
        cv_text: str,
    ) -> dict[str, Any]:
        context = build_simulation_context(graph, chunks, query)
        personas_json = json.dumps([asdict(p) for p in personas], ensure_ascii=False, indent=2)
        environment_json = json.dumps(asdict(environment), ensure_ascii=False, indent=2)
        prompt = f"""다음 ProjectOS 페르소나 agent들과 환경 규칙으로 {environment.rounds}라운드 시뮬레이션을 실행하세요.

출력 목적:
1. 기존 그래프를 강화할 수 있는 노드/관계 후보
2. CV가 있으면 CV 보강 초안
3. 사용자 쿼리가 있으면 쿼리에 대한 분석 리포트

페르소나:
{personas_json}

환경:
{environment_json}

그래프/문서 컨텍스트:
{context}

CV 원문:
{cv_text[:_MAX_DOC_CHARS] or "(chunks에서 추론)"}

사용자 쿼리:
{query or "(없음)"}

JSON만 응답하세요:
{{
  "timeline": [
    {{"round": 1, "agent_id": "agent_1", "observation": "관찰", "proposal": "제안"}}
  ],
  "graph_enhancements": {{
    "nodes": [
      {{"type": "Skill|Project|Achievement|Role|Organization|Publication|Event|Institution", "name": "노드명", "description": "설명", "evidence": "근거"}}
    ],
    "edges": [
      {{"source_type": "Person", "source_name": "출발 노드명", "target_type": "Skill", "target_name": "도착 노드명", "relation": "USES_SKILL", "evidence": "근거", "confidence": 0.7}}
    ]
  }},
  "cv_improvements": {{
    "summary": "개선 요약",
    "improved_draft": "개선된 CV/문서 초안 또는 빈 문자열",
    "bullets": ["보강 bullet"]
  }},
  "report": {{
    "title": "리포트 제목",
    "answer": "사용자 쿼리에 대한 답변 또는 시뮬레이션 요약",
    "recommendations": ["추천 조치"],
    "evidence": ["근거"]
  }}
}}"""
        try:
            return await self._llm.chat_json([{"role": "user", "content": prompt}])
        except Exception as exc:
            logger.warning(f"ProjectSimulationAgent simulation failed, using fallback: {exc}")
            return fallback_simulation_result(graph, chunks, personas, environment, query)

    def _normalize_result(
        self,
        result: dict[str, Any],
        personas: list[PersonaAgentSpec],
        environment: EnvironmentSpec,
        query: str,
    ) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "personas": [asdict(p) for p in personas],
            "environment": asdict(environment),
            "timeline": result.get("timeline", []),
            "graph_enhancements": result.get("graph_enhancements", {"nodes": [], "edges": []}),
            "cv_improvements": result.get("cv_improvements", {}),
            "report": result.get("report", {}),
        }


def build_simulation_context(graph: nx.DiGraph, chunks: list[TextChunk], query: str = "") -> str:
    type_counts: dict[str, int] = {}
    for _, data in graph.nodes(data=True):
        ntype = data.get("type", "Unknown")
        type_counts[ntype] = type_counts.get(ntype, 0) + 1

    important_nodes = sorted(graph.nodes, key=lambda node: -graph.degree(node))[:30]
    node_lines = []
    for node_id in important_nodes:
        data = graph.nodes[node_id]
        node_lines.append(
            f"- {node_id} [{data.get('type', 'Unknown')}]: {data.get('description', '')}"
        )

    edge_lines = []
    for source, target, data in list(graph.edges(data=True))[:80]:
        edge_lines.append(
            f"- {graph.nodes[source].get('name', source)} --{data.get('relation', '')}--> "
            f"{graph.nodes[target].get('name', target)}"
        )

    doc_text = "\n\n".join(
        f"[{chunk.source_file}#{chunk.chunk_id}]\n{chunk.text}"
        for chunk in select_relevant_chunks(chunks, query)
    )

    context = f"""## Graph Summary
nodes={graph.number_of_nodes()}, edges={graph.number_of_edges()}, types={type_counts}

## Important Nodes
{chr(10).join(node_lines) or "(none)"}

## Edges
{chr(10).join(edge_lines) or "(none)"}

## Document Excerpts
{doc_text[:_MAX_DOC_CHARS] or "(none)"}"""
    return context[:_MAX_CONTEXT_CHARS]


def select_relevant_chunks(chunks: list[TextChunk], query: str = "", limit: int = 12) -> list[TextChunk]:
    if not query.strip():
        cv_chunks = [chunk for chunk in chunks if chunk.file_type == "cv"]
        return (cv_chunks or chunks)[:limit]
    tokens = [token.lower() for token in query.split() if len(token) > 1]
    scored = []
    for chunk in chunks:
        text = chunk.text.lower()
        score = sum(1 for token in tokens if token in text)
        if chunk.file_type == "cv":
            score += 0.5
        scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:limit]]


def apply_graph_enhancements(graph: nx.DiGraph, enhancements: dict[str, Any]) -> dict[str, int]:
    nodes_added = 0
    edges_added = 0

    for node in enhancements.get("nodes", []) or []:
        ntype = str(node.get("type") or "").strip()
        name = str(node.get("name") or "").strip()
        if not ntype or not name:
            continue
        node_id = f"{ntype}:{name}"
        if node_id not in graph:
            graph.add_node(
                node_id,
                type=ntype,
                name=name,
                description=str(node.get("description") or ""),
                source_files=["simulation"],
                source_chunk_ids=[],
                attributes={"simulation_evidence": node.get("evidence", "")},
            )
            nodes_added += 1

    for edge in enhancements.get("edges", []) or []:
        source_id = _find_node_id(
            graph,
            str(edge.get("source_type") or ""),
            str(edge.get("source_name") or ""),
        )
        target_id = _find_node_id(
            graph,
            str(edge.get("target_type") or ""),
            str(edge.get("target_name") or ""),
        )
        if not source_id or not target_id or graph.has_edge(source_id, target_id):
            continue
        graph.add_edge(
            source_id,
            target_id,
            relation=str(edge.get("relation") or "RELATED_TO"),
            confidence=float(edge.get("confidence") or 0.6),
            source_chunk_id="simulation",
            evidence=str(edge.get("evidence") or ""),
        )
        edges_added += 1

    return {"nodes_added": nodes_added, "edges_added": edges_added}


def _find_node_id(graph: nx.DiGraph, ntype: str, name: str) -> str | None:
    exact = f"{ntype}:{name}"
    if exact in graph:
        return exact
    name_lower = name.lower().strip()
    for node_id, data in graph.nodes(data=True):
        if data.get("type") == ntype and str(data.get("name", "")).lower().strip() == name_lower:
            return node_id
    return None


def fallback_simulation_result(
    graph: nx.DiGraph,
    chunks: list[TextChunk],
    personas: list[PersonaAgentSpec],
    environment: EnvironmentSpec,
    query: str,
) -> dict[str, Any]:
    top_nodes = sorted(graph.nodes, key=lambda node: -graph.degree(node))[:5]
    evidence = [
        f"{graph.nodes[node].get('name', node)} ({graph.nodes[node].get('type', 'Unknown')})"
        for node in top_nodes
    ]
    cv_chunks = [chunk.text for chunk in chunks if chunk.file_type == "cv"]
    return {
        "timeline": [
            {
                "round": 1,
                "agent_id": personas[0].agent_id if personas else "agent_1",
                "observation": "그래프 중심 노드와 CV 청크를 기준으로 검토했습니다.",
                "proposal": "중심 노드의 성과, 사용 기술, 결과 지표를 문서에 더 명확히 연결하세요.",
            }
        ],
        "graph_enhancements": {"nodes": [], "edges": []},
        "cv_improvements": {
            "summary": "기존 근거를 기반으로 역할, 사용 기술, 결과를 더 명확히 쓰는 방향이 적합합니다.",
            "improved_draft": "\n\n".join(cv_chunks[:3]),
            "bullets": [
                "각 프로젝트 항목에 문제, 본인 역할, 기술 스택, 결과를 한 문장으로 연결",
                "성과가 있는 항목은 수치 또는 검증 가능한 산출물 추가",
            ],
        },
        "report": {
            "title": "ProjectOS Simulation Report",
            "answer": query or environment.objective,
            "recommendations": [
                "그래프의 중심 노드를 CV 핵심 서사로 사용",
                "고립 노드나 설명이 짧은 노드는 추가 근거 문서로 보강",
            ],
            "evidence": evidence,
        },
    }
