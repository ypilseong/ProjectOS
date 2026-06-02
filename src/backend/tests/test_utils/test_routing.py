from app.config import config
from app.utils import routing
from app.utils.routing import Role, route, over_budget


def test_chunk_extraction_follows_graph_extraction_backend(monkeypatch):
    monkeypatch.setattr(config, "GRAPH_EXTRACTION_BACKEND", "local")
    assert route(Role.CHUNK_EXTRACTION) == "local"


def test_chunk_extraction_can_be_claude(monkeypatch):
    monkeypatch.setattr(config, "GRAPH_EXTRACTION_BACKEND", "claude_code")
    monkeypatch.setattr(config, "LLM_BUDGET_USD", 0.0)
    assert route(Role.CHUNK_EXTRACTION) == "claude_code"


def test_simulation_always_local(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "claude_code")
    assert route(Role.SIMULATION) == "local"


def test_other_roles_follow_global_backend(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "claude_code")
    monkeypatch.setattr(config, "LLM_BUDGET_USD", 0.0)
    assert route(Role.ANALYSIS) == "claude_code"


def test_over_budget_downgrades_claude_to_local(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "claude_code")
    monkeypatch.setattr(config, "LLM_BUDGET_USD", 1.0)
    monkeypatch.setattr(routing, "get_llm_usage", lambda: {"total_cost_usd": 2.0})
    assert over_budget() is True
    assert route(Role.ANALYSIS) == "local"


def test_zero_budget_means_unlimited(monkeypatch):
    monkeypatch.setattr(config, "LLM_BUDGET_USD", 0.0)
    monkeypatch.setattr(routing, "get_llm_usage", lambda: {"total_cost_usd": 999.0})
    assert over_budget() is False
