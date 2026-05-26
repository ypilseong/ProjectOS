# Global Graph View & Document Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 전체 프로젝트 그래프 통합 뷰와 문서 약점 분석 기능을 추가한다.

**Architecture:** 백엔드에 `GET /api/graph/global` 엔드포인트(런타임 병합)와 `AnalysisAgent` + `/projects/{id}/analysis` API를 추가한다. 프론트엔드에서는 HomeView에 전체 그래프 탭, ProjectDetail 사이드바에 분석 버튼과 결과 드로어를 추가한다.

**Tech Stack:** FastAPI, NetworkX, OpenAI SDK (LLMClient), Vue 3, Element Plus, D3.js

---

## File Map

| 파일 | 변경 유형 | 역할 |
|------|----------|------|
| `src/backend/app/api/graph.py` | 변경 | `global_router` + `GET /global` 엔드포인트 추가 |
| `src/backend/app/main.py` | 변경 | `global_router`를 `/api/graph` prefix로 등록 |
| `src/backend/app/agents/analysis_agent.py` | 신규 | 문서 약점 분석 + 개선 초안 생성 |
| `src/backend/app/api/projects.py` | 변경 | `POST/GET /{id}/analysis` 엔드포인트 추가 |
| `src/backend/tests/test_api/test_graph_global.py` | 신규 | 전체 그래프 API 테스트 |
| `src/backend/tests/test_agents/test_analysis_agent.py` | 신규 | AnalysisAgent 테스트 |
| `src/frontend/src/api/client.js` | 변경 | `globalApi`, `runAnalysis`, `getAnalysis` 추가 |
| `src/frontend/src/components/GraphView.vue` | 변경 | `projectColors` prop 지원 |
| `src/frontend/src/views/HomeView.vue` | 변경 | 전체 그래프 탭 추가 |
| `src/frontend/src/components/AnalysisDrawer.vue` | 신규 | 분석 결과 드로어 |
| `src/frontend/src/views/ProjectDetail.vue` | 변경 | 사이드바 분석 섹션 추가 |

---

### Task 1: GET /api/graph/global 엔드포인트

**Files:**
- Modify: `src/backend/app/api/graph.py`
- Modify: `src/backend/app/main.py`
- Create: `src/backend/tests/test_api/test_graph_global.py`

- [ ] **Step 1: 테스트 작성**

`src/backend/tests/test_api/test_graph_global.py` 파일 생성:

```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def two_project_dirs(tmp_path):
    for proj_id, name in [("proj1", "프로젝트A"), ("proj2", "프로젝트B")]:
        d = tmp_path / proj_id
        d.mkdir()
        (d / "meta.json").write_text(
            json.dumps({"project_id": proj_id, "name": name, "status": "ready"})
        )
        graph = {
            "nodes": [
                {"id": "n1", "name": "홍길동", "type": "Person"},
                {"id": "n2", "name": "Python", "type": "Skill"},
            ],
            "links": [{"source": "n1", "target": "n2", "relation": "USES_SKILL"}],
        }
        (d / "graph.json").write_text(json.dumps(graph))
    return tmp_path


def test_global_graph_empty_when_no_graphs(client, tmp_path):
    with patch("app.api.graph.config") as mock_cfg:
        mock_cfg.PROJECTS_DIR = str(tmp_path)
        r = client.get("/api/graph/global")
    assert r.status_code == 200
    data = r.json()
    assert data["nodes"] == []
    assert data["links"] == []
    assert data["projects"] == []


def test_global_graph_namespaces_node_ids(client, two_project_dirs):
    with patch("app.api.graph.config") as mock_cfg:
        mock_cfg.PROJECTS_DIR = str(two_project_dirs)
        r = client.get("/api/graph/global")
    assert r.status_code == 200
    data = r.json()
    node_ids = {n["id"] for n in data["nodes"]}
    assert "proj1::n1" in node_ids
    assert "proj2::n1" in node_ids
    assert len(node_ids) == 4  # 충돌 없이 4개


def test_global_graph_links_use_namespaced_ids(client, two_project_dirs):
    with patch("app.api.graph.config") as mock_cfg:
        mock_cfg.PROJECTS_DIR = str(two_project_dirs)
        r = client.get("/api/graph/global")
    data = r.json()
    link_sources = {lnk["source"] for lnk in data["links"]}
    assert "proj1::n1" in link_sources
    assert "proj2::n1" in link_sources


def test_global_graph_includes_project_metadata(client, two_project_dirs):
    with patch("app.api.graph.config") as mock_cfg:
        mock_cfg.PROJECTS_DIR = str(two_project_dirs)
        r = client.get("/api/graph/global")
    data = r.json()
    project_ids = {p["id"] for p in data["projects"]}
    assert "proj1" in project_ids
    assert "proj2" in project_ids
    names = {p["name"] for p in data["projects"]}
    assert "프로젝트A" in names


def test_global_graph_skips_projects_without_graph(client, tmp_path):
    d = tmp_path / "nograph"
    d.mkdir()
    (d / "meta.json").write_text(
        json.dumps({"project_id": "nograph", "name": "No Graph"})
    )
    # graph.json 없음
    with patch("app.api.graph.config") as mock_cfg:
        mock_cfg.PROJECTS_DIR = str(tmp_path)
        r = client.get("/api/graph/global")
    data = r.json()
    assert data["nodes"] == []
    assert data["projects"] == []
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
cd src/backend
python3 -m pytest tests/test_api/test_graph_global.py -v
```

