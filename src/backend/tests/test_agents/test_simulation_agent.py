import networkx as nx
import pytest

from app.agents.simulation_agent import (
    EnvironmentSpec,
    PersonaAgentSpec,
    PersonaSimulationAgent,
    ProjectSimulationAgent,
    apply_graph_enhancements,
    build_simulation_context,
    fallback_simulation_result,
)
from app.models.graph import TextChunk


def _graph_with_category_hub() -> nx.DiGraph:
    """Graph where a Category hub has the highest degree but real entities are few."""
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang")
    graph.add_node("Category:Skills", type="Category", name="Skills")
    graph.add_edge("Person:Yang", "Category:Skills", relation="HAS")
    for i in range(6):
        sid = f"Skill:S{i}"
        graph.add_node(sid, type="Skill", name=f"S{i}", description=f"skill {i}")
        graph.add_edge("Category:Skills", sid, relation="INCLUDES")
    return graph


def test_apply_graph_enhancements_adds_nodes_and_edges():
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang")

    changes = apply_graph_enhancements(
        graph,
        {
            "nodes": [
                {
                    "type": "Skill",
                    "name": "Python",
                    "description": "Programming",
                    "evidence": "cv.pdf",
                }
            ],
            "edges": [
                {
                    "source_type": "Person",
                    "source_name": "Yang",
                    "target_type": "Skill",
                    "target_name": "Python",
                    "relation": "USES_SKILL",
                    "confidence": 0.8,
                }
            ],
        },
    )

    assert changes == {"nodes_added": 1, "edges_added": 1}
    assert "Skill:Python" in graph
    assert graph.has_edge("Person:Yang", "Skill:Python")
    assert graph.edges["Person:Yang", "Skill:Python"]["relation"] == "USES_SKILL"


def test_apply_graph_enhancements_attaches_simulation_evidence_anchor():
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang")

    apply_graph_enhancements(
        graph,
        {
            "nodes": [
                {"type": "Skill", "name": "Python", "evidence": "cv.pdf says Python"}
            ],
            "edges": [
                {
                    "source_type": "Person",
                    "source_name": "Yang",
                    "target_type": "Skill",
                    "target_name": "Python",
                    "relation": "USES_SKILL",
                    "evidence": "Yang uses Python",
                    "confidence": 0.7,
                }
            ],
        },
    )

    node_evidence = graph.nodes["Skill:Python"]["evidence"]
    assert isinstance(node_evidence, list)
    assert node_evidence[0]["method"] == "simulation"
    assert node_evidence[0]["directness"] == "inferred"
    assert node_evidence[0]["quote"] == "cv.pdf says Python"

    edge_evidence = graph.edges["Person:Yang", "Skill:Python"]["evidence"]
    assert isinstance(edge_evidence, dict)
    assert edge_evidence["method"] == "simulation"
    assert edge_evidence["directness"] == "inferred"
    assert edge_evidence["quote"] == "Yang uses Python"
    assert edge_evidence["confidence"] == 0.7


