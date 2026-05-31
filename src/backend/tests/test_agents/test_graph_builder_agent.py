import pytest
from unittest.mock import AsyncMock, patch
import networkx as nx
from app.models.graph import TextChunk, Ontology, EntityTypeDef, EdgeTypeDef


MOCK_EXTRACT = {
    "entities": [
        {"type": "Person", "name": "Yang Pilseong", "description": "ML 연구자"},
        {"type": "Skill", "name": "Python", "description": "프로그래밍 언어"},
    ],
    "relations": [
        {
            "source": "Yang Pilseong",
            "source_type": "Person",
            "target": "Python",
            "target_type": "Skill",
            "relation": "USES_SKILL",
            "confidence": 0.95,
        }
    ],
}


@pytest.fixture
def sample_ontology():
    return Ontology(
        entity_types=[
            EntityTypeDef("Person", "사람", []),
            EntityTypeDef("Skill", "기술", []),
        ],
        edge_types=[EdgeTypeDef("USES_SKILL", "기술 사용", ["Person"], ["Skill"])],
        analysis_summary="test",
    )


@pytest.mark.asyncio
async def test_graph_builder_creates_nodes(sample_ontology):
    from app.agents.graph_builder_agent import GraphBuilderAgent

    agent = GraphBuilderAgent()
    chunks = [TextChunk("id1", "Yang Pilseong은 Python 전문가", "cv.pdf", "cv", 1, 0)]

    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_EXTRACT)):
        graph = await agent.run(chunks, sample_ontology)

    assert "Person:Yang Pilseong" in graph.nodes
    assert "Skill:Python" in graph.nodes
    assert graph.number_of_edges() >= 1


@pytest.mark.asyncio
async def test_graph_edge_has_relation(sample_ontology):
    from app.agents.graph_builder_agent import GraphBuilderAgent

    agent = GraphBuilderAgent()
    chunks = [TextChunk("id1", "test", "cv.pdf", "cv", 1, 0)]

    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_EXTRACT)):
        graph = await agent.run(chunks, sample_ontology)

    edges = list(graph.edges(data=True))
    assert len(edges) >= 1
    assert edges[0][2]["relation"] == "USES_SKILL"
    assert edges[0][2]["confidence"] == 0.95
    assert edges[0][2]["source_chunk_id"] == "id1"


@pytest.mark.asyncio
async def test_graph_nodes_track_source_chunk_ids(sample_ontology):
    from app.agents.graph_builder_agent import GraphBuilderAgent

    agent = GraphBuilderAgent()
    chunks = [TextChunk("id1", "test", "cv.pdf", "cv", 1, 0)]

    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_EXTRACT)):
        graph = await agent.run(chunks, sample_ontology)

    assert graph.nodes["Skill:Python"]["source_chunk_ids"] == ["id1"]


@pytest.mark.asyncio
async def test_graph_builder_filters_generic_person_entities(sample_ontology):
    from app.agents.graph_builder_agent import GraphBuilderAgent

    agent = GraphBuilderAgent()
    chunks = [TextChunk("id1", "저는 Python을 사용합니다", "cv.pdf", "cv", 1, 0)]
    extract = {
        "entities": [
            {"type": "Person", "name": "저", "description": "author"},
            {"type": "Person", "name": "Author", "description": "author"},
            {"type": "Skill", "name": "Python", "description": "programming"},
        ],
        "relations": [],
    }

    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=extract)):
        graph = await agent.run(chunks, sample_ontology)

    assert "Person:저" not in graph.nodes
    assert "Person:Author" not in graph.nodes
    assert "Skill:Python" in graph.nodes