Expected: `FAILED` — `404 Not Found` or import error (엔드포인트 미존재)

- [ ] **Step 3: graph.py에 global_router 추가**

`src/backend/app/api/graph.py` 파일 상단 `router = APIRouter()` 바로 뒤에 추가:

```python
global_router = APIRouter()

PROJECT_COLORS = [
    "#4A90D9", "#5BA85B", "#E8A838", "#9B59B6", "#E74C3C",
    "#1ABC9C", "#E67E22", "#27AE60", "#2980B9", "#8E44AD",
]


@global_router.get("/global")
async def get_global_graph():
    base = Path(config.PROJECTS_DIR)
    if not base.exists():
        return {"nodes": [], "links": [], "projects": []}

    all_nodes: list[dict] = []
    all_links: list[dict] = []
    projects_meta: list[dict] = []
    color_idx = 0

    for proj_dir in sorted(d for d in base.iterdir() if d.is_dir()):
        graph_path = proj_dir / "graph.json"
        meta_path = proj_dir / "meta.json"
        if not graph_path.exists() or not meta_path.exists():
            continue

        project_id = proj_dir.name
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        project_name = meta.get("name", project_id)
        color = PROJECT_COLORS[color_idx % len(PROJECT_COLORS)]
        color_idx += 1

        projects_meta.append({"id": project_id, "name": project_name, "color": color})

        data = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes = data.get("nodes", [])
        links = data.get("links", [])

        id_map: dict[str, str] = {}
        for node in nodes:
            orig_id = node["id"]
            new_id = f"{project_id}::{orig_id}"
            id_map[orig_id] = new_id
            all_nodes.append({**node, "id": new_id, "project_id": project_id, "project_name": project_name})

        for lnk in links:
            src = lnk.get("source")
            tgt = lnk.get("target")
            if isinstance(src, dict):
                src = src["id"]
            if isinstance(tgt, dict):
                tgt = tgt["id"]
            all_links.append({
                **lnk,
                "source": id_map.get(src, f"{project_id}::{src}"),
                "target": id_map.get(tgt, f"{project_id}::{tgt}"),
            })

    return {"nodes": all_nodes, "links": all_links, "projects": projects_meta}
```

- [ ] **Step 4: main.py에 global_router 등록**

`src/backend/app/main.py`를 다음과 같이 수정:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import projects, graph, chat, tasks

