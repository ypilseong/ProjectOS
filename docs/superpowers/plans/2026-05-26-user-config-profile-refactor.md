# User Config + Profile Generation Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자 설정(user.json)을 추가하고, 그래프 빌드와 프로필 생성을 분리하며, Role 추출 기준을 공식 직함으로 좁힌다.

**Architecture:** 최초 방문 시 이름을 저장하는 `/api/user` 엔드포인트 추가 → 그래프 빌드는 graph.json + vault 초기 생성만 수행 → 별도 `/api/projects/{id}/profiles` 엔드포인트가 user.json 기반 fuzzy match로 Person 노드를 찾아 프로필 생성 + vault 업데이트.

**Tech Stack:** FastAPI, NetworkX, difflib.SequenceMatcher, Vue 3, Element Plus

---

## File Map

| 파일 | 변경 유형 | 역할 |
|------|----------|------|
| `src/backend/app/config.py` | 변경 | `USER_CONFIG_PATH` 추가 |
| `src/backend/app/api/user.py` | 신규 | `GET/POST /api/user` |
| `src/backend/app/main.py` | 변경 | user_router 등록 |
| `src/backend/tests/conftest.py` | 변경 | USER_CONFIG_PATH 테스트 격리 |
| `src/backend/tests/test_api/test_user_api.py` | 신규 | user API 테스트 |
| `src/backend/app/agents/obsidian_writer_agent.py` | 변경 | `profiles` 파라미터 optional |
| `src/backend/app/api/graph.py` | 변경 | `_run_graph()`에서 profile/vault 분리 |
| `src/backend/app/agents/profile_agent.py` | 변경 | `person_ids` 파라미터 추가 |
| `src/backend/tests/test_agents/test_profile_agent.py` | 변경 | person_ids 필터 테스트 추가 |
| `src/backend/app/api/projects.py` | 변경 | `POST/GET /{id}/profiles` + `_run_profiles()` + 헬퍼 함수 |
| `src/backend/app/api/graph.py` | 변경 | `GET /{id}/profiles` 제거 |
| `src/backend/tests/test_api/test_projects_api.py` | 변경 | profiles 엔드포인트 테스트 추가 |
| `src/backend/app/agents/graph_builder_agent.py` | 변경 | Role 추출 프롬프트 강화 |
| `src/frontend/src/api/client.js` | 변경 | `userApi`, `runProfiles` 추가 |
| `src/frontend/src/components/UserSetupModal.vue` | 신규 | 최초 방문 이름 입력 모달 |
| `src/frontend/src/views/HomeView.vue` | 변경 | onMounted user 체크 + UserSetupModal |
| `src/frontend/src/views/ProjectDetail.vue` | 변경 | 프로필 생성 섹션 |

---

### Task 1: User Config — Backend

**Files:**
- Modify: `src/backend/app/config.py`
- Create: `src/backend/app/api/user.py`
- Modify: `src/backend/app/main.py`
- Modify: `src/backend/tests/conftest.py`
- Create: `src/backend/tests/test_api/test_user_api.py`

- [ ] **Step 1: 테스트 작성**

`src/backend/tests/test_api/test_user_api.py` 파일 생성:

```python
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_get_user_returns_404_when_not_set(client):
    r = client.get("/api/user")
    assert r.status_code == 404


def test_post_user_saves_config(client):
    r = client.post("/api/user", json={"name": "양필성", "display_name": "Pilseong Yang"})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "양필성"
    assert data["display_name"] == "Pilseong Yang"


def test_get_user_returns_saved_config(client):
    client.post("/api/user", json={"name": "양필성", "display_name": "Pilseong Yang"})
    r = client.get("/api/user")
    assert r.status_code == 200
    assert r.json()["name"] == "양필성"


def test_post_user_display_name_defaults_to_name(client):
    r = client.post("/api/user", json={"name": "양필성"})
    assert r.json()["display_name"] == "양필성"
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
cd src/backend && python3 -m pytest tests/test_api/test_user_api.py -v
```

Expected: `FAILED` — 404 (라우터 미등록)

- [ ] **Step 3: config.py에 USER_CONFIG_PATH 추가**

