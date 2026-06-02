from app.config import config
from app.utils.llm_client import get_llm_usage


class Role:
    CHUNK_EXTRACTION = "chunk_extraction"
    ONTOLOGY = "ontology"
    PROFILE = "profile"
    QUERY = "query"
    ANALYSIS = "analysis"
    DEDUP = "dedup"
    CANONICAL = "canonical"
    REFINEMENT = "refinement"
    SIMULATION = "simulation"
    DIGEST = "digest"


def _policy_backend(role: str) -> str:
    """현재 동작을 그대로 보존하는 기본 정책."""
    if role == Role.CHUNK_EXTRACTION:
        return config.GRAPH_EXTRACTION_BACKEND
    if role == Role.SIMULATION:
        return "local"
    return config.LLM_BACKEND


def over_budget() -> bool:
    budget = config.LLM_BUDGET_USD
    if budget <= 0:
        return False
    spent = get_llm_usage().get("total_cost_usd", 0.0)
    return spent >= budget


def route(role: str) -> str:
    backend = _policy_backend(role)
    if backend == "claude_code" and over_budget():
        return "local"
    return backend