@pytest.mark.asyncio
async def test_project_simulation_agent_returns_schema_v2_with_input_snapshot():
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang")
    chunks = [
        TextChunk("c1", "Yang built ProjectOS with Python.", "cv.pdf", "cv", None, 0),
    ]
    persona = PersonaAgentSpec(
        agent_id="agent_1",
        name="Yang",
        role="Person perspective",
        goals=["Find graph gaps"],
        knowledge=["ProjectOS evidence"],
        source_nodes=["Person:Yang"],
    )
    environment = EnvironmentSpec(objective="Improve CV", success_criteria=["source-backed deltas"])

    class FakePersonaAgent:
        async def run(self, graph, chunks, query="", max_agents=8):
            return [persona]

    class FakeEnvironmentAgent:
        async def run(self, graph, chunks, personas, query=""):
            return environment

    class FakeLlm:
        async def chat_json(self, messages):
            return {
                "timeline": [
                    {
                        "round": 1,
                        "agent_id": "agent_1",
                        "observation": "Python evidence is present.",
                        "proposal": "Add Python as an explicit skill.",
                    }
                ],
                "graph_enhancements": {
                    "nodes": [
                        {
                            "type": "Skill",
                            "name": "Python",
                            "description": "Programming language",
                            "evidence": "chunk:cv.pdf#c1",
                        }
                    ],
                    "edges": [
                        {
                            "source_type": "Person",
                            "source_name": "Yang",
                            "target_type": "Skill",
                            "target_name": "Python",
                            "relation": "USES_SKILL",
                            "evidence": "chunk:cv.pdf#c1",
                            "confidence": 0.8,
                        }
                    ],
                },
                "cv_improvements": {"summary": "Make the skill explicit."},
                "report": {"title": "Simulation Report", "answer": "ok"},
            }

    agent = ProjectSimulationAgent(
        persona_agent=FakePersonaAgent(),
        environment_agent=FakeEnvironmentAgent(),
        llm=FakeLlm(),
    )

    result = await agent.run(graph, chunks, query="Improve CV", project_id="project-1")

    assert result["schema_version"] == "2.0"
    assert result["project_id"] == "project-1"
    assert result["run_id"].startswith("sim_")
    assert result["input_graph_snapshot"]["node_count"] == 1
    assert result["input_graph_snapshot"]["edge_count"] == 0
    assert result["summary"]["graph_delta_count"] == 2
    assert result["graph_delta"]["summary"] == {
        "proposed_nodes": 1,
        "proposed_edges": 1,
        "applied_nodes": 1,
        "applied_edges": 1,
        "skipped": 0,
    }
    assert result["graph_delta"]["nodes"][0]["status"] == "applied"
    assert result["graph_delta"]["edges"][0]["source_id"] == "Person:Yang"
    assert result["graph_delta"]["edges"][0]["target_id"] == "Skill:Python"
    assert result["report_sections"][0]["section_id"] == "section_summary"
    assert result["debate"]["turns"][0]["speaker_id"] == "agent_1"
    assert result["legacy"]["report"]["answer"] == "ok"
    assert result["report"]["answer"] == "ok"
    assert graph.has_edge("Person:Yang", "Skill:Python")


@pytest.mark.asyncio
async def test_project_simulation_agent_marks_deltas_proposed_without_apply():
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang")
    chunks = [TextChunk("c1", "Yang built ProjectOS.", "cv.pdf", "cv", None, 0)]
    persona = PersonaAgentSpec(agent_id="agent_1", name="Yang", role="Person perspective")
    environment = EnvironmentSpec(objective="Improve CV")

    class FakePersonaAgent:
        async def run(self, graph, chunks, query="", max_agents=8):
            return [persona]

    class FakeEnvironmentAgent:
        async def run(self, graph, chunks, personas, query=""):
            return environment

    class FakeLlm:
        async def chat_json(self, messages):
            return {
                "graph_enhancements": {
                    "nodes": [{"type": "Skill", "name": "Python"}],
                    "edges": [],
                },
                "report": {"answer": "ok"},
            }

    agent = ProjectSimulationAgent(
        persona_agent=FakePersonaAgent(),
        environment_agent=FakeEnvironmentAgent(),
        llm=FakeLlm(),
    )

    result = await agent.run(graph, chunks, query="Improve CV", apply_graph=False)

    assert result["graph_delta"]["nodes"][0]["status"] == "proposed"
    assert result["applied_graph_changes"] == {"nodes_added": 0, "edges_added": 0}
    assert "Skill:Python" not in graph


@pytest.mark.asyncio
async def test_project_simulation_agent_runs_multi_turn_persona_debate():
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang")
    chunks = [TextChunk("c1", "Yang built ProjectOS.", "cv.pdf", "cv", None, 0)]
    personas = [
        PersonaAgentSpec(agent_id="agent_1", name="Yang", role="Person perspective"),
        PersonaAgentSpec(agent_id="agent_2", name="Reviewer", role="Evidence reviewer"),
    ]
    environment = EnvironmentSpec(objective="Improve CV", rounds=2)

    class FakePersonaAgent:
        async def run(self, graph, chunks, query="", max_agents=8):
            return personas

    class FakeEnvironmentAgent:
        async def run(self, graph, chunks, personas, query=""):
            return environment

    class FakeLlm:
        def __init__(self):
            self.turn_prompts = []
            self.synthesis_prompts = []

        async def chat_json(self, messages):
            prompt = messages[-1]["content"]
            if "다음 ProjectOS 페르소나 debate 로그를 종합" in prompt:
                self.synthesis_prompts.append(prompt)
                return {
                    "graph_enhancements": {"nodes": [], "edges": []},
                    "cv_improvements": {"summary": "Keep source-backed claims."},
                    "report": {"title": "Simulation Report", "answer": "ok"},
                }

            self.turn_prompts.append(prompt)
            return {
                "observation": f"observation {len(self.turn_prompts)}",
                "proposal": f"proposal {len(self.turn_prompts)}",
                "evidence_refs": ["Person:Yang"],
                "responds_to": "turn_001" if len(self.turn_prompts) > 1 else "",
                "unresolved_questions": ["Need stronger evidence"],
            }

    fake_llm = FakeLlm()
    agent = ProjectSimulationAgent(
        persona_agent=FakePersonaAgent(),
        environment_agent=FakeEnvironmentAgent(),
        llm=fake_llm,
    )

    result = await agent.run(graph, chunks, query="Improve CV", apply_graph=False)

    assert len(fake_llm.turn_prompts) == 4
    assert len(fake_llm.synthesis_prompts) == 1
    assert [turn["round"] for turn in result["timeline"]] == [1, 1, 2, 2]
    assert [turn["speaker_id"] for turn in result["debate"]["turns"]] == [
        "agent_1",
        "agent_2",
        "agent_1",
        "agent_2",
    ]
    assert result["debate"]["turns"][1]["responds_to"] == "turn_001"
    assert "turn_001" in fake_llm.turn_prompts[1]