app = FastAPI(title="ProjectOS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(graph.router, prefix="/api/projects", tags=["graph"])
app.include_router(graph.global_router, prefix="/api/graph", tags=["graph"])
app.include_router(chat.router, prefix="/api/projects", tags=["chat"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
cd src/backend
python3 -m pytest tests/test_api/test_graph_global.py -v
```

Expected: 모든 테스트 `PASSED`

- [ ] **Step 6: 커밋**

```bash
git add src/backend/app/api/graph.py src/backend/app/main.py src/backend/tests/test_api/test_graph_global.py
git commit -m "feat: add GET /api/graph/global endpoint with runtime project merge"
```

---

### Task 2: AnalysisAgent

**Files:**
- Create: `src/backend/app/agents/analysis_agent.py`
- Create: `src/backend/tests/test_agents/test_analysis_agent.py`

- [ ] **Step 1: 테스트 작성**

`src/backend/tests/test_agents/test_analysis_agent.py` 파일 생성:

```python
import pytest
from unittest.mock import AsyncMock, patch
import networkx as nx
from app.models.graph import TextChunk

MOCK_ISSUES = {
    "summary": "전반적으로 기술 역량은 좋으나 성과 수치가 부족합니다.",
    "issues": [
        {
            "category": "성과 수치",
            "severity": "high",
            "description": "정량적 성과가 없습니다.",
            "suggestion": "수치 기반 성과를 추가하세요.",
        },
        {
            "category": "기술 스택",
            "severity": "medium",
            "description": "최신 기술이 부족합니다.",
            "suggestion": "최신 프레임워크 경험을 추가하세요.",
        },
    ],
}
MOCK_DRAFT = "# 개선된 이력서\n\n## 경력\n수치 기반 성과를 포함한 내용..."


@pytest.fixture
def sample_chunks():
    return [
        TextChunk(
            chunk_id="c1",
            text="Python 개발자입니다. 다수의 프로젝트를 진행했습니다.",
            source_file="cv.pdf",
            file_type="note",
            page_num=1,
            char_offset=0,
        )
    ]


@pytest.fixture
def sample_graph():
    g = nx.DiGraph()
    g.add_node("Person:A", type="Person", name="홍길동")
    g.add_node("Skill:Python", type="Skill", name="Python")
    g.add_edge("Person:A", "Skill:Python", relation="USES_SKILL")
    return g


@pytest.mark.asyncio
async def test_analysis_agent_returns_required_fields(sample_chunks, sample_graph):
    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_ISSUES)), \
         patch.object(agent._llm, "chat", new=AsyncMock(return_value=MOCK_DRAFT)):
        result = await agent.run(sample_chunks, sample_graph)

    assert "summary" in result
    assert "issues" in result
    assert "improved_draft" in result
    assert "generated_at" in result


@pytest.mark.asyncio
async def test_analysis_agent_issues_structure(sample_chunks, sample_graph):
    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_ISSUES)), \
         patch.object(agent._llm, "chat", new=AsyncMock(return_value=MOCK_DRAFT)):
        result = await agent.run(sample_chunks, sample_graph)

    assert len(result["issues"]) == 2
    issue = result["issues"][0]
    assert issue["severity"] in ("high", "medium", "low")
    assert "category" in issue
    assert "description" in issue
    assert "suggestion" in issue


@pytest.mark.asyncio
async def test_analysis_agent_works_without_graph(sample_chunks):
    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_ISSUES)), \
         patch.object(agent._llm, "chat", new=AsyncMock(return_value=MOCK_DRAFT)):
        result = await agent.run(sample_chunks, None)

    assert result["summary"] == MOCK_ISSUES["summary"]
    assert result["improved_draft"] == MOCK_DRAFT


def test_graph_summary_counts_by_type(sample_graph):
    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    summary = agent._graph_summary(sample_graph)
    assert "2" in summary
    assert "Person" in summary
    assert "Skill" in summary


def test_graph_summary_with_none():
    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    assert agent._graph_summary(None) == "그래프 없음"


def test_graph_summary_empty_graph():
    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    assert agent._graph_summary(nx.DiGraph()) == "그래프 없음"
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
cd src/backend
python3 -m pytest tests/test_agents/test_analysis_agent.py -v
```

Expected: `ImportError` — `analysis_agent` 모듈 없음

- [ ] **Step 3: AnalysisAgent 구현**

`src/backend/app/agents/analysis_agent.py` 파일 생성:

```python
from datetime import datetime, timezone

import networkx as nx

