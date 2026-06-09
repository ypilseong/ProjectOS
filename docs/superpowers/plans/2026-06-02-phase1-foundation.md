# Phase 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ProjectOS의 LLM 백엔드 선택을 중앙화한 라우팅 정책 테이블 + 비용 budget guard, 빌드/쿼리 결정 trace 로깅, 에이전트 skills descriptor 카탈로그를 추가해 Phase 2(자동화)·Phase 3(상호운용/학습)의 토대를 만든다.

**Architecture:** 세 개의 작은 순수 모듈(`routing.py`, `trace.py`, `skills.py`)을 신규 추가하고, 흩어진 `LLMClient()` / `LLMClient(backend=...)` 호출을 `LLMClient.for_role(Role.X)` 팩토리로 교체한다. 라우팅은 기존 동작(chunk 추출=`GRAPH_EXTRACTION_BACKEND`, simulation=local, 그 외=`LLM_BACKEND`)을 그대로 보존하되, Claude 누적 비용이 budget을 넘으면 claude_code→local로 자동 강등한다. trace는 프로젝트별 `traces.jsonl`에 append-only로 기록한다.

**Tech Stack:** Python 3.14, FastAPI, pydantic-settings, pytest, NetworkX (기존 스택 그대로). 신규 외부 의존성 없음.

**모든 명령은 `src/backend/`에서 실행한다.**

---

## File Structure

신규 생성:
- `src/backend/app/utils/routing.py` — Role 상수 + `route()` + `over_budget()` (LLM 백엔드 라우팅 단일 진입점)
- `src/backend/app/utils/trace.py` — `record_trace()` + `read_traces()` (프로젝트별 결정 trace sink)
- `src/backend/app/api/skills.py` — `GET /api/skills` 라우터
- `src/backend/app/skills.py` — `SkillDescriptor` + `CATALOG` (에이전트 메타데이터)
- 테스트: `tests/test_utils/test_routing.py`, `tests/test_utils/test_trace.py`, `tests/test_utils/test_skills_catalog.py`, `tests/test_agents/test_role_routing.py`, `tests/test_api/test_traces_api.py`, `tests/test_api/test_skills_api.py`

수정:
- `src/backend/app/config.py` — `LLM_BUDGET_USD` 추가
- `src/backend/app/utils/llm_client.py` — `LLMClient.for_role()` 팩토리 추가
- `src/backend/app/agents/{ontology,profile,query,analysis,graph_builder,simulation}_agent.py` — `for_role`로 교체
- `src/backend/app/utils/{llm_dedup,entity_canonicalization,achievement_refinement}.py` — `for_role`로 교체
- `src/backend/app/api/graph.py` — `_run_graph`에 trace 기록 + `GET /{project_id}/traces` 추가
- `src/backend/app/main.py` — skills 라우터 등록

---

## Group A — Constraint-aware Routing + Budget Guard

### Task 1: Routing 모듈 + budget guard

**Files:**
- Modify: `src/backend/app/config.py:25` (LLM_THINKING_MODE 줄 다음)
- Create: `src/backend/app/utils/routing.py`
- Test: `src/backend/tests/test_utils/test_routing.py`

- [ ] **Step 1: config에 budget 필드 추가**

`src/backend/app/config.py`의 `LLM_THINKING_MODE: bool = True` 줄 바로 다음에 추가:

```python
    LLM_BUDGET_USD: float = 0.0  # 0 = unlimited; Claude 누적 비용이 이 값을 넘으면 local로 강등
```

- [ ] **Step 2: 실패하는 테스트 작성**

`src/backend/tests/test_utils/test_routing.py` 생성:

```python
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
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_utils/test_routing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.utils.routing'`

- [ ] **Step 4: routing 모듈 구현**

`src/backend/app/utils/routing.py` 생성:

```python
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
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_utils/test_routing.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: 커밋**

```bash
git add app/config.py app/utils/routing.py tests/test_utils/test_routing.py
git commit -m "feat: add constraint-aware LLM routing policy with budget guard"
```

---

### Task 2: `LLMClient.for_role()` 팩토리

**Files:**
- Modify: `src/backend/app/utils/llm_client.py:283-291` (`LLMClient.__init__` 다음)
- Test: `src/backend/tests/test_utils/test_llm_client.py` (기존 파일에 추가)

- [ ] **Step 1: 실패하는 테스트 추가**

`src/backend/tests/test_utils/test_llm_client.py` 끝에 추가:

```python
def test_for_role_local(monkeypatch):
    from app.utils import llm_client as lc
    monkeypatch.setattr("app.utils.routing.route", lambda role: "local")
    client = lc.LLMClient.for_role("anything")
    assert isinstance(client._impl, lc._OpenAIBackend)


def test_for_role_claude(monkeypatch):
    from app.utils import llm_client as lc
    monkeypatch.setattr("app.utils.routing.route", lambda role: "claude_code")
    client = lc.LLMClient.for_role("anything")
    assert isinstance(client._impl, lc._ClaudeCodeBackend)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_utils/test_llm_client.py::test_for_role_local -v`
Expected: FAIL with `AttributeError: type object 'LLMClient' has no attribute 'for_role'`

- [ ] **Step 3: 팩토리 구현**

`src/backend/app/utils/llm_client.py`의 `LLMClient.__init__` 메서드(현재 284-291줄) 다음에 추가:

```python
    @classmethod
    def for_role(cls, role: str, disable_plugins: bool = False) -> "LLMClient":
        from app.utils.routing import route

        return cls(backend=route(role), disable_plugins=disable_plugins)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_utils/test_llm_client.py -v`
Expected: PASS (기존 + 2 신규 통과)

- [ ] **Step 5: 커밋**

```bash
git add app/utils/llm_client.py tests/test_utils/test_llm_client.py
git commit -m "feat: add LLMClient.for_role factory routing by task role"
```

---

### Task 3: 에이전트 호출부를 `for_role`로 마이그레이션

기존 동작을 바꾸지 않고(behavior-preserving) 백엔드 선택을 라우팅으로 일원화한다.

**Files:**
- Modify: `src/backend/app/agents/ontology_agent.py:21`
- Modify: `src/backend/app/agents/profile_agent.py:15`
- Modify: `src/backend/app/agents/query_agent.py:15`
- Modify: `src/backend/app/agents/analysis_agent.py:18`
- Modify: `src/backend/app/agents/graph_builder_agent.py:28-31`
- Modify: `src/backend/app/agents/simulation_agent.py:42,127,195`
- Modify: `src/backend/app/utils/llm_dedup.py:98`
- Modify: `src/backend/app/utils/entity_canonicalization.py:35`
- Modify: `src/backend/app/utils/achievement_refinement.py:39`
- Test: `src/backend/tests/test_agents/test_role_routing.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/backend/tests/test_agents/test_role_routing.py` 생성:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_agents/test_role_routing.py -v`
Expected: FAIL — 에이전트들이 아직 `for_role`를 호출하지 않으므로 `assert ... in calls` 실패

- [ ] **Step 3: ontology_agent 교체**

`src/backend/app/agents/ontology_agent.py:21`
변경 전: `        self._llm = LLMClient()`
변경 후:
```python
        self._llm = LLMClient.for_role(Role.ONTOLOGY)
```
파일 상단 import 영역에 추가: `from app.utils.routing import Role`

- [ ] **Step 4: profile_agent 교체**

`src/backend/app/agents/profile_agent.py:15`
변경 전: `        self._llm = LLMClient()`
변경 후:
```python
        self._llm = LLMClient.for_role(Role.PROFILE)
```
import 추가: `from app.utils.routing import Role`

- [ ] **Step 5: query_agent 교체**

`src/backend/app/agents/query_agent.py:15`
변경 전: `        self._llm = LLMClient()`
변경 후:
```python
        self._llm = LLMClient.for_role(Role.QUERY)
```
import 추가: `from app.utils.routing import Role`