@pytest.mark.asyncio
async def test_simulation_lineage_multi_turn_debate():
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang")
    chunks = [TextChunk("c1", "Yang built ProjectOS.", "cv.pdf", "cv", None, 0)]
    personas = [
        PersonaAgentSpec(agent_id="agent_1", name="Yang", role="Person perspective"),
        PersonaAgentSpec(agent_id="agent_2", name="Reviewer", role="Evidence reviewer"),
    ]
    environment = EnvironmentSpec(objective="Improve CV", rounds=2)

    class FakePersonaAgent:
        async def run(self, graph, chunks, query="", max_agents=8):
            return personas

    class FakeEnvironmentAgent:
        async def run(self, graph, chunks, personas, query=""):
            return environment

    class FakeLlm:
        model_name = "local-test-model"

        async def chat_json(self, messages):
            prompt = messages[-1]["content"]
            if "다음 ProjectOS 페르소나 debate 로그를 종합" in prompt:
                return {
                    "graph_enhancements": {"nodes": [], "edges": []},
                    "report": {"title": "Simulation Report", "answer": "ok"},
                }
            return {"observation": "obs", "proposal": "prop"}

    agent = ProjectSimulationAgent(
        persona_agent=FakePersonaAgent(),
        environment_agent=FakeEnvironmentAgent(),
        llm=FakeLlm(),
    )

    result = await agent.run(graph, chunks, query="Improve CV", apply_graph=False)

    lineage = result["lineage"]
    assert lineage["engine"] == "multi_turn_debate"
    assert lineage["engine_version"]
    assert lineage["turn_calls"] == 4
    assert lineage["fallback_turns"] == 0
    assert lineage["total_turns"] == 4
    assert lineage["turns_with_previous_context"] == 3
    assert lineage["synthesis_model"] == "local-test-model"
    assert lineage["synthesis_completed_at"]

    turns = result["debate"]["turns"]
    assert turns[0]["had_previous_context"] is False
    assert turns[1]["had_previous_context"] is True
    assert all(turn["is_fallback"] is False for turn in turns)


@pytest.mark.asyncio
async def test_simulation_lineage_fallback_engine():
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang")
    chunks = [TextChunk("c1", "Yang built ProjectOS.", "cv.pdf", "cv", None, 0)]
    personas = [
        PersonaAgentSpec(agent_id="agent_1", name="Yang", role="Person perspective"),
        PersonaAgentSpec(agent_id="agent_2", name="Reviewer", role="Evidence reviewer"),
    ]
    environment = EnvironmentSpec(objective="Improve CV", rounds=2)

    class FakePersonaAgent:
        async def run(self, graph, chunks, query="", max_agents=8):
            return personas

    class FakeEnvironmentAgent:
        async def run(self, graph, chunks, personas, query=""):
            return environment

    class FakeLlm:
        model_name = "local-test-model"

        async def chat_json(self, messages):
            raise RuntimeError("llm down")

    agent = ProjectSimulationAgent(
        persona_agent=FakePersonaAgent(),
        environment_agent=FakeEnvironmentAgent(),
        llm=FakeLlm(),
    )

    result = await agent.run(graph, chunks, query="Improve CV", apply_graph=False)

    lineage = result["lineage"]
    assert lineage["engine"] == "fallback"
    assert lineage["turn_calls"] == 0
    assert lineage["fallback_turns"] == 4
    assert lineage["total_turns"] == 4
    assert lineage["synthesis_model"] == ""
    assert lineage["synthesis_completed_at"] == ""