from app.models.graph import TextChunk
from app.utils.llm_client import LLMClient
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AnalysisAgent:
    def __init__(self):
        self._llm = LLMClient()

    async def run(self, chunks: list[TextChunk], graph: nx.DiGraph | None = None) -> dict:
        full_text = "\n\n".join(c.text for c in chunks)
        graph_summary = self._graph_summary(graph)

        logger.info("AnalysisAgent: 약점 분석 시작")
        issues_result = await self._analyze_issues(full_text, graph_summary)

        logger.info("AnalysisAgent: 개선 초안 생성 시작")
        improved_draft = await self._generate_draft(full_text, issues_result.get("issues", []))

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": issues_result.get("summary", ""),
            "issues": issues_result.get("issues", []),
            "improved_draft": improved_draft,
        }

    def _graph_summary(self, graph: nx.DiGraph | None) -> str:
        if graph is None or graph.number_of_nodes() == 0:
            return "그래프 없음"
        type_counts: dict[str, int] = {}
        for _, data in graph.nodes(data=True):
            t = data.get("type", "Unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        parts = [f"{t}: {cnt}개" for t, cnt in type_counts.items()]
        return (
            f"총 {graph.number_of_nodes()}개 노드, "
            f"{graph.number_of_edges()}개 엣지. "
            + ", ".join(parts)
        )

    async def _analyze_issues(self, full_text: str, graph_summary: str) -> dict:
        prompt = f"""다음 문서를 분석하여 약점과 개선 방향을 찾아주세요.

그래프 분석 요약: {graph_summary}

문서 내용:
{full_text[:6000]}

JSON 형식으로 응답하세요 (한국어):
{{
  "summary": "전반적 평가 2~3문장",
  "issues": [
    {{
      "category": "카테고리명",
      "severity": "high|medium|low",
      "description": "구체적 문제 설명",
      "suggestion": "개선 제안"
    }}
  ]
}}"""
        return await self._llm.chat_json([{"role": "user", "content": prompt}])

    async def _generate_draft(self, full_text: str, issues: list[dict]) -> str:
        issues_text = "\n".join(
            f"- [{i.get('severity', 'medium')}] {i.get('category', '')}: {i.get('suggestion', '')}"
            for i in issues
        )
        prompt = f"""다음 원본 문서와 개선 제안을 바탕으로 개선된 문서 초안을 작성하세요.

개선 제안:
{issues_text}

원본 문서:
{full_text[:4000]}

개선된 문서를 마크다운 형식으로 작성하세요. 원본 구조를 유지하되 제안된 개선사항을 반영하세요."""
        return await self._llm.chat([{"role": "user", "content": prompt}])
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd src/backend
python3 -m pytest tests/test_agents/test_analysis_agent.py -v
```

Expected: 모든 테스트 `PASSED`

- [ ] **Step 5: 커밋**

```bash
git add src/backend/app/agents/analysis_agent.py src/backend/tests/test_agents/test_analysis_agent.py
git commit -m "feat: add AnalysisAgent with issue detection and draft generation"
```

---

### Task 3: Analysis API 엔드포인트

**Files:**
- Modify: `src/backend/app/api/projects.py`

- [ ] **Step 1: 테스트 작성**

`src/backend/tests/test_api/test_projects_api.py`에 다음 테스트 추가 (파일 끝에 append):

```python
def test_get_analysis_returns_404_when_not_run(client):
    r = client.post("/api/projects", json={"name": "Analysis Test"})
    pid = r.json()["project_id"]
    r2 = client.get(f"/api/projects/{pid}/analysis")
    assert r2.status_code == 404


def test_run_analysis_returns_404_when_no_chunks(client):
    r = client.post("/api/projects", json={"name": "No Chunks"})
    pid = r.json()["project_id"]
    r2 = client.post(f"/api/projects/{pid}/analysis")
    assert r2.status_code == 400


def test_run_analysis_returns_task_id_when_chunks_exist(client, tmp_path):
    import json as _json
    r = client.post("/api/projects", json={"name": "Has Chunks"})
    pid = r.json()["project_id"]

    # chunks.json 직접 생성
    from app.config import config as _cfg
    proj_dir = Path(_cfg.PROJECTS_DIR) / pid
    proj_dir.mkdir(parents=True, exist_ok=True)
    chunks_data = [
        {
            "chunk_id": "c1", "text": "test", "source_file": "cv.pdf",
            "file_type": "note", "page_num": None, "char_offset": 0,
        }
    ]
    (proj_dir / "chunks.json").write_text(_json.dumps(chunks_data))

    from unittest.mock import patch, AsyncMock
    mock_result = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "summary": "테스트",
        "issues": [],
        "improved_draft": "초안",
    }
    with patch("app.agents.analysis_agent.AnalysisAgent.run", new=AsyncMock(return_value=mock_result)):
        r2 = client.post(f"/api/projects/{pid}/analysis")

    assert r2.status_code == 200
    assert "task_id" in r2.json()
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
cd src/backend
python3 -m pytest tests/test_api/test_projects_api.py::test_get_analysis_returns_404_when_not_run tests/test_api/test_projects_api.py::test_run_analysis_returns_404_when_no_chunks tests/test_api/test_projects_api.py::test_run_analysis_returns_task_id_when_chunks_exist -v
```

Expected: `FAILED` — 404 Not Found (엔드포인트 없음)

- [ ] **Step 3: projects.py에 엔드포인트 추가**

`src/backend/app/api/projects.py`의 `_run_parse` 함수 정의 바로 앞에 다음을 추가:

```python
@router.post("/{project_id}/analysis")
async def run_analysis(project_id: str):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    chunks_path = Path(config.PROJECTS_DIR) / project_id / "chunks.json"
    if not chunks_path.exists():
        raise HTTPException(400, "No files uploaded yet — upload files first")
    task = task_manager.create(project_id, "analysis")
    asyncio.create_task(_run_analysis(task.task_id, project_id))
    return {"task_id": task.task_id}