@pytest.mark.asyncio
async def test_graph_builder_normalizes_combined_user_person_name(tmp_path, monkeypatch, sample_ontology):
    import json
    from app.agents.graph_builder_agent import GraphBuilderAgent

    user_json = tmp_path / "user.json"
    user_json.write_text(json.dumps({"name": "양필성", "display_name": "Pilseong Yang"}))
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    agent = GraphBuilderAgent()
    chunks = [TextChunk("id1", "양필성 / Pilseong Yang은 Python을 사용합니다", "cv.pdf", "cv", 1, 0)]
    extract = {
        "entities": [
            {"type": "Person", "name": "양필성 / Pilseong Yang", "description": "document owner"},
            {"type": "Skill", "name": "Python", "description": "programming"},
        ],
        "relations": [
            {
                "source": "양필성 / Pilseong Yang",
                "source_type": "Person",
                "target": "Python",
                "target_type": "Skill",
                "relation": "USES_SKILL",
            }
        ],
    }

    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=extract)):
        graph = await agent.run(chunks, sample_ontology)

    assert "Person:양필성" in graph.nodes
    assert "Person:양필성 / Pilseong Yang" not in graph.nodes
    assert graph.has_edge("Person:양필성", "Skill:Python")


def test_user_context_includes_both_names(tmp_path, monkeypatch):
    import json
    from app.agents.graph_builder_agent import GraphBuilderAgent

    user_json = tmp_path / "user.json"
    user_json.write_text(json.dumps({"name": "양필성", "display_name": "Pilseong Yang"}))
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    agent = GraphBuilderAgent()
    assert "양필성" in agent._user_context
    assert "Pilseong Yang" in agent._user_context
    assert "implicit subject" in agent._user_context


def test_user_context_includes_aliases(tmp_path, monkeypatch):
    import json
    from app.agents.graph_builder_agent import GraphBuilderAgent

    user_json = tmp_path / "user.json"
    user_json.write_text(json.dumps({
        "name": "양필성",
        "display_name": "Pilseong Yang",
        "aliases": ["Phil"],
    }))
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    agent = GraphBuilderAgent()
    assert "Phil" in agent._user_context


def test_user_context_empty_when_no_user_json(tmp_path, monkeypatch):
    from app.agents.graph_builder_agent import GraphBuilderAgent

    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(tmp_path / "missing.json"))
    agent = GraphBuilderAgent()
    assert agent._user_context == ""


def test_graph_builder_uses_local_llm_for_bulk_extraction(monkeypatch):
    from app.agents.graph_builder_agent import GraphBuilderAgent
    from app.utils.llm_client import _OpenAIBackend

    monkeypatch.setattr("app.config.config.LLM_BACKEND", "claude_code")
    monkeypatch.setattr("app.config.config.GRAPH_EXTRACTION_BACKEND", "local")

    agent = GraphBuilderAgent()

    assert isinstance(agent._llm._impl, _OpenAIBackend)


def test_graph_builder_can_use_claude_for_explicit_e2e_test(monkeypatch):
    from app.agents.graph_builder_agent import GraphBuilderAgent
    from app.utils.llm_client import _ClaudeCodeBackend

    monkeypatch.setattr("app.config.config.GRAPH_EXTRACTION_BACKEND", "claude_code")

    agent = GraphBuilderAgent()

    assert isinstance(agent._llm._impl, _ClaudeCodeBackend)
    assert agent._llm._impl.disable_plugins is True


@pytest.mark.asyncio
async def test_prompt_contains_user_context(tmp_path, monkeypatch, sample_ontology):
    import json
    from app.agents.graph_builder_agent import GraphBuilderAgent

    user_json = tmp_path / "user.json"
    user_json.write_text(json.dumps({"name": "양필성", "display_name": "Pilseong Yang"}))
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    agent = GraphBuilderAgent()
    chunk = TextChunk("id1", "● Total GPA 4.35/4.50", "cv.pdf", "pdf", 1, 0)

    captured = {}

    async def fake_chat_json(messages, **kw):
        captured["prompt"] = messages[0]["content"]
        return {"entities": [], "relations": []}

    with patch.object(agent._llm, "chat_json", side_effect=fake_chat_json):
        await agent._extract_from_chunk(chunk, ["Person", "Achievement"], ["ACHIEVED"])

    assert "양필성" in captured["prompt"]
    assert "Pilseong Yang" in captured["prompt"]