- [ ] **Step 6: analysis_agent 교체**

`src/backend/app/agents/analysis_agent.py:18`
변경 전: `        self._llm = LLMClient()`
변경 후:
```python
        self._llm = LLMClient.for_role(Role.ANALYSIS)
```
import 추가: `from app.utils.routing import Role`

- [ ] **Step 7: graph_builder_agent 교체**

`src/backend/app/agents/graph_builder_agent.py:28-31`
변경 전:
```python
        self._llm = LLMClient(
            backend=config.GRAPH_EXTRACTION_BACKEND,
            disable_plugins=config.CLAUDE_GRAPH_DISABLE_PLUGINS,
        )
```
변경 후:
```python
        self._llm = LLMClient.for_role(
            Role.CHUNK_EXTRACTION,
            disable_plugins=config.CLAUDE_GRAPH_DISABLE_PLUGINS,
        )
```
import 추가: `from app.utils.routing import Role`
(라우팅이 `Role.CHUNK_EXTRACTION` → `config.GRAPH_EXTRACTION_BACKEND`로 매핑하므로 동작 동일)

- [ ] **Step 8: simulation_agent 교체 (3곳)**

`src/backend/app/agents/simulation_agent.py`의 42, 127, 195줄 각각:
변경 전: `        self._llm = llm or LLMClient(backend="local")`
변경 후:
```python
        self._llm = llm or LLMClient.for_role(Role.SIMULATION)
```
import 추가: `from app.utils.routing import Role`
(`replace_all`로 3곳 일괄 교체 가능)

- [ ] **Step 9: 유틸 3개 교체**

`src/backend/app/utils/llm_dedup.py:98`
변경 전: `        llm_client = LLMClient()`
변경 후: `        llm_client = LLMClient.for_role(Role.DEDUP)`
import 추가: `from app.utils.routing import Role`

`src/backend/app/utils/entity_canonicalization.py:35`
변경 전: `        llm_client = LLMClient()`
변경 후: `        llm_client = LLMClient.for_role(Role.CANONICAL)`
import 추가: `from app.utils.routing import Role`

`src/backend/app/utils/achievement_refinement.py:39`
변경 전: `        llm_client = LLMClient()`
변경 후: `        llm_client = LLMClient.for_role(Role.REFINEMENT)`
import 추가: `from app.utils.routing import Role`

- [ ] **Step 10: 마이그레이션 테스트 통과 확인**

Run: `python3 -m pytest tests/test_agents/test_role_routing.py -v`
Expected: PASS (3 passed)

- [ ] **Step 11: 회귀 없는지 전체 테스트**

Run: `python3 -m pytest tests/ -q`
Expected: 기존 통과 수 + 신규 통과 (실패 0). 동작 보존이므로 기존 테스트가 모두 통과해야 함.

- [ ] **Step 12: 커밋**

```bash
git add app/agents/ app/utils/llm_dedup.py app/utils/entity_canonicalization.py app/utils/achievement_refinement.py tests/test_agents/test_role_routing.py
git commit -m "refactor: route all agent LLM clients through for_role"
```

---

## Group B — Decision Trace Logging

### Task 4: Trace sink 모듈

**Files:**
- Create: `src/backend/app/utils/trace.py`
- Test: `src/backend/tests/test_utils/test_trace.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/backend/tests/test_utils/test_trace.py` 생성:

```python
from app.config import config
from app.utils.trace import record_trace, read_traces


def test_record_and_read_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    record_trace("proj1", "graph_build", backend="local", nodes=10, edges=12)
    record_trace("proj1", "query", backend="claude_code", cost_usd=0.05)
    traces = read_traces("proj1")
    assert len(traces) == 2
    assert traces[0]["operation"] == "graph_build"
    assert traces[0]["nodes"] == 10
    assert traces[1]["backend"] == "claude_code"
    assert "timestamp" in traces[0]


def test_read_missing_project_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    assert read_traces("nope") == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_utils/test_trace.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.utils.trace'`