@router.get("/{project_id}/analysis")
async def get_analysis(project_id: str):
    p = Path(config.PROJECTS_DIR) / project_id / "analysis.json"
    if not p.exists():
        raise HTTPException(404, "Analysis not run yet")
    return json.loads(p.read_text(encoding="utf-8"))
```

그리고 파일 끝 `_run_parse` 함수 뒤에 다음을 추가:

```python
async def _run_analysis(task_id: str, project_id: str):
    import networkx as nx
    from app.agents.analysis_agent import AnalysisAgent
    from app.models.graph import TextChunk
    try:
        task_manager.update(task_id, status=TaskStatus.RUNNING, message="청크 로딩 중...", progress=10)
        proj_dir = Path(config.PROJECTS_DIR) / project_id
        chunks_data = json.loads((proj_dir / "chunks.json").read_text(encoding="utf-8"))
        chunks = [TextChunk(**c) for c in chunks_data]

        graph = None
        graph_path = proj_dir / "graph.json"
        if graph_path.exists():
            data = json.loads(graph_path.read_text(encoding="utf-8"))
            graph = nx.node_link_graph(data)

        task_manager.update(task_id, message="LLM 분석 중... (1~2분 소요)", progress=30)
        agent = AnalysisAgent()
        result = await agent.run(chunks, graph)

        task_manager.update(task_id, message="결과 저장 중...", progress=90)
        (proj_dir / "analysis.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        task_manager.update(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=f"분석 완료: {len(result.get('issues', []))}개 개선 포인트 발견",
        )
    except Exception as e:
        task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))
```

`projects.py` 상단 import에 `json`이 없다면 추가:

```python
import json
```

(이미 있는지 확인 후 없는 경우만 추가)

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd src/backend
python3 -m pytest tests/test_api/test_projects_api.py::test_get_analysis_returns_404_when_not_run tests/test_api/test_projects_api.py::test_run_analysis_returns_404_when_no_chunks tests/test_api/test_projects_api.py::test_run_analysis_returns_task_id_when_chunks_exist -v
```

Expected: 모든 테스트 `PASSED`

- [ ] **Step 5: 전체 테스트 확인**

```bash
cd src/backend
python3 -m pytest tests/ -v
```

Expected: 모든 테스트 `PASSED`

- [ ] **Step 6: 커밋**

```bash
git add src/backend/app/api/projects.py src/backend/tests/test_api/test_projects_api.py
git commit -m "feat: add POST/GET /projects/{id}/analysis API endpoints"
```

---

### Task 4: Frontend API 클라이언트 업데이트

**Files:**
- Modify: `src/frontend/src/api/client.js`

- [ ] **Step 1: client.js 수정**

`src/frontend/src/api/client.js`를 다음으로 교체:

```js
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

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

- [ ] **Step 2: 커밋**

```bash
git add src/frontend/src/api/client.js
git commit -m "feat: add globalApi, runAnalysis, getAnalysis to API client"
```

---

### Task 5: GraphView.vue — projectColors prop 추가

**Files:**
- Modify: `src/frontend/src/components/GraphView.vue`

- [ ] **Step 1: GraphView.vue 수정**

`<script setup>` 섹션의 `defineProps` 블록을 다음으로 교체:

```js
const props = defineProps({
  graphData: { type: Object, default: null },
  projectColors: { type: Object, default: null },   // { project_id: color }
  onProjectNodeClick: { type: Function, default: null }, // 전체 그래프 모드 콜백
})
```

`getColor` 함수를 다음으로 교체 (노드 객체도 받을 수 있도록):

```js
function getColor(typeOrNode) {
  if (typeof typeOrNode === 'object' && typeOrNode !== null) {
    // 노드 객체인 경우: projectColors 우선
    if (props.projectColors && typeOrNode.project_id) {
      return props.projectColors[typeOrNode.project_id] || NODE_COLORS.default
    }
    return NODE_COLORS[typeOrNode.type] || NODE_COLORS.default
  }
  return NODE_COLORS[typeOrNode] || NODE_COLORS.default
}
```

`draw` 함수 내 노드 원 색상 라인을 다음으로 교체:

```js
node.append('circle')
  .attr('r', d => d.type === 'Person' ? 14 : 10)
  .attr('fill', d => getColor(d))
  .attr('stroke', '#fff')
  .attr('stroke-width', 2)
