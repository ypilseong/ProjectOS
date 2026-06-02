from app.utils import llm_client as lc
from app.utils.routing import Role


def _spy_for_role(monkeypatch):
    calls = []
    orig = lc.LLMClient.for_role.__func__

    def spy(cls, role, disable_plugins=False):
        calls.append(role)
        return orig(cls, role, disable_plugins)

    monkeypatch.setattr(lc.LLMClient, "for_role", classmethod(spy))
    return calls


def test_ontology_agent_uses_ontology_role(monkeypatch):
    calls = _spy_for_role(monkeypatch)
    from app.agents.ontology_agent import OntologyAgent

    OntologyAgent()
    assert Role.ONTOLOGY in calls


def test_graph_builder_uses_chunk_extraction_role(monkeypatch):
    calls = _spy_for_role(monkeypatch)
    from app.agents.graph_builder_agent import GraphBuilderAgent

    GraphBuilderAgent()
    assert Role.CHUNK_EXTRACTION in calls


def test_query_agent_uses_query_role(monkeypatch):
    calls = _spy_for_role(monkeypatch)
    from app.agents.query_agent import QueryAgent

    QueryAgent()
    assert Role.QUERY in calls
