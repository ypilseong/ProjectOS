import networkx as nx

from app.agents.simulation_agent import (
    EnvironmentSpec,
    PersonaAgentSpec,
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