```

`onNodeClick` 함수 끝에 project 클릭 콜백 추가:

```js
function onNodeClick(d, data) {
  if (props.onProjectNodeClick && d.project_id) {
    props.onProjectNodeClick(d.project_id)
    return
  }
  selectedNode.value = d
  // ... 기존 코드 유지
```

툴바에 프로젝트 범례 추가 (`<div class="graph-toolbar">` 내부 끝):

```html
<div v-if="projectColors" class="project-legend">
  <span
    v-for="(color, pid) in projectColors"
    :key="pid"
    class="legend-item"
    :style="{ background: color }"
  >{{ pid }}</span>
</div>
```

`<style scoped>` 끝에 추가:

```css
.project-legend { display: flex; flex-wrap: wrap; gap: 4px; margin-left: 8px; }
.legend-item { padding: 2px 8px; border-radius: 10px; color: white; font-size: 11px; }
```

- [ ] **Step 2: 커밋**

```bash
git add src/frontend/src/components/GraphView.vue
git commit -m "feat: add projectColors prop to GraphView for multi-project coloring"
```

---

### Task 6: HomeView.vue — 전체 그래프 탭 추가

**Files:**
- Modify: `src/frontend/src/views/HomeView.vue`

- [ ] **Step 1: HomeView.vue template 수정**

`<el-main class="main">` 내용 전체를 다음으로 교체:

```html
<el-main class="main">
  <el-tabs v-model="activeTab" class="home-tabs">
    <!-- 프로젝트 목록 탭 -->
    <el-tab-pane label="프로젝트 목록" name="projects">
      <div v-if="loading" class="loading">
        <el-skeleton :rows="3" animated />
      </div>

      <el-empty
        v-else-if="!projects.length"
        description="첫 프로젝트를 만들어 커리어 그래프를 시작하세요"
        :image-size="160"
      >
        <el-button type="primary" @click="createDialogVisible = true">
          프로젝트 생성
        </el-button>
      </el-empty>

      <div v-else class="project-grid">
        <el-card
          v-for="p in projects"
          :key="p.project_id"
          class="project-card"
          shadow="hover"
          @click="router.push(`/projects/${p.project_id}`)"
        >
          <div class="card-header">
            <span class="project-name">{{ p.name }}</span>
            <el-tag :type="statusType(p.status)" size="small">{{ statusLabel(p.status) }}</el-tag>
          </div>
          <p class="project-desc">{{ p.description || '(설명 없음)' }}</p>
          <div class="card-footer">
            <div v-if="p.stats" class="stats-mini">
              <span>노드 {{ p.stats.total_nodes }}</span>
              <span>엣지 {{ p.stats.total_edges }}</span>
            </div>
            <div class="card-actions">
              <el-button size="small" type="danger" text @click.stop="deleteProject(p.project_id)">
                삭제
              </el-button>
            </div>
          </div>
        </el-card>
      </div>
    </el-tab-pane>

    <!-- 전체 그래프 탭 -->
    <el-tab-pane label="전체 그래프" name="global-graph">
      <div v-if="globalGraphLoading" class="loading">
        <el-skeleton :rows="5" animated />
      </div>
      <el-empty
        v-else-if="!globalGraphData || !globalGraphData.nodes.length"
        description="그래프가 구축된 프로젝트가 없습니다. 프로젝트를 만들고 그래프를 구축하세요."
        :image-size="120"
      />
      <div v-else style="height: 600px">
        <GraphView
          :graph-data="globalGraphData"
          :project-colors="globalProjectColors"
          :on-project-node-click="goToProject"
        />
      </div>
    </el-tab-pane>
  </el-tabs>
</el-main>
```

- [ ] **Step 2: HomeView.vue script 수정**

`<script setup>` 내 import에 추가:

```js
import GraphView from '../components/GraphView.vue'
import { globalApi } from '../api/client.js'
```

기존 `const projects = ref([])` 아래에 추가:

```js
const activeTab = ref('projects')
const globalGraphData = ref(null)
const globalGraphLoading = ref(false)
```

`globalProjectColors` computed 추가:

```js
const globalProjectColors = computed(() => {
  if (!globalGraphData.value?.projects) return null
  return Object.fromEntries(
    globalGraphData.value.projects.map(p => [p.id, p.color])
  )
})
```

`activeTab` watch 추가 (탭 전환 시 첫 1회만 로드):

```js
watch(activeTab, async (tab) => {
  if (tab === 'global-graph' && !globalGraphData.value) {
    globalGraphLoading.value = true
    try {
      const r = await globalApi.getGraph()
      globalGraphData.value = r.data
    } catch {
      globalGraphData.value = { nodes: [], links: [], projects: [] }
    } finally {
      globalGraphLoading.value = false
    }
  }
})
```

`goToProject` 함수 추가:

```js
function goToProject(projectId) {
  router.push(`/projects/${projectId}`)
}
```

`watch` import에 추가:

```js
import { ref, computed, watch, onMounted } from 'vue'
```

- [ ] **Step 3: HomeView.vue style 수정**

`<style scoped>` 끝에 추가:

```css
.home-tabs { width: 100%; }
```

- [ ] **Step 4: 커밋**

```bash
git add src/frontend/src/views/HomeView.vue
git commit -m "feat: add global graph tab to HomeView"
```

---

### Task 7: AnalysisDrawer.vue 신규 컴포넌트

**Files:**
- Create: `src/frontend/src/components/AnalysisDrawer.vue`

- [ ] **Step 1: AnalysisDrawer.vue 생성**

```vue
<template>
  <el-drawer
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    title="문서 분석 결과"
    direction="rtl"
    size="480px"
  >
    <div v-if="analysisData" class="analysis-content">
      <div class="summary-box">
        <p class="summary-text">{{ analysisData.summary }}</p>
        <div class="generated-at">분석일: {{ formatDate(analysisData.generated_at) }}</div>
      </div>

      <el-tabs v-model="innerTab" class="result-tabs">
        <!-- 개선 포인트 탭 -->
        <el-tab-pane label="개선 포인트" name="issues">
          <div v-if="!analysisData.issues?.length" class="no-issues">
            <el-empty description="발견된 문제가 없습니다" :image-size="80" />
          </div>
          <div v-else class="issues-list">
            <el-card
              v-for="(issue, idx) in analysisData.issues"
              :key="idx"
              class="issue-card"
              :body-style="{ padding: '12px' }"
            >
              <div class="issue-header">
                <el-tag :color="severityColor(issue.severity)" effect="dark" size="small">
                  {{ severityLabel(issue.severity) }}
                </el-tag>
                <span class="issue-category">{{ issue.category }}</span>
              </div>
              <p class="issue-description">{{ issue.description }}</p>
              <div class="issue-suggestion">
                <el-icon><ArrowRight /></el-icon>
                {{ issue.suggestion }}
              </div>
            </el-card>
          </div>
        </el-tab-pane>

        <!-- 개선 초안 탭 -->
        <el-tab-pane label="개선 초안" name="draft">
          <el-scrollbar height="500px">
            <pre class="draft-text">{{ analysisData.improved_draft }}</pre>
          </el-scrollbar>
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-drawer>
</template>

<script setup>
import { ref } from 'vue'
import { ArrowRight } from '@element-plus/icons-vue'

defineProps({
  visible: { type: Boolean, default: false },
  analysisData: { type: Object, default: null },
})
defineEmits(['update:visible'])

const innerTab = ref('issues')

function severityColor(severity) {
  return { high: '#E74C3C', medium: '#E8A838', low: '#95A5A6' }[severity] || '#95A5A6'
}

function severityLabel(severity) {
  return { high: '높음', medium: '중간', low: '낮음' }[severity] || severity
}

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' })
}
</script>

