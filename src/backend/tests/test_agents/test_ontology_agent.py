import pytest
from unittest.mock import AsyncMock, patch


MOCK_RESPONSE = {
    "entity_types": [
        {"name": "Person", "description": "사람 엔티티", "examples": ["Yang Pilseong"]},
        {"name": "Skill", "description": "기술 스택", "examples": ["Python"]},
    ],
    "edge_types": [
        {
            "name": "USES_SKILL",
            "description": "기술 사용 관계",
            "source_types": ["Person"],
            "target_types": ["Skill"],
        }
    ],
    "analysis_summary": "커리어 중심 온톨로지",
}


@pytest.mark.asyncio
async def test_ontology_agent_output():
    from app.agents.ontology_agent import OntologyAgent
    from app.models.graph import TextChunk

    agent = OntologyAgent()
    chunks = [TextChunk("id1", "Yang Pilseong은 Python 전문가", "cv.pdf", "cv", 1, 0)]

    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_RESPONSE)):
        ontology = await agent.run(chunks)

    assert len(ontology.entity_types) == 2
    assert ontology.entity_types[0].name == "Person"
    assert ontology.edge_types[0].name == "USES_SKILL"
    assert ontology.edge_types[0].source_types == ["Person"]
    assert ontology.analysis_summary == "커리어 중심 온톨로지"


@pytest.mark.asyncio
async def test_ontology_entity_type_def_fields():
    from app.agents.ontology_agent import OntologyAgent
    from app.models.graph import TextChunk

    agent = OntologyAgent()
    chunks = [TextChunk("id1", "test", "cv.pdf", "cv", 1, 0)]

    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_RESPONSE)):
        ontology = await agent.run(chunks)

    et = ontology.entity_types[0]
    assert et.name == "Person"
    assert et.description == "사람 엔티티"
    assert et.examples == ["Yang Pilseong"]


def test_ontology_has_fixed_types():
    from app.agents.ontology_agent import OntologyAgent
    agent = OntologyAgent()
    assert "Person" in agent.FIXED_ENTITY_TYPES
    assert "Project" in agent.FIXED_ENTITY_TYPES
    assert "Skill" in agent.FIXED_ENTITY_TYPES
    assert "Organization" in agent.FIXED_ENTITY_TYPES
    assert "Publication" in agent.FIXED_ENTITY_TYPES
    assert len(agent.FIXED_ENTITY_TYPES) == 10


def test_ontology_has_fixed_edge_types():
    from app.agents.ontology_agent import OntologyAgent
    agent = OntologyAgent()
    assert "WORKED_AT" in agent.FIXED_EDGE_TYPES
    assert "USES_SKILL" in agent.FIXED_EDGE_TYPES
    assert "DEVELOPED" in agent.FIXED_EDGE_TYPES
    assert len(agent.FIXED_EDGE_TYPES) == 10


@pytest.mark.asyncio
async def test_sample_truncated_to_max():
    from app.agents.ontology_agent import OntologyAgent
    from app.models.graph import TextChunk
    from app.config import config

    agent = OntologyAgent()
    big_chunks = [
        TextChunk(f"id{i}", "X" * 1000, "cv.pdf", "cv", i, i * 1000)
        for i in range(100)
    ]
    sample = agent._build_sample(big_chunks)
    assert len(sample) <= config.MAX_ONTOLOGY_SAMPLE_CHARS