- [ ] **Step 3: trace 모듈 구현**

`src/backend/app/utils/trace.py` 생성:

```python
import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import config


def _trace_path(project_id: str) -> Path:
    return Path(config.PROJECTS_DIR) / project_id / "traces.jsonl"


def record_trace(project_id: str, operation: str, **fields) -> dict:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "operation": operation,
        **fields,
    }
    path = _trace_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_traces(project_id: str) -> list[dict]:
    path = _trace_path(project_id)
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_utils/test_trace.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/utils/trace.py tests/test_utils/test_trace.py
git commit -m "feat: add append-only decision trace sink"
```

---

### Task 5: 그래프 빌드에 trace 기록 연결

빌드 시작 시 누적 usage를 스냅샷하고, 완료 시 비용 델타 + 노드/엣지 수를 trace로 기록한다.

**Files:**
- Modify: `src/backend/app/api/graph.py` (`_run_graph` 시작부 ~238줄, 완료부 441-447줄)

- [ ] **Step 1: 빌드 시작 시 usage 스냅샷 추가**

`src/backend/app/api/graph.py`의 `_run_graph` 안, 다음 줄
```python
        task_manager.update(task_id, status=TaskStatus.RUNNING, message="그래프 구축 시작", progress=10)
```
바로 다음에 추가:
```python
        from app.utils.llm_client import get_llm_usage
        from app.utils.trace import record_trace
        from app.utils.routing import Role, route

        usage_before = get_llm_usage().get("total_cost_usd", 0.0)
```

- [ ] **Step 2: 완료 시 trace 기록 추가**

같은 함수에서 다음 블록(441-447줄)
```python
            project_store.save(project)
        task_manager.update(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=f"완료: 노드 {stats.total_nodes}개, 엣지 {stats.total_edges}개",
        )
```
의 `project_store.save(project)` 다음, `task_manager.update(... COMPLETED ...)` 앞에 삽입:
```python
        cost_delta = get_llm_usage().get("total_cost_usd", 0.0) - usage_before
        record_trace(
            project_id,
            "graph_build",
            backend=route(Role.CHUNK_EXTRACTION),
            incremental=incremental,
            nodes=stats.total_nodes,
            edges=stats.total_edges,
            cost_usd=round(cost_delta, 6),
        )
```

- [ ] **Step 3: 구문/임포트 확인**

Run: `python3 -c "import app.api.graph"`
Expected: 오류 없이 종료 (exit 0)

- [ ] **Step 4: 전체 테스트로 회귀 확인**

Run: `python3 -m pytest tests/ -q`
Expected: 실패 0

- [ ] **Step 5: 커밋**

```bash
git add app/api/graph.py
git commit -m "feat: record graph build cost/size trace on completion"
```

---

### Task 6: `GET /api/projects/{id}/traces` 엔드포인트

**Files:**
- Modify: `src/backend/app/api/graph.py` (라우터에 엔드포인트 추가)
- Test: `src/backend/tests/test_api/test_traces_api.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/backend/tests/test_api/test_traces_api.py` 생성:

```python
from fastapi.testclient import TestClient

from app.config import config
from app.main import app
from app.utils.trace import record_trace


def test_get_traces_returns_records(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    record_trace("p1", "graph_build", backend="local", nodes=3, edges=2)
    client = TestClient(app)
    resp = client.get("/api/projects/p1/traces")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["traces"]) == 1
    assert body["traces"][0]["operation"] == "graph_build"


def test_get_traces_empty_for_unknown_project(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    client = TestClient(app)
    resp = client.get("/api/projects/unknown/traces")
    assert resp.status_code == 200
    assert resp.json() == {"traces": []}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_api/test_traces_api.py -v`
Expected: FAIL — 엔드포인트가 없어 404 반환

- [ ] **Step 3: 엔드포인트 구현**