def test_fuzzy_match_finds_similar():
    from app.agents.graph_builder_agent import GraphBuilderAgent
    import networkx as nx

    agent = GraphBuilderAgent()
    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong")

    # Exact match (different case)
    existing = agent._find_existing_node(g, "Person", "yang pilseong")
    assert existing == "Person:Yang Pilseong"


def test_relation_type_aliases_common_llm_typo():
    from app.agents.graph_builder_agent import GraphBuilderAgent

    assert GraphBuilderAgent._normalize_relation_type("LEAD_BY") == "LED_BY"
    assert GraphBuilderAgent._normalize_relation_type(None) == ""


def test_used_in_relation_is_reversed_to_project_uses_skill():
    from app.agents.graph_builder_agent import GraphBuilderAgent

    agent = GraphBuilderAgent()
    relation, src_type, src_name, tgt_type, tgt_name = agent._normalize_relation(
        "USED_IN", "Skill", "NLP", "Project", "Speaker Identification"
    )

    assert relation == "USES_SKILL"
    assert (src_type, src_name) == ("Project", "Speaker Identification")
    assert (tgt_type, tgt_name) == ("Skill", "NLP")


def test_normalize_entity_name_only_cleans_whitespace():
    from app.agents.graph_builder_agent import GraphBuilderAgent

    agent = GraphBuilderAgent()

    assert agent._normalize_entity_name("Skill", "  NLP   method ") == "NLP method"
    assert agent._normalize_entity_name("Skill", "자연어처리") == "자연어처리"


def test_applied_to_relation_is_normalized_to_project_uses_skill():
    from app.agents.graph_builder_agent import GraphBuilderAgent

    agent = GraphBuilderAgent()
    relation, src_type, src_name, tgt_type, tgt_name = agent._normalize_relation(
        "APPLIED_TO", "Skill", "NLP", "Project", "Speaker Identification"
    )

    assert relation == "USES_SKILL"
    assert (src_type, src_name) == ("Project", "Speaker Identification")
    assert (tgt_type, tgt_name) == ("Skill", "NLP")


def test_has_role_relation_is_preserved():
    from app.agents.graph_builder_agent import GraphBuilderAgent

    assert GraphBuilderAgent._normalize_relation_type("HAS_ROLE") == "HAS_ROLE"


def test_fuzzy_match_no_match():
    from app.agents.graph_builder_agent import GraphBuilderAgent
    import networkx as nx

    agent = GraphBuilderAgent()
    g = nx.DiGraph()
    g.add_node("Person:Kim Chulsoo", type="Person", name="Kim Chulsoo")

    existing = agent._find_existing_node(g, "Person", "Lee Younghee")
    assert existing is None


def test_fuzzy_match_wrong_type():
    from app.agents.graph_builder_agent import GraphBuilderAgent
    import networkx as nx

    agent = GraphBuilderAgent()
    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong")

    # Same name but wrong type — should not match
    existing = agent._find_existing_node(g, "Skill", "Yang Pilseong")
    assert existing is None


def test_graph_stats():
    from app.agents.graph_builder_agent import GraphBuilderAgent
    import networkx as nx

    agent = GraphBuilderAgent()
    g = nx.DiGraph()
    g.add_node("Person:A", type="Person", name="A")
    g.add_node("Skill:B", type="Skill", name="B")
    g.add_edge("Person:A", "Skill:B", relation="USES_SKILL")

    stats = agent.get_stats(g)
    assert stats.total_nodes == 2
    assert stats.total_edges == 1
    assert stats.nodes_by_type["Person"] == 1
    assert stats.edges_by_type["USES_SKILL"] == 1


def test_save_and_load_graph(tmp_path):
    from app.agents.graph_builder_agent import GraphBuilderAgent
    import networkx as nx
    import json

    agent = GraphBuilderAgent()
    g = nx.DiGraph()
    g.add_node("Person:A", type="Person", name="A", description="test",
               source_files=["cv.pdf"], attributes={})
    path = str(tmp_path / "graph.json")
    agent.save(g, path)

    assert (tmp_path / "graph.json").exists()
    data = json.loads((tmp_path / "graph.json").read_text())
    assert "nodes" in data