<style scoped>
.analysis-content { display: flex; flex-direction: column; gap: 16px; }
.summary-box {
  background: #f0f9ff;
  border-left: 4px solid #409eff;
  padding: 12px 16px;
  border-radius: 4px;
}
.summary-text { margin: 0 0 6px; font-size: 14px; color: #303133; line-height: 1.6; }
.generated-at { font-size: 11px; color: #909399; }
.result-tabs { margin-top: 4px; }
.issues-list { display: flex; flex-direction: column; gap: 10px; padding: 4px 0; }
.issue-card { border-radius: 6px; }
.issue-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.issue-category { font-weight: bold; font-size: 14px; color: #303133; }
.issue-description { margin: 0 0 8px; font-size: 13px; color: #606266; }
.issue-suggestion {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  font-size: 13px;
  color: #409eff;
  background: #ecf5ff;
  padding: 8px;
  border-radius: 4px;
}
.no-issues { padding: 32px 0; }
.draft-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Noto Sans KR', sans-serif;
  font-size: 13px;
  line-height: 1.7;
  color: #303133;
  padding: 8px;
}
</style>
```

- [ ] **Step 2: 커밋**

```bash
git add src/frontend/src/components/AnalysisDrawer.vue
git commit -m "feat: add AnalysisDrawer component for displaying analysis results"
```

---

### Task 8: ProjectDetail.vue — 사이드바 분석 섹션

**Files:**
- Modify: `src/frontend/src/views/ProjectDetail.vue`

- [ ] **Step 1: template에 분석 섹션 추가**

`ProjectDetail.vue` template의 `</el-aside>` 닫힘 태그 바로 앞(Vault 파일 섹션 뒤)에 추가:

```html
<el-divider />
<div class="sidebar-section">
  <div class="sidebar-label">문서 분석</div>
  <div v-if="analysisTask">
    <ProgressPanel
      :task-id="analysisTask"
      @completed="onAnalysisCompleted"
      @failed="onAnalysisFailed"
    />
  </div>
  <div v-else-if="analysisData">
    <el-button size="small" type="primary" plain style="width:100%;margin-bottom:6px" @click="analysisDrawerVisible = true">
      분석 결과 보기
    </el-button>
    <el-button size="small" plain style="width:100%" :loading="analysisRunning" @click="runAnalysis">
      재분석
    </el-button>
  </div>
  <div v-else>
    <el-button size="small" type="primary" style="width:100%" :loading="analysisRunning" @click="runAnalysis">
      분석 실행
    </el-button>
    <p style="font-size:11px;color:#909399;margin-top:6px">파일 업로드 후 실행 가능</p>
  </div>
</div>

<AnalysisDrawer
  v-model:visible="analysisDrawerVisible"
  :analysis-data="analysisData"
/>
```

- [ ] **Step 2: script에 분석 로직 추가**

import에 추가:

```js
import AnalysisDrawer from '../components/AnalysisDrawer.vue'
```

`const vaultTree = ref([])` 아래에 추가:

```js
const analysisData = ref(null)
const analysisTask = ref(null)
const analysisRunning = ref(false)
const analysisDrawerVisible = ref(false)
```

`onMounted` 내 `loadSidebarData()` 호출 뒤에 추가:

```js
try {
  const ar = await projectsApi.getAnalysis(projectId.value)
  analysisData.value = ar.data
} catch {
  // 분석 미실행 상태 — 정상
}
```

새 함수 추가 (기존 `goToUpload` 함수 뒤):

```js
async function runAnalysis() {
  analysisRunning.value = true
  try {
    const r = await projectsApi.runAnalysis(projectId.value)
    analysisTask.value = r.data.task_id
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '분석을 시작할 수 없습니다.')
  } finally {
    analysisRunning.value = false
  }
}

async function onAnalysisCompleted() {
  analysisTask.value = null
  try {
    const r = await projectsApi.getAnalysis(projectId.value)
    analysisData.value = r.data
    analysisDrawerVisible.value = true
  } catch {
    ElMessage.error('분석 결과를 불러오지 못했습니다.')
  }
}

function onAnalysisFailed(err) {
  analysisTask.value = null
  ElMessage.error(err || '분석에 실패했습니다.')
}
```

- [ ] **Step 3: 커밋**

```bash
git add src/frontend/src/views/ProjectDetail.vue
git commit -m "feat: add document analysis sidebar section to ProjectDetail"
```

---

## 자체 검토 (Spec Coverage)

| 스펙 요구사항 | 구현 태스크 |
|-------------|-----------|
| 전체 그래프: 런타임 병합 | Task 1 (GET /api/graph/global) |
| 전체 그래프: HomeView 탭 | Task 6 |
| 전체 그래프: 프로젝트 색상 구분 | Task 5 (projectColors prop) |
| 전체 그래프: Project 노드 클릭 → 이동 | Task 5 (onProjectNodeClick) + Task 6 (goToProject) |
| 문서 분석: 약점 리스트 | Task 2 (AnalysisAgent._analyze_issues) |
| 문서 분석: 개선 초안 | Task 2 (AnalysisAgent._generate_draft) |
| 문서 분석: 캐싱 (analysis.json) | Task 3 (_run_analysis 저장) |
| 문서 분석: 사이드바 버튼 | Task 8 |
| 문서 분석: SSE 진행 표시 | Task 8 (ProgressPanel 재사용) |
| 문서 분석: 결과 드로어 | Task 7 (AnalysisDrawer) |
| 분석 결과: 두 탭 구성 | Task 7 (개선 포인트 + 개선 초안) |
| graph.json 없어도 분석 가능 | Task 3 (_run_analysis: graph=None 허용) |