def test_fallback_simulation_result_uses_cv_chunks_and_query():
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang")
    graph.add_node("Project:ProjectOS", type="Project", name="ProjectOS")
    graph.add_edge("Person:Yang", "Project:ProjectOS", relation="DEVELOPED")
    chunks = [
        TextChunk("c1", "Built ProjectOS with Python.", "cv.pdf", "cv", None, 0),
        TextChunk("c2", "Other note", "note.md", "note", None, 10),
    ]
    personas = [
        PersonaAgentSpec(
            agent_id="agent_1",
            name="Yang",
            role="Person perspective",
        )
    ]
    environment = EnvironmentSpec(objective="Improve CV")

    result = fallback_simulation_result(
        graph,
        chunks,
        personas,
        environment,
        "What should be improved?",
    )

    assert result["report"]["answer"] == "What should be improved?"
    assert "Built ProjectOS" in result["cv_improvements"]["improved_draft"]
    assert result["timeline"][0]["agent_id"] == "agent_1"


def test_build_simulation_context_excludes_meta_hubs():
    context = build_simulation_context(_graph_with_category_hub(), [], "")

    summary, _, rest = context.partition("## Important Nodes")
    important, _, edges = rest.partition("## Edges")

    # Category hub dominates degree but must not appear in analytical surfaces.
    assert "Category:Skills" not in important
    assert "Category" not in summary
    assert "Skills" not in edges
    # Real entities are still present.
    assert "Skill:S0" in important


def test_fallback_simulation_result_excludes_meta_hubs():
    graph = _graph_with_category_hub()
    personas = [PersonaAgentSpec(agent_id="agent_1", name="Yang", role="Person perspective")]
    environment = EnvironmentSpec(objective="Improve CV")

    result = fallback_simulation_result(graph, [], personas, environment, "q")

    evidence = " ".join(result["report"].get("evidence", []))
    assert "Skills" not in evidence


def test_fallback_personas_excludes_meta_hubs():
    agent = PersonaSimulationAgent()
    personas = agent._fallback_personas(_graph_with_category_hub(), max_agents=3)

    source_nodes = {n for p in personas for n in p.source_nodes}
    assert "Category:Skills" not in source_nodes
    assert all(p.name != "Skills" for p in personas)


@pytest.mark.asyncio
async def test_debate_and_synthesis_prompts_require_structured_evidence_refs():
    from app.agents.simulation_agent import EVIDENCE_REF_RULE, ProjectSimulationAgent

    captured_prompts = []

    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang")
    chunks = [TextChunk("c1", "Yang built ProjectOS.", "cv.pdf", "cv", None, 0)]
    personas = [
        PersonaAgentSpec(agent_id="agent_1", name="Yang", role="Person perspective"),
        PersonaAgentSpec(agent_id="agent_2", name="Reviewer", role="Evidence reviewer"),
    ]
    environment = EnvironmentSpec(objective="Improve CV", rounds=2)

    class FakePersonaAgent:
        async def run(self, graph, chunks, query="", max_agents=8):
            return personas

    class FakeEnvironmentAgent:
        async def run(self, graph, chunks, personas, query=""):
            return environment

    class PromptCapturingLLM:
        model = "fake-model"

        async def chat_json(self, messages):
            prompt = messages[0]["content"]
            captured_prompts.append(prompt)
            if "debate의 다음 발언" in prompt:
                return {
                    "observation": "관찰", "proposal": "제안",
                    "evidence_refs": ["Skill:Python"],
                    "responds_to": "", "unresolved_questions": [],
                }
            return {
                "timeline": [], "graph_enhancements": {"nodes": [], "edges": []},
                "cv_improvements": {}, "report": {"title": "t", "answer": "a",
                "recommendations": [], "evidence": []},
            }

    agent = ProjectSimulationAgent(
        persona_agent=FakePersonaAgent(),
        environment_agent=FakeEnvironmentAgent(),
        llm=PromptCapturingLLM(),
    )
    await agent.run(graph, chunks, query="테스트 쿼리", apply_graph=False)

    debate_prompts = [p for p in captured_prompts if "debate의 다음 발언" in p]
    synthesis_prompts = [p for p in captured_prompts if "종합해" in p]
    assert debate_prompts and synthesis_prompts
    assert all(EVIDENCE_REF_RULE in p for p in debate_prompts)
    assert all(EVIDENCE_REF_RULE in p for p in synthesis_prompts)


