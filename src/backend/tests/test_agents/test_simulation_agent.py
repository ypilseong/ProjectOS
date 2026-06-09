import networkx as nx
import pytest

from app.agents.simulation_agent import (
    EnvironmentSpec,
    PersonaAgentSpec,
    ProjectSimulationAgent,
    apply_graph_enhancements,
    fallback_simulation_result,
)
from app.models.graph import TextChunk


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