`src/backend/app/api/graph.py`의 `router`에 엔드포인트 추가 (기존 `@router.get(...)` 엔드포인트들과 같은 위치, 예: `_run_graph` 정의 위쪽 라우트 모음 영역). `router`가 `APIRouter()`로 정의된 것을 확인 후 추가:

```python
@router.get("/{project_id}/traces")
async def get_traces(project_id: str):
    from app.utils.trace import read_traces

    return {"traces": read_traces(project_id)}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_api/test_traces_api.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/api/graph.py tests/test_api/test_traces_api.py
git commit -m "feat: add GET project traces endpoint"
```

---

## Group C — Skills Descriptor Catalog

### Task 7: Skills 카탈로그 모듈

**Files:**
- Create: `src/backend/app/skills.py`
- Test: `src/backend/tests/test_utils/test_skills_catalog.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/backend/tests/test_utils/test_skills_catalog.py` 생성:

```python
from app.skills import CATALOG, catalog_as_dicts
from app.utils.routing import Role

_VALID_ROLES = {
    Role.CHUNK_EXTRACTION, Role.ONTOLOGY, Role.PROFILE, Role.QUERY,
    Role.ANALYSIS, Role.DEDUP, Role.CANONICAL, Role.REFINEMENT,
    Role.SIMULATION, Role.DIGEST,
}
_VALID_COST = {"low", "high"}
_VALID_MODE = {"on_demand", "scheduled", "continuous"}


def test_catalog_not_empty():
    assert len(CATALOG) >= 6


def test_skill_names_unique():
    names = [s.name for s in CATALOG]
    assert len(names) == len(set(names))


def test_every_skill_has_valid_fields():
    for s in CATALOG:
        assert s.role in _VALID_ROLES
        assert s.cost_profile in _VALID_COST
        assert s.execution_mode in _VALID_MODE
        assert s.inputs and s.outputs
        assert s.description


def test_catalog_as_dicts_is_json_serializable():
    import json
    json.dumps(catalog_as_dicts())
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_utils/test_skills_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.skills'`

- [ ] **Step 3: 카탈로그 구현**

`src/backend/app/skills.py` 생성:

```python
from dataclasses import asdict, dataclass

from app.utils.routing import Role


@dataclass
class SkillDescriptor:
    name: str
    description: str
    inputs: list[str]
    outputs: list[str]
    role: str
    cost_profile: str  # "low" | "high"
    execution_mode: str  # "on_demand" | "scheduled" | "continuous"


CATALOG: list[SkillDescriptor] = [
    SkillDescriptor(
        name="parse_documents",
        description="업로드된 PDF/DOCX/TXT를 청크로 분해한다.",
        inputs=["file_paths"],
        outputs=["chunks"],
        role=Role.CHUNK_EXTRACTION,
        cost_profile="low",
        execution_mode="on_demand",
    ),
    SkillDescriptor(
        name="build_ontology",
        description="청크 샘플에서 엔티티/관계 타입 온톨로지를 정의한다.",
        inputs=["chunks"],
        outputs=["ontology"],
        role=Role.ONTOLOGY,
        cost_profile="high",
        execution_mode="on_demand",
    ),
    SkillDescriptor(
        name="build_graph",
        description="청크+온톨로지에서 NetworkX 지식 그래프를 구축한다.",
        inputs=["chunks", "ontology"],
        outputs=["graph"],
        role=Role.CHUNK_EXTRACTION,
        cost_profile="high",
        execution_mode="on_demand",
    ),
    SkillDescriptor(
        name="query_career_graph",
        description="자연어 질문에 그래프+vault 컨텍스트로 답한다.",
        inputs=["question", "graph"],
        outputs=["answer_stream"],
        role=Role.QUERY,
        cost_profile="high",
        execution_mode="on_demand",
    ),
    SkillDescriptor(
        name="run_analysis",
        description="문서의 약점을 분석하고 개선 초안을 생성한다.",
        inputs=["chunks", "graph"],
        outputs=["issues", "improved_draft"],
        role=Role.ANALYSIS,
        cost_profile="high",
        execution_mode="on_demand",
    ),
    SkillDescriptor(
        name="simulate_persona",
        description="그래프 노드에서 페르소나 에이전트를 구성해 멀티에이전트 시뮬레이션을 실행한다.",
        inputs=["graph", "chunks", "query"],
        outputs=["persona_specs", "timeline"],
        role=Role.SIMULATION,
        cost_profile="low",
        execution_mode="on_demand",
    ),
]


def catalog_as_dicts() -> list[dict]:
    return [asdict(s) for s in CATALOG]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_utils/test_skills_catalog.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/skills.py tests/test_utils/test_skills_catalog.py
git commit -m "feat: add agent skills descriptor catalog"
```