```python
class Config(BaseSettings):
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o"
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    FUZZY_MATCH_THRESHOLD: float = 0.85
    MAX_ONTOLOGY_SAMPLE_CHARS: int = 50000
    PROJECTS_DIR: str = "./projects"
    VAULT_DIR: str = "./vault"
    LOG_DIR: str = "../../logs"
    USER_CONFIG_PATH: str = "./user.json"

    model_config = {"env_file": ".env", "extra": "ignore"}
```

- [ ] **Step 4: app/api/user.py 생성**

```python
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.config import config

router = APIRouter()


@router.get("")
async def get_user():
    path = Path(config.USER_CONFIG_PATH)
    if not path.exists():
        raise HTTPException(status_code=404, detail="User config not set")
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("")
async def set_user(body: dict):
    data = {
        "name": body.get("name", ""),
        "display_name": body.get("display_name") or body.get("name", ""),
    }
    path = Path(config.USER_CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data
```

- [ ] **Step 5: main.py에 user_router 등록**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import projects, graph, chat, tasks, user
from app.utils.logger import configure_logging

configure_logging()

app = FastAPI(title="ProjectOS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user.router, prefix="/api/user", tags=["user"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(graph.router, prefix="/api/projects", tags=["graph"])
app.include_router(graph.global_router, prefix="/api/graph", tags=["graph"])
app.include_router(chat.router, prefix="/api/projects", tags=["chat"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: conftest.py에 USER_CONFIG_PATH 격리 추가**

```python
import os

os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

import pytest


@pytest.fixture(autouse=True)
def isolate_filesystem(tmp_path, monkeypatch):
    from app.config import config

    projects_dir = tmp_path / "projects"
    vault_dir = tmp_path / "vault"
    logs_dir = tmp_path / "logs"
    projects_dir.mkdir()
    vault_dir.mkdir()
    logs_dir.mkdir()

    monkeypatch.setattr(config, "PROJECTS_DIR", str(projects_dir))
    monkeypatch.setattr(config, "VAULT_DIR", str(vault_dir))
    monkeypatch.setattr(config, "LOG_DIR", str(logs_dir))
    monkeypatch.setattr(config, "USER_CONFIG_PATH", str(tmp_path / "user.json"))

    yield
```

- [ ] **Step 7: 테스트 통과 확인**

```bash
cd src/backend && python3 -m pytest tests/test_api/test_user_api.py -v
```

Expected: `4 passed`

- [ ] **Step 8: 전체 테스트 확인**

```bash
cd src/backend && python3 -m pytest tests/ -v
```

Expected: 전체 통과 (기존 테스트 회귀 없음)

- [ ] **Step 9: 커밋**

```bash
git add src/backend/app/config.py src/backend/app/api/user.py src/backend/app/main.py \
        src/backend/tests/conftest.py src/backend/tests/test_api/test_user_api.py
git commit -m "feat: add user config API (GET/POST /api/user)"
```

---

### Task 2: ObsidianWriterAgent — profiles 파라미터 optional

**Files:**
- Modify: `src/backend/app/agents/obsidian_writer_agent.py`

- [ ] **Step 1: profiles 파라미터를 optional로 변경**

`obsidian_writer_agent.py`의 `run()` 시그니처와 `profile_map` 라인을 수정:

```python
def run(
    self,
    graph: nx.DiGraph,
    profiles: list[CareerProfile] | None = None,
    vault_path: str | None = None,
    delta: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
):
    vault = Path(vault_path or config.VAULT_DIR)
    self._setup_vault(vault)
    profile_map = {p.name: p for p in (profiles or [])}
```

- [ ] **Step 2: 전체 테스트 확인**

```bash
cd src/backend && python3 -m pytest tests/ -v
```

Expected: 전체 통과

- [ ] **Step 3: 커밋**

```bash
git add src/backend/app/agents/obsidian_writer_agent.py
git commit -m "refactor: make profiles parameter optional in ObsidianWriterAgent"
```

---

### Task 3: Graph Build — 프로필 생성 분리

**Files:**
- Modify: `src/backend/app/api/graph.py`

`_run_graph()` 에서 ProfileAgent 호출, profiles.json 저장, `is_valid_person_name` import를 제거하고 ObsidianWriterAgent를 profiles 없이 호출한다.

- [ ] **Step 1: graph.py의 `_run_graph()` 수정**

`_run_graph()` 함수 전체를 다음으로 교체:

```python
async def _run_graph(task_id: str, project_id: str, incremental: bool):
    try:
        from app.agents.graph_builder_agent import GraphBuilderAgent
        from app.agents.obsidian_writer_agent import ObsidianWriterAgent
        from app.models.graph import EdgeTypeDef, EntityTypeDef, Ontology, TextChunk

        task_manager.update(task_id, status=TaskStatus.RUNNING, message="그래프 구축 시작", progress=10)
        proj_dir = Path(config.PROJECTS_DIR) / project_id
        chunks_data = json.loads((proj_dir / "chunks.json").read_text(encoding="utf-8"))
        chunks = [TextChunk(**c) for c in chunks_data]
        ont_data = json.loads((proj_dir / "ontology.json").read_text(encoding="utf-8"))
        ontology = Ontology(
            entity_types=[EntityTypeDef(**e) for e in ont_data["entity_types"]],
            edge_types=[EdgeTypeDef(**e) for e in ont_data["edge_types"]],
            analysis_summary=ont_data["analysis_summary"],
        )
        graph_path = str(proj_dir / "graph.json")
        graph_agent = GraphBuilderAgent()
        total_chunks = len(chunks)
        task_manager.update(
            task_id,
            message=f"엔티티/관계 추출 중... (0/{total_chunks})",
            progress=30,
        )

        def on_chunk_progress(current: int, total: int):
            ratio = current / total if total else 1
            task_manager.update(
                task_id,
                message=f"엔티티/관계 추출 중... ({current}/{total})",
                progress=30 + int(ratio * 40),
            )

        graph = await graph_agent.run(
            chunks,
            ontology,
            incremental=incremental,
            graph_path=graph_path,
            progress_callback=on_chunk_progress,
        )
        graph_agent.save(graph, graph_path)

        total_nodes = graph.number_of_nodes()
        task_manager.update(
            task_id,
            message=f"Obsidian vault 작성 중... (0/{total_nodes})",
            progress=72,
        )
        writer = ObsidianWriterAgent()
        vault_path = str(Path(config.VAULT_DIR) / project_id)

        def on_vault_progress(current: int, total: int, name: str):
            ratio = current / total if total else 1
            task_manager.update(
                task_id,
                message=f"Obsidian vault 작성 중... ({current}/{total}) {name}",
                progress=72 + int(ratio * 25),
            )

        writer.run(
            graph,
            vault_path=vault_path,
            delta=incremental,
            progress_callback=on_vault_progress,
        )
        stats = graph_agent.get_stats(graph)
        project = project_store.get(project_id)
        if project:
            project.status = ProjectStatus.READY
            project.stats = dataclasses.asdict(stats)
            project_store.save(project)
        task_manager.update(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=f"완료: 노드 {stats.total_nodes}개, 엣지 {stats.total_edges}개",
        )
    except Exception as e:
        project = project_store.get(project_id)
        if project:
            project.status = ProjectStatus.FAILED
            project_store.save(project)
        task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))
```

- [ ] **Step 2: 전체 테스트 확인**

```bash
cd src/backend && python3 -m pytest tests/ -v
```

Expected: 전체 통과

- [ ] **Step 3: 커밋**

```bash
git add src/backend/app/api/graph.py
git commit -m "refactor: decouple profile generation from graph build in _run_graph"
```

---

### Task 4: ProfileAgent — person_ids 필터

**Files:**
- Modify: `src/backend/app/agents/profile_agent.py`
- Modify: `src/backend/tests/test_agents/test_profile_agent.py`

- [ ] **Step 1: 테스트 추가**

`test_profile_agent.py` 파일 끝에 추가:

```python
@pytest.fixture
def two_person_graph():
    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong",
               description="ML researcher", source_files=["cv.pdf"])
    g.add_node("Person:Kim Chulsoo", type="Person", name="Kim Chulsoo",
               description="Advisor", source_files=["cv.pdf"])
    g.add_node("Skill:Python", type="Skill", name="Python",
               description="", source_files=["cv.pdf"])
    g.add_edge("Person:Yang Pilseong", "Skill:Python", relation="USES_SKILL")
    return g


@pytest.mark.asyncio
async def test_profile_agent_filters_by_person_ids(two_person_graph):
    from app.agents.profile_agent import ProfileAgent

    agent = ProfileAgent()
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_PROFILE_RESPONSE)):
        profiles = await agent.run(two_person_graph, person_ids=["Person:Yang Pilseong"])

    assert len(profiles) == 1
    assert profiles[0].name == "Yang Pilseong"


@pytest.mark.asyncio
async def test_profile_agent_returns_all_when_person_ids_is_none(two_person_graph):
    from app.agents.profile_agent import ProfileAgent

    agent = ProfileAgent()
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_PROFILE_RESPONSE)):
        profiles = await agent.run(two_person_graph, person_ids=None)

    assert len(profiles) == 2
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
cd src/backend && python3 -m pytest tests/test_agents/test_profile_agent.py -v
```

Expected: `test_profile_agent_filters_by_person_ids` FAILED

- [ ] **Step 3: ProfileAgent.run() 시그니처 변경**

`profile_agent.py`의 `run()` 메서드를 다음으로 교체:

```python
async def run(
    self,
    graph: nx.DiGraph,
    person_ids: list[str] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[CareerProfile]:
    all_person_nodes = [
        (nid, data)
        for nid, data in graph.nodes(data=True)
        if data.get("type") == "Person"
        and is_valid_person_name(str(data.get("name", "")))
    ]
    if person_ids is not None:
        id_set = set(person_ids)
        person_nodes = [(nid, data) for nid, data in all_person_nodes if nid in id_set]
    else:
        person_nodes = all_person_nodes

    profiles = []
    total = len(person_nodes)
    for i, (node_id, node_data) in enumerate(person_nodes, start=1):
        name = node_data["name"]
        logger.info(f"ProfileAgent: building profile for {name}")
        context = self._collect_context(graph, node_id)
        profile = await self._generate_profile(name, context)
        profiles.append(profile)
        if progress_callback:
            progress_callback(i, total, name)
    return profiles
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd src/backend && python3 -m pytest tests/test_agents/test_profile_agent.py -v
```

Expected: `6 passed`

- [ ] **Step 5: 전체 테스트 확인**

```bash
cd src/backend && python3 -m pytest tests/ -v
```

Expected: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add src/backend/app/agents/profile_agent.py \
        src/backend/tests/test_agents/test_profile_agent.py
git commit -m "feat: add person_ids filter to ProfileAgent.run()"
```

---

### Task 5: Profile API Endpoints

**Files:**
- Modify: `src/backend/app/api/projects.py`
- Modify: `src/backend/app/api/graph.py`
- Modify: `src/backend/tests/test_api/test_projects_api.py`

- [ ] **Step 1: 테스트 추가**

`test_projects_api.py` 파일 끝에 추가:

```python
def test_get_profiles_returns_404_when_not_run(client):
    r = client.post("/api/projects", json={"name": "Profiles Test"})
    pid = r.json()["project_id"]
    r2 = client.get(f"/api/projects/{pid}/profiles")
    assert r2.status_code == 404


def test_run_profiles_returns_400_when_no_graph(client):
    r = client.post("/api/projects", json={"name": "No Graph"})
    pid = r.json()["project_id"]
    r2 = client.post(f"/api/projects/{pid}/profiles")
    assert r2.status_code == 400


def test_run_profiles_returns_task_id_when_graph_and_user_exist(client):
    import json as _json
    from pathlib import Path
    from app.config import config as _cfg
    from unittest.mock import patch, AsyncMock

    r = client.post("/api/projects", json={"name": "Has Graph"})
    pid = r.json()["project_id"]

    proj_dir = Path(_cfg.PROJECTS_DIR) / pid
    graph_data = {
        "directed": True, "multigraph": False, "graph": {},
        "nodes": [{"type": "Person", "name": "양필성", "id": "Person:양필성",
                   "description": "", "source_files": [], "attributes": {}}],
        "links": [],
    }
    (proj_dir / "graph.json").write_text(_json.dumps(graph_data))
    Path(_cfg.USER_CONFIG_PATH).write_text(
        _json.dumps({"name": "양필성", "display_name": "Pilseong Yang"})
    )

    with patch("app.agents.profile_agent.ProfileAgent.run", new=AsyncMock(return_value=[])):
        r2 = client.post(f"/api/projects/{pid}/profiles")

    assert r2.status_code == 200
    assert "task_id" in r2.json()
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
cd src/backend && python3 -m pytest \
  tests/test_api/test_projects_api.py::test_get_profiles_returns_404_when_not_run \
  tests/test_api/test_projects_api.py::test_run_profiles_returns_400_when_no_graph \
  tests/test_api/test_projects_api.py::test_run_profiles_returns_task_id_when_graph_and_user_exist \
  -v
```

Expected: `FAILED` — 404 (엔드포인트 없음)

- [ ] **Step 3: projects.py에 imports, 헬퍼 함수, 엔드포인트 추가**

`projects.py` 상단 import 블록에 추가:

```python
import dataclasses
import json
from difflib import SequenceMatcher
```

파일 끝 `_run_parse` 함수 앞에 다음 추가:

```python
@router.get("/{project_id}/profiles")
async def get_profiles(project_id: str):
    p = Path(config.PROJECTS_DIR) / project_id / "profiles.json"
    if not p.exists():
        raise HTTPException(404, "Profiles not built yet")
    return json.loads(p.read_text(encoding="utf-8"))


@router.post("/{project_id}/profiles")
async def run_profiles(project_id: str):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    graph_path = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    if not graph_path.exists():
        raise HTTPException(400, "Graph not built yet — run graph build first")
    task = task_manager.create(project_id, "profiles")
    asyncio.create_task(_run_profiles(task.task_id, project_id))
    return {"task_id": task.task_id}
```

파일 끝에 헬퍼 함수 + `_run_profiles` 추가:

```python
def _find_user_person(graph, user_name: str, display_name: str) -> str | None:
    threshold = 0.7
    best_id, best_score = None, 0.0
    for nid, data in graph.nodes(data=True):
        if data.get("type") != "Person":
            continue
        node_name = data.get("name", "").lower()
        s = max(
            SequenceMatcher(None, user_name.lower(), node_name).ratio(),
            SequenceMatcher(None, display_name.lower(), node_name).ratio(),
        )
        if s > best_score:
            best_score, best_id = s, nid
    return best_id if best_score >= threshold else None


def _most_connected_person(graph) -> str | None:
    persons = [nid for nid, d in graph.nodes(data=True) if d.get("type") == "Person"]
    return max(persons, key=lambda n: graph.degree(n)) if persons else None


async def _run_profiles(task_id: str, project_id: str):
    import networkx as nx
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent
    from app.agents.profile_agent import ProfileAgent
    from app.utils.logger import get_logger

    logger = get_logger(__name__)
    try:
        task_manager.update(task_id, status=TaskStatus.RUNNING, message="그래프 로딩 중...", progress=10)
        proj_dir = Path(config.PROJECTS_DIR) / project_id

        data = json.loads((proj_dir / "graph.json").read_text(encoding="utf-8"))
        if "links" in data and "edges" not in data:
            data["edges"] = data.pop("links")
        graph = nx.node_link_graph(data)

        user_path = Path(config.USER_CONFIG_PATH)
        if not user_path.exists():
            raise ValueError("User config not set — set user name first")
        user_data = json.loads(user_path.read_text(encoding="utf-8"))
        user_name = user_data.get("name", "")
        display_name = user_data.get("display_name") or user_name

        person_id = _find_user_person(graph, user_name, display_name)
        if not person_id:
            person_id = _most_connected_person(graph)
            if person_id:
                logger.warning(f"No fuzzy match for '{user_name}' — using most connected: {person_id}")
            else:
                raise ValueError("No Person nodes found in graph")

        task_manager.update(task_id, message=f"프로필 생성 중... {person_id}", progress=30)
        profile_agent = ProfileAgent()

        def on_progress(current: int, total: int, name: str):
            task_manager.update(
                task_id,
                message=f"프로필 생성 중... ({current}/{total}) {name}",
                progress=30 + int((current / total if total else 1) * 50),
            )

        profiles = await profile_agent.run(graph, person_ids=[person_id], progress_callback=on_progress)
        profiles_data = [dataclasses.asdict(p) for p in profiles]
        (proj_dir / "profiles.json").write_text(
            json.dumps(profiles_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        task_manager.update(task_id, message="Obsidian vault 업데이트 중...", progress=85)
        writer = ObsidianWriterAgent()
        vault_path = str(Path(config.VAULT_DIR) / project_id)
        writer.run(graph, profiles, vault_path=vault_path, delta=True)

        task_manager.update(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=f"프로필 생성 완료: {len(profiles)}개",
        )
    except Exception as e:
        task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))
```

- [ ] **Step 4: graph.py에서 GET /profiles 제거**

`graph.py`에서 다음 블록 삭제:

```python
@router.get("/{project_id}/profiles")
async def get_profiles(project_id: str):
    p = Path(config.PROJECTS_DIR) / project_id / "profiles.json"
    if not p.exists():
        raise HTTPException(404, "Profiles not built yet")
    return json.loads(p.read_text(encoding="utf-8"))
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
cd src/backend && python3 -m pytest \
  tests/test_api/test_projects_api.py::test_get_profiles_returns_404_when_not_run \
  tests/test_api/test_projects_api.py::test_run_profiles_returns_400_when_no_graph \
  tests/test_api/test_projects_api.py::test_run_profiles_returns_task_id_when_graph_and_user_exist \
  -v
```

Expected: `3 passed`

- [ ] **Step 6: 전체 테스트 확인**

```bash
cd src/backend && python3 -m pytest tests/ -v
```

Expected: 전체 통과

- [ ] **Step 7: 커밋**

```bash
git add src/backend/app/api/projects.py src/backend/app/api/graph.py \
        src/backend/tests/test_api/test_projects_api.py
git commit -m "feat: add POST/GET /projects/{id}/profiles with user.json-based person matching"
```

---

### Task 6: Role 추출 프롬프트 강화

**Files:**
- Modify: `src/backend/app/agents/graph_builder_agent.py`

- [ ] **Step 1: 프롬프트 내 Role 규칙 교체**

`graph_builder_agent.py`의 `_extract_from_chunk` 프롬프트에서 기존 Role 관련 줄:

```python
        - If a term is a role or responsibility, classify it as Role only when it is specific and useful.
```

을 다음으로 교체:

```python
        - Role is ONLY for formal job titles or academic positions that could appear on a resume or business card. Examples: "Research Engineer", "PhD Student", "Professor", "Team Lead", "Software Engineer", "Undergraduate Researcher". Do NOT classify as Role: activity descriptions ("데이터 검수", "reviewing model evaluation frameworks"), participant labels ("발표자", "사회자", "패널", "moderator"), generic descriptions ("지역 주민", "기업", "약 1년간 근무"), or any phrase that is not a named position. If an item describes a concrete outcome or result → Achievement. If it describes participation in an event → Event. Vague or generic descriptions → do not extract at all.
```

- [ ] **Step 2: 전체 테스트 확인**

```bash
cd src/backend && python3 -m pytest tests/ -v
```

Expected: 전체 통과

- [ ] **Step 3: 커밋**

```bash
git add src/backend/app/agents/graph_builder_agent.py
git commit -m "fix: restrict Role extraction to formal job titles only"
```

---

### Task 7: Frontend — UserSetupModal + HomeView

**Files:**
- Create: `src/frontend/src/components/UserSetupModal.vue`
- Modify: `src/frontend/src/views/HomeView.vue`

- [ ] **Step 1: UserSetupModal.vue 생성**

```vue
<template>
  <el-dialog
    v-model="visible"
    title="ProjectOS에 오신 걸 환영합니다"
    width="420px"
    :close-on-click-modal="false"
    :show-close="false"
  >
    <p style="color:#606266;margin-bottom:16px">
      커리어 프로필 생성에 사용할 이름을 입력해 주세요.
    </p>
    <el-form @submit.prevent="save">
      <el-form-item label="이름 (한국어)">
        <el-input v-model="name" placeholder="예: 양필성" autofocus />
      </el-form-item>
      <el-form-item label="영문 이름">
        <el-input v-model="displayName" placeholder="예: Pilseong Yang" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button type="primary" :disabled="!name.trim()" :loading="saving" @click="save">
        시작하기
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { userApi } from '../api/client.js'

const visible = ref(true)
const name = ref('')
const displayName = ref('')
const saving = ref(false)

const emit = defineEmits(['saved'])

async function save() {
  if (!name.value.trim()) return
  saving.value = true
  try {
    await userApi.set({ name: name.value.trim(), display_name: displayName.value.trim() || name.value.trim() })
    visible.value = false
    emit('saved')
  } finally {
    saving.value = false
  }
}
</script>
```

- [ ] **Step 2: HomeView.vue에 UserSetupModal 연동**

`HomeView.vue`의 `<script setup>` imports에 추가:

```js
import UserSetupModal from '../components/UserSetupModal.vue'
import { userApi } from '../api/client.js'
```

기존 `const projects = ref([])` 아래에 추가:

```js
const showUserSetup = ref(false)
```

`onMounted` 함수 시작 부분에 추가:

```js
try {
  await userApi.get()
} catch {
  showUserSetup.value = true
}
```

template의 `<el-main>` 바로 앞에 추가:

```html
<UserSetupModal v-if="showUserSetup" @saved="showUserSetup = false" />
```

- [ ] **Step 3: 커밋**

```bash
git add src/frontend/src/components/UserSetupModal.vue \
        src/frontend/src/views/HomeView.vue
git commit -m "feat: add UserSetupModal for first-launch user name configuration"
```

---

### Task 8: Frontend — client.js + ProjectDetail 프로필 섹션

**Files:**
- Modify: `src/frontend/src/api/client.js`
- Modify: `src/frontend/src/views/ProjectDetail.vue`

- [ ] **Step 1: client.js에 userApi, runProfiles 추가**

`client.js` 파일 전체를 다음으로 교체:

```js
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const userApi = {
  get: () => api.get('/user'),
  set: (data) => api.post('/user', data),
}

export const projectsApi = {
  list: () => api.get('/projects'),
  create: (data) => api.post('/projects', data),
  get: (id) => api.get(`/projects/${id}`),
  delete: (id) => api.delete(`/projects/${id}`),
  uploadFiles: (id, formData) => api.post(`/projects/${id}/files`, formData),
  addFiles: (id, formData) => api.post(`/projects/${id}/files/add`, formData),
  getOntology: (id) => api.get(`/projects/${id}/ontology`),
  runOntology: (id) => api.post(`/projects/${id}/ontology`),
  getGraph: (id) => api.get(`/projects/${id}/graph`),
  getGraphStats: (id) => api.get(`/projects/${id}/graph/stats`),
  runGraph: (id) => api.post(`/projects/${id}/graph`),
  runGraphIncremental: (id) => api.post(`/projects/${id}/graph/incremental`),
  getProfiles: (id) => api.get(`/projects/${id}/profiles`),
  runProfiles: (id) => api.post(`/projects/${id}/profiles`),
  getVaultTree: (id) => api.get(`/projects/${id}/vault`),
  downloadVault: (id) => `/api/projects/${id}/vault/download`,
  runAnalysis: (id) => api.post(`/projects/${id}/analysis`),
  getAnalysis: (id) => api.get(`/projects/${id}/analysis`),
}

export const globalApi = {
  getGraph: () => api.get('/graph/global'),
}

export const tasksApi = {
  get: (taskId) => api.get(`/tasks/${taskId}`),
  streamUrl: (taskId) => `/api/tasks/${taskId}/stream`,
}

export const chatStreamUrl = (projectId) => `/api/projects/${projectId}/chat`

export default api
```

- [ ] **Step 2: ProjectDetail.vue에 프로필 생성 섹션 추가**

`ProjectDetail.vue`의 `<script setup>` imports에 추가:

```js
import { projectsApi } from '../api/client.js'
```

(이미 import돼 있으면 `runProfiles`가 포함됐으므로 확인만)

기존 `const analysisData = ref(null)` 아래에 추가:

```js
const profileData = ref(null)
const profileTask = ref(null)
const profileRunning = ref(false)
```

`onMounted` 내 analysis 로딩 코드 뒤에 추가:

```js
try {
  const pr = await projectsApi.getProfiles(projectId.value)
  profileData.value = pr.data
} catch {
  // 프로필 미생성 — 정상
}
```

`onAnalysisFailed` 함수 뒤에 추가:

```js
async function runProfiles() {
  profileRunning.value = true
  try {
    const r = await projectsApi.runProfiles(projectId.value)
    profileTask.value = r.data.task_id
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '프로필 생성을 시작할 수 없습니다.')
  } finally {
    profileRunning.value = false
  }
}

async function onProfileCompleted() {
  profileTask.value = null
  try {
    const r = await projectsApi.getProfiles(projectId.value)
    profileData.value = r.data
    ElMessage.success('프로필 생성이 완료됐습니다.')
  } catch {
    ElMessage.error('프로필 결과를 불러오지 못했습니다.')
  }
}

function onProfileFailed(err) {
  profileTask.value = null
  ElMessage.error(err || '프로필 생성에 실패했습니다.')
}
```

분석 섹션 바로 위(`<el-divider />` 앞)에 프로필 섹션 추가:

```html
<el-divider />
<div class="sidebar-section">
  <div class="sidebar-label">커리어 프로필</div>
  <div v-if="profileTask">
    <ProgressPanel
      :task-id="profileTask"
      @completed="onProfileCompleted"
      @failed="onProfileFailed"
    />
  </div>
  <div v-else-if="profileData && profileData.length">
    <el-button size="small" type="success" plain style="width:100%;margin-bottom:6px"
               @click="ElMessage.info('프로필 뷰어 준비 중')">
      프로필 보기 ({{ profileData.length }}개)
    </el-button>
    <el-button size="small" plain style="width:100%" :loading="profileRunning" @click="runProfiles">
      재생성
    </el-button>
  </div>
  <div v-else>
    <el-button
      size="small"
      type="primary"
      style="width:100%"
      :loading="profileRunning"
      :disabled="project?.status !== 'ready'"
      @click="runProfiles"
    >
      프로필 생성
    </el-button>
    <p style="font-size:11px;color:#909399;margin-top:6px">
      그래프 빌드 완료 후 실행 가능
    </p>
  </div>
</div>
```

- [ ] **Step 3: 프론트엔드 빌드 확인**

```bash
cd src/frontend && npm run build
```

Expected: 성공 (Vite large chunk 경고만 허용)

- [ ] **Step 4: 커밋**

```bash
git add src/frontend/src/api/client.js src/frontend/src/views/ProjectDetail.vue
git commit -m "feat: add profile generation section to ProjectDetail sidebar"
```

---

## 자체 검토 (Spec Coverage)

| 스펙 요구사항 | 구현 태스크 |
|-------------|-----------|
| user.json 저장 (GET/POST /api/user) | Task 1 |
| USER_CONFIG_PATH 테스트 격리 | Task 1 (conftest) |
| ObsidianWriterAgent profiles optional | Task 2 |
| 그래프 빌드에서 프로필 분리 | Task 3 |
| vault는 그래프 빌드 시 초기 생성 | Task 3 |
| ProfileAgent person_ids 필터 | Task 4 |
| POST /projects/{id}/profiles 엔드포인트 | Task 5 |
| user.json 기반 fuzzy match Person 탐색 | Task 5 (_find_user_person) |
| degree fallback + 경고 로그 | Task 5 (_most_connected_person) |
| vault delta=True 업데이트 | Task 5 (_run_profiles) |
| GET /profiles graph.py에서 projects.py로 이동 | Task 5 |
| Role = 공식 직함만 | Task 6 |
| 행동/책임 → Achievement 또는 미추출 | Task 6 |
| 이벤트 참가 역할 → Event | Task 6 |
| 최초 방문 UserSetupModal | Task 7 |
| client.js userApi, runProfiles | Task 8 |
| ProjectDetail 프로필 생성 섹션 | Task 8 |
