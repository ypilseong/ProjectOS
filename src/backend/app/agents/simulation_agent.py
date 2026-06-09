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
        project_id: str = "",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        started_at_dt = datetime.now(timezone.utc)
        started_at = started_at_dt.isoformat()
        run_id = run_id or _simulation_run_id(started_at_dt)
        input_graph_snapshot = build_input_graph_snapshot(graph, captured_at=started_at)
        personas = await self._persona_agent.run(graph, chunks, query=query)
        environment = await self._environment_agent.run(graph, chunks, personas, query=query)
        raw_result = await self._simulate(graph, chunks, personas, environment, query, cv_text)
        legacy_result = self._normalize_legacy_result(raw_result, personas, environment, query)

        applied = {"nodes_added": 0, "edges_added": 0}
        delta_statuses = _proposed_delta_statuses(legacy_result.get("graph_enhancements", {}))
        if apply_graph:
            applied, delta_statuses = _apply_graph_enhancements_with_status(
                graph,
                legacy_result.get("graph_enhancements", {}),
            )

        completed_at = datetime.now(timezone.utc).isoformat()
        return build_simulation_result_v2(
            legacy_result,
            personas,
            environment,
            query,
            project_id=project_id,
            run_id=run_id,
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            input_graph_snapshot=input_graph_snapshot,
            applied_graph_changes=applied,
            delta_statuses=delta_statuses,
        )

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

    def _normalize_legacy_result(
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


def build_input_graph_snapshot(graph: nx.DiGraph, captured_at: str | None = None) -> dict[str, Any]:
    snapshot = nx.node_link_data(graph)
    return {
        "format": "networkx_node_link",
        "captured_at": captured_at or datetime.now(timezone.utc).isoformat(),
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "graph": snapshot,
    }


def build_simulation_result_v2(
    legacy_result: dict[str, Any],
    personas: list[PersonaAgentSpec],
    environment: EnvironmentSpec,
    query: str,
    *,
    project_id: str = "",
    run_id: str | None = None,
    status: str = "completed",
    started_at: str | None = None,
    completed_at: str | None = None,
    input_graph_snapshot: dict[str, Any] | None = None,
    applied_graph_changes: dict[str, int] | None = None,
    delta_statuses: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    started_at = started_at or legacy_result.get("generated_at") or now.isoformat()
    completed_at = completed_at or now.isoformat()
    run_id = run_id or _simulation_run_id(now)
    applied_graph_changes = applied_graph_changes or {"nodes_added": 0, "edges_added": 0}
    delta_statuses = delta_statuses or _proposed_delta_statuses(legacy_result.get("graph_enhancements", {}))

    graph_delta = _build_graph_delta(legacy_result.get("graph_enhancements", {}), delta_statuses)
    report_sections = _build_report_sections(legacy_result, graph_delta)
    v2_personas = [_persona_to_v2(persona) for persona in personas]
    debate = _build_debate(legacy_result.get("timeline", []), v2_personas)
    workflow_steps = _build_workflow_steps(
        v2_personas,
        debate,
        graph_delta,
        report_sections,
        applied_graph_changes,
        started_at,
        completed_at,
    )
    event_log = _build_event_log(workflow_steps, v2_personas, debate, graph_delta, report_sections)
    low_confidence_count = sum(
        1
        for item in [*graph_delta["nodes"], *graph_delta["edges"]]
        if item.get("confidence") is not None and item["confidence"] < 0.6
    )
    report = legacy_result.get("report", {}) or {}

    envelope = {
        "schema_version": "2.0",
        "project_id": project_id,
        "run_id": run_id,
        "query": query,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "generated_at": completed_at,
        "summary": {
            "title": str(report.get("title") or "ProjectOS Simulation Report"),
            "answer": str(report.get("answer") or query or environment.objective),
            "graph_delta_count": len(graph_delta["nodes"]) + len(graph_delta["edges"]),
            "report_section_count": len(report_sections),
            "low_confidence_count": low_confidence_count,
        },
        "workflow_steps": workflow_steps,
        "event_log": event_log,
        "personas": v2_personas,
        "environment": _environment_to_v2(environment),
        "debate": debate,
        "graph_delta": graph_delta,
        "report_sections": report_sections,
        "input_graph_snapshot": input_graph_snapshot,
        "legacy": {
            "generated_at": legacy_result.get("generated_at"),
            "query": query,
            "personas": legacy_result.get("personas", []),
            "environment": legacy_result.get("environment", {}),
            "timeline": legacy_result.get("timeline", []),
            "graph_enhancements": legacy_result.get("graph_enhancements", {"nodes": [], "edges": []}),
            "cv_improvements": legacy_result.get("cv_improvements", {}),
            "report": report,
            "applied_graph_changes": applied_graph_changes,
        },
    }

    # Compatibility window for existing Obsidian/plugin clients that still read the flat shape.
    envelope["timeline"] = legacy_result.get("timeline", [])
    envelope["graph_enhancements"] = legacy_result.get("graph_enhancements", {"nodes": [], "edges": []})
    envelope["cv_improvements"] = legacy_result.get("cv_improvements", {})
    envelope["report"] = report
    envelope["applied_graph_changes"] = applied_graph_changes
    return envelope


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


def _simulation_run_id(dt: datetime) -> str:
    return f"sim_{dt.strftime('%Y%m%d_%H%M%S_%f')}"


def _persona_to_v2(persona: PersonaAgentSpec) -> dict[str, Any]:
    return {
        "id": persona.agent_id,
        "agent_id": persona.agent_id,
        "name": persona.name,
        "role": persona.role,
        "stance": persona.communication_style,
        "assumptions": [],
        "focus_areas": persona.goals,
        "goals": persona.goals,
        "knowledge": persona.knowledge,
        "source_node_ids": persona.source_nodes,
        "source_nodes": persona.source_nodes,
        "key_points": persona.knowledge,
        "communication_style": persona.communication_style,
    }


def _environment_to_v2(environment: EnvironmentSpec) -> dict[str, Any]:
    return {
        "objective": environment.objective,
        "rules": environment.rules,
        "constraints": environment.constraints,
        "evaluation_criteria": environment.success_criteria,
        "risks": [],
        "rounds": environment.rounds,
        "success_criteria": environment.success_criteria,
    }


def _build_debate(timeline: list[dict[str, Any]], personas: list[dict[str, Any]]) -> dict[str, Any]:
    persona_ids = {persona["id"] for persona in personas}
    turns = []
    for idx, item in enumerate(timeline or []):
        speaker_id = str(item.get("agent_id") or item.get("speaker_id") or "")
        turns.append({
            "turn_id": f"turn_{idx + 1:03d}",
            "round": int(item.get("round") or idx + 1),
            "speaker_id": speaker_id,
            "stance": "review" if speaker_id in persona_ids else "",
            "claim": str(item.get("observation") or item.get("claim") or ""),
            "evidence_refs": _evidence_refs(item.get("evidence_refs") or item.get("evidence")),
            "proposal": str(item.get("proposal") or item.get("recommendation") or ""),
            "unresolved_questions": [
                str(value)
                for value in item.get("unresolved_questions", [])
                if value
            ],
        })
    return {
        "turns": turns,
        "agreements": [],
        "disagreements": [],
        "unresolved_questions": [],
    }


def _build_report_sections(legacy_result: dict[str, Any], graph_delta: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    report = legacy_result.get("report", {}) or {}
    if report:
        sections.append({
            "section_id": "section_summary",
            "title": str(report.get("title") or "Executive Summary"),
            "kind": "executive_summary",
            "summary": str(report.get("answer") or ""),
            "body": str(report.get("answer") or ""),
            "evidence_refs": _evidence_refs(report.get("evidence")),
            "uncertainty": [],
            "related_delta_ids": [],
            "source_persona_ids": [],
        })
        recommendations = [str(value) for value in report.get("recommendations", []) if value]
        if recommendations:
            sections.append({
                "section_id": "section_recommendations",
                "title": "Recommendations",
                "kind": "recommendations",
                "summary": recommendations[0],
                "body": "\n".join(f"- {item}" for item in recommendations),
                "items": recommendations,
                "evidence_refs": _evidence_refs(report.get("evidence")),
                "uncertainty": [],
                "related_delta_ids": [],
                "source_persona_ids": [],
            })

    cv_improvements = legacy_result.get("cv_improvements", {}) or {}
    if cv_improvements:
        bullets = [str(value) for value in cv_improvements.get("bullets", []) if value]
        sections.append({
            "section_id": "section_cv_improvements",
            "title": "CV Improvements",
            "kind": "cv_improvements",
            "summary": str(cv_improvements.get("summary") or ""),
            "body": str(cv_improvements.get("improved_draft") or ""),
            "items": bullets,
            "evidence_refs": [],
            "uncertainty": [],
            "related_delta_ids": [],
            "source_persona_ids": [],
        })

    delta_ids = [
        item["delta_id"]
        for item in [*graph_delta.get("nodes", []), *graph_delta.get("edges", [])]
    ]
    if delta_ids:
        sections.append({
            "section_id": "section_graph_delta",
            "title": "Graph Delta",
            "kind": "graph_delta",
            "summary": f"{len(delta_ids)} graph delta candidates.",
            "body": "\n".join(delta_ids),
            "evidence_refs": [],
            "uncertainty": [],
            "related_delta_ids": delta_ids,
            "source_persona_ids": [],
        })
    return sections


def _build_workflow_steps(
    personas: list[dict[str, Any]],
    debate: dict[str, Any],
    graph_delta: dict[str, Any],
    report_sections: list[dict[str, Any]],
    applied_graph_changes: dict[str, int],
    started_at: str,
    completed_at: str,
) -> list[dict[str, Any]]:
    delta_count = len(graph_delta.get("nodes", [])) + len(graph_delta.get("edges", []))
    applied_count = applied_graph_changes.get("nodes_added", 0) + applied_graph_changes.get("edges_added", 0)
    return [
        _workflow_step("load_context", "Load Context", "completed", started_at, started_at, "Loaded graph and source chunks."),
        _workflow_step("build_personas", "Build Personas", "completed", started_at, started_at, f"Built {len(personas)} persona agents."),
        _workflow_step("build_environment", "Build Environment", "completed", started_at, started_at, "Built simulation rules and constraints."),
        _workflow_step("persona_analysis", "Persona Analysis", "completed", started_at, completed_at, f"Recorded {len(debate.get('turns', []))} debate turns."),
        _workflow_step("debate", "Debate", "completed", started_at, completed_at, f"Grouped {len(debate.get('turns', []))} turns."),
        _workflow_step("graph_delta_draft", "Graph Delta Draft", "completed", started_at, completed_at, f"Drafted {delta_count} graph deltas."),
        _workflow_step("final_report", "Final Report", "completed", started_at, completed_at, f"Created {len(report_sections)} report sections."),
        _workflow_step("apply_graph_changes", "Apply Graph Changes", "completed", started_at, completed_at, f"Applied {applied_count} graph changes."),
        _workflow_step("complete", "Complete", "completed", started_at, completed_at, "Simulation completed."),
    ]


def _workflow_step(
    step_id: str,
    label: str,
    status: str,
    started_at: str,
    completed_at: str,
    summary: str,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "label": label,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "summary": summary,
        "output_refs": {},
        "error": None,
    }


def _build_event_log(
    workflow_steps: list[dict[str, Any]],
    personas: list[dict[str, Any]],
    debate: dict[str, Any],
    graph_delta: dict[str, Any],
    report_sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events = []
    for idx, step in enumerate(workflow_steps, start=1):
        events.append({
            "event_id": f"evt_{idx:03d}",
            "step_id": step["id"],
            "type": "step_completed",
            "timestamp": step["completed_at"],
            "summary": step["summary"],
            "payload_ref": {},
        })

    next_idx = len(events) + 1
    if personas:
        events.append({
            "event_id": f"evt_{next_idx:03d}",
            "step_id": "build_personas",
            "type": "step_result",
            "timestamp": workflow_steps[-1]["completed_at"],
            "summary": f"{len(personas)} personas available.",
            "payload_ref": {"kind": "personas", "ids": [persona["id"] for persona in personas]},
        })
        next_idx += 1
    if debate.get("turns"):
        events.append({
            "event_id": f"evt_{next_idx:03d}",
            "step_id": "debate",
            "type": "step_result",
            "timestamp": workflow_steps[-1]["completed_at"],
            "summary": f"{len(debate['turns'])} debate turns available.",
            "payload_ref": {"kind": "debate", "ids": [turn["turn_id"] for turn in debate["turns"]]},
        })
        next_idx += 1
    delta_ids = [
        item["delta_id"]
        for item in [*graph_delta.get("nodes", []), *graph_delta.get("edges", [])]
    ]
    if delta_ids:
        events.append({
            "event_id": f"evt_{next_idx:03d}",
            "step_id": "graph_delta_draft",
            "type": "graph_delta_proposed",
            "timestamp": workflow_steps[-1]["completed_at"],
            "summary": f"{len(delta_ids)} graph deltas proposed.",
            "payload_ref": {"kind": "graph_delta", "ids": delta_ids},
        })
        next_idx += 1
    if report_sections:
        events.append({
            "event_id": f"evt_{next_idx:03d}",
            "step_id": "final_report",
            "type": "report_section_completed",
            "timestamp": workflow_steps[-1]["completed_at"],
            "summary": f"{len(report_sections)} report sections completed.",
            "payload_ref": {
                "kind": "report_sections",
                "ids": [section["section_id"] for section in report_sections],
            },
        })
    return events


def _build_graph_delta(
    enhancements: dict[str, Any],
    delta_statuses: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    nodes = []
    for idx, node in enumerate(enhancements.get("nodes", []) or []):
        status = _status_at(delta_statuses.get("nodes", []), idx)
        ntype = str(node.get("type") or "").strip()
        name = str(node.get("name") or "").strip()
        node_id = status.get("node_id") or (f"{ntype}:{name}" if ntype and name else "")
        nodes.append({
            "delta_id": f"delta_node_{idx + 1:03d}",
            "operation": "add",
            "node_id": node_id,
            "type": ntype,
            "name": name,
            "description": str(node.get("description") or ""),
            "confidence": _numeric_or_none(node.get("confidence")),
            "evidence_refs": _evidence_refs(node.get("evidence_refs") or node.get("evidence")),
            "source_event_ids": [],
            "source_report_section_ids": ["section_graph_delta"],
            "status": status["status"],
            "status_reason": status.get("status_reason", ""),
        })

    edges = []
    for idx, edge in enumerate(enhancements.get("edges", []) or []):
        status = _status_at(delta_statuses.get("edges", []), idx)
        source_type = str(edge.get("source_type") or "").strip()
        source_name = str(edge.get("source_name") or "").strip()
        target_type = str(edge.get("target_type") or "").strip()
        target_name = str(edge.get("target_name") or "").strip()
        source_id = status.get("source_id") or (f"{source_type}:{source_name}" if source_type and source_name else "")
        target_id = status.get("target_id") or (f"{target_type}:{target_name}" if target_type and target_name else "")
        edges.append({
            "delta_id": f"delta_edge_{idx + 1:03d}",
            "operation": "add",
            "source": {"type": source_type, "name": source_name, "node_id": source_id},
            "target": {"type": target_type, "name": target_name, "node_id": target_id},
            "source_id": source_id,
            "target_id": target_id,
            "source_type": source_type,
            "source_name": source_name,
            "target_type": target_type,
            "target_name": target_name,
            "relation": str(edge.get("relation") or "RELATED_TO"),
            "confidence": _numeric_or_none(edge.get("confidence")),
            "evidence_refs": _evidence_refs(edge.get("evidence_refs") or edge.get("evidence")),
            "source_event_ids": [],
            "source_report_section_ids": ["section_graph_delta"],
            "status": status["status"],
            "status_reason": status.get("status_reason", ""),
        })

    applied_nodes = sum(1 for item in nodes if item["status"] == "applied")
    applied_edges = sum(1 for item in edges if item["status"] == "applied")
    skipped = sum(1 for item in [*nodes, *edges] if item["status"] == "skipped")
    return {
        "summary": {
            "proposed_nodes": len(nodes),
            "proposed_edges": len(edges),
            "applied_nodes": applied_nodes,
            "applied_edges": applied_edges,
            "skipped": skipped,
        },
        "nodes": nodes,
        "edges": edges,
    }


def _status_at(statuses: list[dict[str, Any]], idx: int) -> dict[str, Any]:
    if idx < len(statuses):
        return statuses[idx]
    return {"status": "proposed", "status_reason": ""}


def _proposed_delta_statuses(enhancements: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        "nodes": [{"status": "proposed", "status_reason": ""} for _ in enhancements.get("nodes", []) or []],
        "edges": [{"status": "proposed", "status_reason": ""} for _ in enhancements.get("edges", []) or []],
    }


def _evidence_refs(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _numeric_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_graph_enhancements(graph: nx.DiGraph, enhancements: dict[str, Any]) -> dict[str, int]:
    changes, _ = _apply_graph_enhancements_with_status(graph, enhancements)
    return changes


def _apply_graph_enhancements_with_status(
    graph: nx.DiGraph,
    enhancements: dict[str, Any],
) -> tuple[dict[str, int], dict[str, list[dict[str, Any]]]]:
    nodes_added = 0
    edges_added = 0
    node_statuses: list[dict[str, Any]] = []
    edge_statuses: list[dict[str, Any]] = []

    for node in enhancements.get("nodes", []) or []:
        ntype = str(node.get("type") or "").strip()
        name = str(node.get("name") or "").strip()
        node_id = f"{ntype}:{name}" if ntype and name else ""
        if not ntype or not name:
            node_statuses.append({
                "status": "skipped",
                "status_reason": "Missing node type or name.",
                "node_id": node_id,
            })
            continue
        if node_id in graph:
            node_statuses.append({
                "status": "skipped",
                "status_reason": "Node already exists.",
                "node_id": node_id,
            })
            continue
        graph.add_node(
            node_id,
            type=ntype,
            name=name,
            description=str(node.get("description") or ""),
            source_files=["simulation"],
            source_chunk_ids=[],
            attributes={"simulation_evidence": node.get("evidence", "")},
        )
        node_statuses.append({"status": "applied", "status_reason": "", "node_id": node_id})
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
        if not source_id or not target_id:
            edge_statuses.append({
                "status": "skipped",
                "status_reason": "Source or target node was not found.",
                "source_id": source_id or "",
                "target_id": target_id or "",
            })
            continue
        if graph.has_edge(source_id, target_id):
            edge_statuses.append({
                "status": "skipped",
                "status_reason": "Edge already exists.",
                "source_id": source_id,
                "target_id": target_id,
            })
            continue
        graph.add_edge(
            source_id,
            target_id,
            relation=str(edge.get("relation") or "RELATED_TO"),
            confidence=float(edge.get("confidence") or 0.6),
            source_chunk_id="simulation",
            evidence=str(edge.get("evidence") or ""),
        )
        edge_statuses.append({
            "status": "applied",
            "status_reason": "",
            "source_id": source_id,
            "target_id": target_id,
        })
        edges_added += 1

    return (
        {"nodes_added": nodes_added, "edges_added": edges_added},
        {"nodes": node_statuses, "edges": edge_statuses},
    )


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