---

### Task 8: `GET /api/skills` 엔드포인트

**Files:**
- Create: `src/backend/app/api/skills.py`
- Modify: `src/backend/app/main.py:3,29` (import + 라우터 등록)
- Test: `src/backend/tests/test_api/test_skills_api.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/backend/tests/test_api/test_skills_api.py` 생성:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_get_skills_returns_catalog():
    client = TestClient(app)
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    body = resp.json()
    assert "skills" in body
    assert len(body["skills"]) >= 6
    names = {s["name"] for s in body["skills"]}
    assert "query_career_graph" in names
    for s in body["skills"]:
        assert {"name", "role", "cost_profile", "execution_mode"} <= set(s.keys())
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_api/test_skills_api.py -v`
Expected: FAIL — `/api/skills` 라우트 없어 404

- [ ] **Step 3: skills 라우터 구현**

`src/backend/app/api/skills.py` 생성:

```python
from fastapi import APIRouter

from app.skills import catalog_as_dicts

router = APIRouter()


@router.get("")
async def list_skills():
    return {"skills": catalog_as_dicts()}
```

- [ ] **Step 4: main.py에 라우터 등록**

`src/backend/app/main.py:3`
변경 전: `from app.api import projects, graph, chat, tasks, user, settings`
변경 후:
```python
from app.api import projects, graph, chat, tasks, user, settings, skills
```

`src/backend/app/main.py`의 라우터 등록 블록(29줄 `tasks.router` 등록 다음)에 추가:
```python
app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_api/test_skills_api.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: 전체 테스트 + 빌드 확인**

Run: `python3 -m pytest tests/ -q`
Expected: 실패 0

- [ ] **Step 7: 커밋**

```bash
git add app/api/skills.py app/main.py tests/test_api/test_skills_api.py
git commit -m "feat: expose GET /api/skills catalog endpoint"
```

---

## 완료 후 마무리

- [ ] **handoff 갱신**: `docs/claude-code-handoff.md`에 이번 Phase 1 구현 세션 항목 추가 (변경 내역 + 검증 결과 + 다음 작업 후보=Phase 2 Digest/Watcher). CLAUDE.md 규칙.
- [ ] **전체 검증**: `python3 -m pytest tests/ -q` 최종 실행, 실패 0 확인.

---

## Self-Review 결과

- **Spec 커버리지**: 방향성 문서 §5 Phase 1의 세 항목 모두 매핑됨 — constraint-aware routing+budget(Task 1-3), trace 로깅(Task 4-6), skills descriptor(Task 7-8). §4.5(라우팅 일반화)·§4.4(trace)·§4.3(skills 표준) 충족.
- **Placeholder 스캔**: TODO/TBD/"적절히 처리" 류 없음. 모든 코드 스텝에 실제 코드 포함.
- **타입 일관성**: `Role.*` 상수는 Task 1에서 정의 후 Task 3·5·7에서 동일 명칭 사용. `record_trace`/`read_traces` 시그니처는 Task 4 정의와 Task 5·6 사용이 일치. `for_role(role, disable_plugins=False)`는 Task 2 정의와 Task 3 사용이 일치.
- **비목표 확인**: learning loop 자동 튜닝·OAuth·digest·watcher는 Phase 2/3로 의도적으로 제외(이 계획 범위 밖).