def test_build_debate_aggregates_synthesis_and_turn_questions():
    from app.agents.simulation_agent import _build_debate

    timeline = [
        {"turn_id": "turn_001", "round": 1, "agent_id": "agent_1",
         "observation": "관찰1", "proposal": "제안1", "evidence_refs": [],
         "unresolved_questions": ["Q-턴1", "Q-공통"]},
        {"turn_id": "turn_002", "round": 1, "agent_id": "agent_2",
         "observation": "관찰2", "proposal": "제안2", "evidence_refs": [],
         "unresolved_questions": ["Q-공통", "Q-턴2"]},
    ]
    personas = [{"id": "agent_1"}, {"id": "agent_2"}]
    synthesis = {
        "agreements": ["뉴로-심볼릭 분리 채택"],
        "disagreements": ["프레이밍 레이어 허용 여부"],
        "unresolved_questions": ["Q-합성"],
    }

    debate = _build_debate(timeline, personas, synthesis)

    assert debate["agreements"] == ["뉴로-심볼릭 분리 채택"]
    assert debate["disagreements"] == ["프레이밍 레이어 허용 여부"]
    assert debate["unresolved_questions"] == ["Q-합성", "Q-턴1", "Q-공통", "Q-턴2"]


def test_build_debate_without_synthesis_rolls_up_turn_questions():
    from app.agents.simulation_agent import _build_debate

    timeline = [
        {"turn_id": "turn_001", "round": 1, "agent_id": "agent_1",
         "observation": "관찰", "proposal": "제안", "evidence_refs": [],
         "unresolved_questions": ["Q1"]},
    ]
    debate = _build_debate(timeline, [{"id": "agent_1"}])
    assert debate["unresolved_questions"] == ["Q1"]
    assert debate["agreements"] == []


def test_evidence_ref_rule_names_both_formats():
    from app.agents.simulation_agent import EVIDENCE_REF_RULE

    assert "타입:이름" in EVIDENCE_REF_RULE
    assert "chunk:" in EVIDENCE_REF_RULE


def test_simulation_agents_force_local_llm(monkeypatch):
    from app.agents.simulation_agent import (
        EnvironmentRulesAgent,
        PersonaSimulationAgent,
        ProjectSimulationAgent,
    )
    from app.config import config

    monkeypatch.setattr(config, "LLM_BACKEND", "claude_code")

    assert PersonaSimulationAgent()._llm._impl.__class__.__name__ == "_OpenAIBackend"
    assert EnvironmentRulesAgent()._llm._impl.__class__.__name__ == "_OpenAIBackend"
    assert ProjectSimulationAgent()._llm._impl.__class__.__name__ == "_OpenAIBackend"


@pytest.mark.asyncio
async def test_run_marks_duplicate_delta_as_skipped_without_applying():
    # graph fixture contains the existing node that the LLM will duplicate
    graph = nx.DiGraph()
    graph.add_node("Person:Yang", type="Person", name="Yang")
    graph.add_node("Skill:Cross-Impact Balance", type="Skill", name="Cross-Impact Balance")

    chunks = [TextChunk("c1", "Yang uses Cross-Impact Balance.", "cv.pdf", "cv", None, 0)]

    persona = PersonaAgentSpec(agent_id="agent_1", name="Yang", role="Person perspective")
    environment = EnvironmentSpec(objective="Improve CV", rounds=1)

    class FakePersonaAgent:
        async def run(self, graph, chunks, query="", max_agents=8):
            return [persona]

    class FakeEnvironmentAgent:
        async def run(self, graph, chunks, personas, query=""):
            return environment

    class FakeLlm:
        async def chat_json(self, messages):
            prompt = messages[-1]["content"]
            # synthesis call
            if "다음 ProjectOS 페르소나 debate 로그를 종합" in prompt:
                return {
                    "graph_enhancements": {
                        "nodes": [
                            {
                                "type": "Skill",
                                "name": "Cross-Impact Balance (CIB)",
                                "description": "d",
                                "evidence": "Skill:Cross-Impact Balance",
                            }
                        ],
                        "edges": [],
                    },
                    "cv_improvements": {},
                    "report": {"title": "t", "answer": "a"},
                }
            # debate turn call
            return {
                "observation": "obs",
                "proposal": "prop",
                "evidence_refs": [],
                "responds_to": "",
                "unresolved_questions": [],
            }

    agent = ProjectSimulationAgent(
        persona_agent=FakePersonaAgent(),
        environment_agent=FakeEnvironmentAgent(),
        llm=FakeLlm(),
    )

    result = await agent.run(graph, chunks, query="q", apply_graph=True)

    node_delta = result["graph_delta"]["nodes"][0]
    assert node_delta["status"] == "skipped"
    assert "Skill:Cross-Impact Balance" in node_delta["status_reason"]
    assert "Skill:Cross-Impact Balance (CIB)" not in graph
    assert result["applied_graph_changes"]["nodes_added"] == 0
