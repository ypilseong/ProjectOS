# ProjectOS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-file career/project knowledge graph builder using 6 AI agents, NetworkX local graph, Obsidian vault output, and FastAPI+Vue.js UI.

**Architecture:** Agent pipeline (Parse→Ontology→Graph→Profile→Vault) with NetworkX replacing Zep Cloud, Obsidian markdown as visual output layer, and QueryAgent for LLM-powered chat over the graph.

**Tech Stack:** Python/FastAPI, NetworkX, PyMuPDF, python-docx, OpenAI SDK, Vue 3/Vite/Element Plus/D3.js

**Reference:** MiroFish (`../MiroFish/`) — DO NOT MODIFY. Read-only for pattern reference.

---

## Phase 1: Foundation

### Task 1: Project Scaffold + CLAUDE.md

- [ ] Create `CLAUDE.md` at project root with concise overview (see content below)
- [ ] Create `backend/` directory structure:
  ```
  backend/
    app/
      api/
      agents/
      models/
      utils/
    tests/
      test_models/
      test_agents/
      test_api/
    pyproject.toml
    run.py
  ```
- [ ] Create `frontend/` directory structure:
  ```
  frontend/
    src/
      components/
      views/
      api/
    public/
    package.json
    vite.config.js
  ```
- [ ] Create `projects/` and `vault/` directories with `.gitkeep`
- [ ] Commit: "feat: scaffold project structure"

**CLAUDE.md content:**
```markdown
# ProjectOS

로컬 파일(이력서, 프로젝트 문서, 논문) → LLM 분석 → NetworkX 그래프 → Obsidian vault

## Quick Start
cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev

## Docs
- Architecture: docs/superpowers/specs/2026-05-24-projectos-design.md
- Agents: docs/agents.md
- API: docs/api.md

## Key Rules
- MiroFish (../MiroFish/) is READ-ONLY reference
- Local graph only — no Zep Cloud
- TDD: write tests first
- Languages: Korean + English
```

---

### Task 2: Backend Models

**Test first** (`backend/tests/test_models/test_graph.py`):
```python
def test_text_chunk_creation():
    chunk = TextChunk(
        chunk_id="abc-123", text="sample", source_file="cv.pdf",
        file_type="cv", page_num=1, char_offset=0
    )
    assert chunk.chunk_id == "abc-123"
    assert chunk.file_type == "cv"

def test_career_profile_timeline():
    profile = CareerProfile(
        name="Yang Pilseong", expertise=["ML"], skills=["Python"],
        projects=["ProjectOS"], organizations=["KAIST"],
        publications=[], achievements=[], persona_summary="...",
        timeline=[{"year": 2020, "event": "입학"}]
    )
    assert profile.timeline[0]["year"] == 2020

def test_graph_stats():
    stats = GraphStats(
        total_nodes=42, total_edges=87,
        nodes_by_type={"Person": 1, "Skill": 15},
        edges_by_type={"USES_SKILL": 30}
    )
    assert stats.total_nodes == 42
```

- [ ] Run tests → confirm they fail
- [ ] Implement `backend/app/models/graph.py`:
  ```python
  from dataclasses import dataclass, field
  from typing import Optional

  @dataclass
  class TextChunk:
      chunk_id: str
      text: str
      source_file: str      # "cv" | "project" | "publication" | "note"
      file_type: str
      page_num: Optional[int]
      char_offset: int

  @dataclass
  class EntityTypeDef:
      name: str
      description: str
      examples: list[str] = field(default_factory=list)

  @dataclass
  class EdgeTypeDef:
      name: str
      description: str
      source_types: list[str] = field(default_factory=list)
      target_types: list[str] = field(default_factory=list)

  @dataclass
  class Ontology:
      entity_types: list[EntityTypeDef]
      edge_types: list[EdgeTypeDef]
      analysis_summary: str

  @dataclass
  class CareerProfile:
      name: str
      expertise: list[str]
      skills: list[str]
      projects: list[str]
      organizations: list[str]
      publications: list[str]
      achievements: list[str]
      persona_summary: str
      timeline: list[dict]

  @dataclass
  class GraphStats:
      total_nodes: int
      total_edges: int
      nodes_by_type: dict[str, int]
      edges_by_type: dict[str, int]
  ```
- [ ] Implement `backend/app/models/project.py`:
  ```python
  from pydantic import BaseModel
  from typing import Optional
  from datetime import datetime
  from enum import Enum

  class ProjectStatus(str, Enum):
      CREATED = "created"
      PARSING = "parsing"
      ONTOLOGY = "ontology"
      BUILDING = "building"
      WRITING = "writing"
      READY = "ready"
      FAILED = "failed"

  class TaskStatus(str, Enum):
      PENDING = "pending"
      RUNNING = "running"
      COMPLETED = "completed"
      FAILED = "failed"

  class Project(BaseModel):
      project_id: str
      name: str
      description: str = ""
      status: ProjectStatus = ProjectStatus.CREATED
      created_at: datetime = datetime.utcnow()
      files: list[str] = []
      stats: Optional[dict] = None

  class Task(BaseModel):
      task_id: str
      project_id: str
      task_type: str
      status: TaskStatus = TaskStatus.PENDING
      progress: int = 0
      message: str = ""
      error: Optional[str] = None
      created_at: datetime = datetime.utcnow()
  ```
- [ ] Run tests → confirm they pass
- [ ] Commit: "feat: add data models (TextChunk, Ontology, CareerProfile, GraphStats)"

---

### Task 3: Config + Utils

- [ ] Implement `backend/app/config.py`:
  ```python
  import os
  from pydantic_settings import BaseSettings

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

      class Config:
          env_file = ".env"

  config = Config()
  ```
- [ ] Implement `backend/app/utils/llm_client.py` (reference MiroFish pattern):
  ```python
  from openai import AsyncOpenAI
  from app.config import config
  import json

  class LLMClient:
      def __init__(self):
          self._client = AsyncOpenAI(
              api_key=config.LLM_API_KEY,
              base_url=config.LLM_BASE_URL,
          )

      async def chat(self, messages: list[dict], **kwargs) -> str:
          resp = await self._client.chat.completions.create(
              model=config.LLM_MODEL,
              messages=messages,
              **kwargs,
          )
          return resp.choices[0].message.content

      async def chat_json(self, messages: list[dict], **kwargs) -> dict:
          text = await self.chat(messages, response_format={"type": "json_object"}, **kwargs)
          return json.loads(text)

      async def stream(self, messages: list[dict], **kwargs):
          stream = await self._client.chat.completions.create(
              model=config.LLM_MODEL,
              messages=messages,
              stream=True,
              **kwargs,
          )
          async for chunk in stream:
              delta = chunk.choices[0].delta.content
              if delta:
                  yield delta

  llm_client = LLMClient()
  ```
- [ ] Implement `backend/app/utils/file_parser.py` (reference MiroFish `text_processor.py`):
  ```python
  import fitz  # PyMuPDF
  from docx import Document
  from charset_normalizer import from_path
  from pathlib import Path

  def extract_text_from_pdf(path: str) -> list[tuple[str, int]]:
      doc = fitz.open(path)
      return [(page.get_text(), i + 1) for i, page in enumerate(doc)]

  def extract_text_from_docx(path: str) -> str:
      doc = Document(path)
      return "\n".join(para.text for para in doc.paragraphs)

  def extract_text_from_txt(path: str) -> str:
      result = from_path(path).best()
      return str(result)

  def extract_text(path: str) -> list[tuple[str, Optional[int]]]:
      suffix = Path(path).suffix.lower()
      if suffix == ".pdf":
          return extract_text_from_pdf(path)
      elif suffix == ".docx":
          return [(extract_text_from_docx(path), None)]
      else:
          return [(extract_text_from_txt(path), None)]
  ```
- [ ] Implement `backend/app/utils/logger.py`:
  ```python
  import logging

  def get_logger(name: str) -> logging.Logger:
      logger = logging.getLogger(name)
      if not logger.handlers:
          handler = logging.StreamHandler()
          handler.setFormatter(logging.Formatter(
              "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
          ))
          logger.addHandler(handler)
          logger.setLevel(logging.INFO)
      return logger
  ```
- [ ] Create `backend/pyproject.toml`:
  ```toml
  [build-system]
  requires = ["setuptools>=68", "wheel"]
  build-backend = "setuptools.backends.legacy:build"

  [project]
  name = "projectos-backend"
  version = "0.1.0"
  requires-python = ">=3.11"
  dependencies = [
      "fastapi>=0.111",
      "uvicorn[standard]>=0.29",
      "pydantic>=2.7",
      "pydantic-settings>=2.2",
      "openai>=1.30",
      "networkx>=3.3",
      "pymupdf>=1.24",
      "python-docx>=1.1",
      "charset-normalizer>=3.3",
      "python-multipart>=0.0.9",
      "aiofiles>=23.2",
  ]

  [project.optional-dependencies]
  dev = ["pytest>=8", "pytest-asyncio>=0.23", "httpx>=0.27"]
  ```
- [ ] Commit: "feat: add config, llm_client, file_parser utils"

---

### Task 4: FastAPI App + TaskManager

**Test first** (`backend/tests/test_api/test_health.py`):
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

- [ ] Run test → confirm it fails
- [ ] Implement `backend/app/main.py`:
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
  app.include_router(chat.router, prefix="/api/projects", tags=["chat"])
  app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])

  @app.get("/health")
  async def health():
      return {"status": "ok"}
  ```
- [ ] Implement `backend/app/services/task_manager.py`:
  ```python
  import uuid
  from datetime import datetime
  from app.models.project import Task, TaskStatus

  class TaskManager:
      def __init__(self):
          self._tasks: dict[str, Task] = {}

      def create(self, project_id: str, task_type: str) -> Task:
          task = Task(
              task_id=str(uuid.uuid4()),
              project_id=project_id,
              task_type=task_type,
          )
          self._tasks[task.task_id] = task
          return task

      def get(self, task_id: str) -> Task | None:
          return self._tasks.get(task_id)

      def update(self, task_id: str, *, status=None, progress=None, message=None, error=None):
          task = self._tasks[task_id]
          if status is not None:
              task.status = status
          if progress is not None:
              task.progress = progress
          if message is not None:
              task.message = message
          if error is not None:
              task.error = error

  task_manager = TaskManager()
  ```
- [ ] Implement `backend/app/services/project_store.py`:
  ```python
  import json
  import uuid
  from pathlib import Path
  from datetime import datetime
  from app.config import config
  from app.models.project import Project

  class ProjectStore:
      def _project_dir(self, project_id: str) -> Path:
          return Path(config.PROJECTS_DIR) / project_id

      def _meta_path(self, project_id: str) -> Path:
          return self._project_dir(project_id) / "meta.json"

      def create(self, name: str, description: str = "") -> Project:
          project_id = str(uuid.uuid4())[:8]
          d = self._project_dir(project_id)
          d.mkdir(parents=True, exist_ok=True)
          (d / "files").mkdir(exist_ok=True)
          project = Project(project_id=project_id, name=name, description=description)
          self._save(project)
          return project

      def get(self, project_id: str) -> Project | None:
          p = self._meta_path(project_id)
          if not p.exists():
              return None
          return Project.model_validate_json(p.read_text())

      def list_all(self) -> list[Project]:
          base = Path(config.PROJECTS_DIR)
          if not base.exists():
              return []
          projects = []
          for d in base.iterdir():
              meta = d / "meta.json"
              if meta.exists():
                  projects.append(Project.model_validate_json(meta.read_text()))
          return sorted(projects, key=lambda p: p.created_at, reverse=True)

      def save(self, project: Project):
          self._save(project)

      def _save(self, project: Project):
          self._meta_path(project.project_id).write_text(
              project.model_dump_json(indent=2)
          )

  project_store = ProjectStore()
  ```
- [ ] Run tests → confirm they pass
- [ ] Commit: "feat: add FastAPI app, TaskManager, ProjectStore"

---

## Phase 2: Agents

### Task 5: ParserAgent

**Test first** (`backend/tests/test_agents/test_parser_agent.py`):
```python
import pytest
from pathlib import Path
from app.agents.parser_agent import ParserAgent

@pytest.fixture
def tmp_txt(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("A" * 600, encoding="utf-8")
    return str(f)

def test_parser_creates_chunks(tmp_txt):
    agent = ParserAgent()
    chunks = agent.run([tmp_txt], file_type="note")
    assert len(chunks) > 1
    assert all(c.source_file == "test.txt" for c in chunks)
    assert all(c.file_type == "note" for c in chunks)

def test_chunk_overlap(tmp_txt):
    agent = ParserAgent()
    chunks = agent.run([tmp_txt], file_type="note")
    if len(chunks) >= 2:
        c1_end = chunks[0].char_offset + len(chunks[0].text)
        assert c1_end > chunks[1].char_offset
```

- [ ] Run tests → confirm they fail
- [ ] Implement `backend/app/agents/parser_agent.py`:
  ```python
  import uuid
  from pathlib import Path
  from app.models.graph import TextChunk
  from app.utils.file_parser import extract_text
  from app.config import config
  from app.utils.logger import get_logger

  logger = get_logger(__name__)

  class ParserAgent:
      def __init__(self):
          self.chunk_size = config.CHUNK_SIZE
          self.overlap = config.CHUNK_OVERLAP

      def run(self, file_paths: list[str], file_type: str = "note") -> list[TextChunk]:
          chunks = []
          for path in file_paths:
              logger.info(f"Parsing {path}")
              pages = extract_text(path)
              source_file = Path(path).name
              for text, page_num in pages:
                  chunks.extend(self._chunk_text(text, source_file, file_type, page_num))
          return chunks

      def _chunk_text(
          self, text: str, source_file: str, file_type: str, page_num
      ) -> list[TextChunk]:
          chunks = []
          offset = 0
          while offset < len(text):
              end = min(offset + self.chunk_size, len(text))
              chunk_text = text[offset:end].strip()
              if chunk_text:
                  chunks.append(TextChunk(
                      chunk_id=str(uuid.uuid4()),
                      text=chunk_text,
                      source_file=source_file,
                      file_type=file_type,
                      page_num=page_num,
                      char_offset=offset,
                  ))
              offset += self.chunk_size - self.overlap
          return chunks
  ```
- [ ] Run tests → confirm they pass
- [ ] Commit: "feat: ParserAgent — PDF/DOCX/TXT chunking with overlap"

---

### Task 6: OntologyAgent

**Test first** (`backend/tests/test_agents/test_ontology_agent.py`):
```python
import pytest
from unittest.mock import AsyncMock, patch
from app.agents.ontology_agent import OntologyAgent
from app.models.graph import TextChunk

MOCK_RESPONSE = {
    "entity_types": [
        {"name": "Person", "description": "사람", "examples": ["Yang Pilseong"]},
        {"name": "Skill", "description": "기술", "examples": ["Python"]}
    ],
    "edge_types": [
        {"name": "USES_SKILL", "description": "기술 사용",
         "source_types": ["Person"], "target_types": ["Skill"]}
    ],
    "analysis_summary": "커리어 중심 온톨로지"
}

@pytest.mark.asyncio
async def test_ontology_agent_output():
    agent = OntologyAgent()
    chunks = [TextChunk("id1", "Yang Pilseong은 Python 전문가", "cv.pdf", "cv", 1, 0)]
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_RESPONSE)):
        ontology = await agent.run(chunks)
    assert len(ontology.entity_types) == 2
    assert ontology.entity_types[0].name == "Person"

@pytest.mark.asyncio
async def test_ontology_uses_fixed_types():
    agent = OntologyAgent()
    assert "Person" in agent.FIXED_ENTITY_TYPES
    assert "Project" in agent.FIXED_ENTITY_TYPES
```

- [ ] Run tests → confirm they fail
- [ ] Implement `backend/app/agents/ontology_agent.py`:
  ```python
  from app.models.graph import TextChunk, Ontology, EntityTypeDef, EdgeTypeDef
  from app.utils.llm_client import LLMClient
  from app.config import config
  from app.utils.logger import get_logger

  logger = get_logger(__name__)

  class OntologyAgent:
      FIXED_ENTITY_TYPES = [
          "Person", "Project", "Skill", "Organization", "Publication",
          "Technology", "Role", "Achievement", "Event", "Institution",
      ]
      FIXED_EDGE_TYPES = [
          "WORKED_AT", "DEVELOPED", "USES_SKILL", "AUTHORED",
          "COLLABORATED_WITH", "ACHIEVED", "PARTICIPATED_IN",
          "PUBLISHED_AT", "MENTORED_BY", "LED_BY",
      ]

      def __init__(self):
          self._llm = LLMClient()

      async def run(self, chunks: list[TextChunk]) -> Ontology:
          sample = self._build_sample(chunks)
          logger.info(f"OntologyAgent: analysing {len(sample)} chars")
          prompt = self._build_prompt(sample)
          result = await self._llm.chat_json([{"role": "user", "content": prompt}])
          return self._parse_result(result)

      def _build_sample(self, chunks: list[TextChunk]) -> str:
          texts = [c.text for c in chunks]
          combined = "\n\n".join(texts)
          return combined[:config.MAX_ONTOLOGY_SAMPLE_CHARS]

      def _build_prompt(self, sample: str) -> str:
          fixed_entities = ", ".join(self.FIXED_ENTITY_TYPES)
          fixed_edges = ", ".join(self.FIXED_EDGE_TYPES)
          return f"""다음 문서를 분석하여 커리어/프로젝트 지식 그래프를 위한 온톨로지를 정의하세요.

고정 엔티티 타입 (반드시 포함): {fixed_entities}
고정 관계 타입 (반드시 포함): {fixed_edges}

문서 내용:
{sample}

다음 JSON 형식으로 응답하세요:
{{
  "entity_types": [
    {{"name": "Person", "description": "개인/사람 엔티티", "examples": ["양필성", "김철수"]}}
  ],
  "edge_types": [
    {{"name": "WORKED_AT", "description": "근무 관계", "source_types": ["Person"], "target_types": ["Organization"]}}
  ],
  "analysis_summary": "문서 요약 및 도메인 특성 설명"
}}"""

      def _parse_result(self, result: dict) -> Ontology:
          entity_types = [
              EntityTypeDef(
                  name=e["name"],
                  description=e.get("description", ""),
                  examples=e.get("examples", []),
              )
              for e in result.get("entity_types", [])
          ]
          edge_types = [
              EdgeTypeDef(
                  name=e["name"],
                  description=e.get("description", ""),
                  source_types=e.get("source_types", []),
                  target_types=e.get("target_types", []),
              )
              for e in result.get("edge_types", [])
          ]
          return Ontology(
              entity_types=entity_types,
              edge_types=edge_types,
              analysis_summary=result.get("analysis_summary", ""),
          )
  ```
- [ ] Run tests → confirm they pass
- [ ] Commit: "feat: OntologyAgent — LLM-based entity/relation type extraction"

---

### Task 7: GraphBuilderAgent

**Test first** (`backend/tests/test_agents/test_graph_builder_agent.py`):
```python
import pytest
from unittest.mock import AsyncMock, patch
import networkx as nx
from app.agents.graph_builder_agent import GraphBuilderAgent
from app.models.graph import TextChunk, Ontology, EntityTypeDef, EdgeTypeDef

MOCK_EXTRACT = {
    "entities": [
        {"type": "Person", "name": "Yang Pilseong", "description": "ML 연구자"},
        {"type": "Skill", "name": "Python", "description": "프로그래밍 언어"},
    ],
    "relations": [
        {"source": "Yang Pilseong", "source_type": "Person",
         "target": "Python", "target_type": "Skill",
         "relation": "USES_SKILL", "confidence": 0.95}
    ]
}

@pytest.fixture
def sample_ontology():
    return Ontology(
        entity_types=[EntityTypeDef("Person", "사람", []), EntityTypeDef("Skill", "기술", [])],
        edge_types=[EdgeTypeDef("USES_SKILL", "기술 사용", ["Person"], ["Skill"])],
        analysis_summary="test"
    )

@pytest.mark.asyncio
async def test_graph_builder_creates_nodes(sample_ontology):
    agent = GraphBuilderAgent()
    chunks = [TextChunk("id1", "Yang Pilseong은 Python 전문가", "cv.pdf", "cv", 1, 0)]
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_EXTRACT)):
        graph = await agent.run(chunks, sample_ontology)
    assert "Person:Yang Pilseong" in graph.nodes
    assert "Skill:Python" in graph.nodes
    assert graph.number_of_edges() >= 1

def test_fuzzy_match_deduplication():
    agent = GraphBuilderAgent()
    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong")
    existing = agent._find_existing_node(g, "Person", "yang pilseong")
    assert existing == "Person:Yang Pilseong"

def test_fuzzy_match_no_match():
    agent = GraphBuilderAgent()
    g = nx.DiGraph()
    g.add_node("Person:Kim Chulsoo", type="Person", name="Kim Chulsoo")
    existing = agent._find_existing_node(g, "Person", "Lee Younghee")
    assert existing is None
```

- [ ] Run tests → confirm they fail
- [ ] Implement `backend/app/agents/graph_builder_agent.py`:
  ```python
  import json
  import networkx as nx
  from difflib import SequenceMatcher
  from pathlib import Path
  from app.models.graph import TextChunk, Ontology, GraphStats
  from app.utils.llm_client import LLMClient
  from app.config import config
  from app.utils.logger import get_logger

  logger = get_logger(__name__)

  class GraphBuilderAgent:
      def __init__(self):
          self._llm = LLMClient()
          self._fuzzy_threshold = config.FUZZY_MATCH_THRESHOLD

      async def run(
          self,
          chunks: list[TextChunk],
          ontology: Ontology,
          incremental: bool = False,
          graph_path: str | None = None,
      ) -> nx.DiGraph:
          graph = nx.DiGraph()
          if incremental and graph_path and Path(graph_path).exists():
              data = json.loads(Path(graph_path).read_text())
              graph = nx.node_link_graph(data)
              logger.info(f"Loaded existing graph: {graph.number_of_nodes()} nodes")

          entity_types = [e.name for e in ontology.entity_types]
          edge_types = [e.name for e in ontology.edge_types]

          for i, chunk in enumerate(chunks):
              logger.info(f"Processing chunk {i+1}/{len(chunks)}")
              try:
                  result = await self._extract_from_chunk(chunk, entity_types, edge_types)
                  self._merge_into_graph(graph, result, chunk)
              except Exception as e:
                  logger.error(f"Chunk {chunk.chunk_id} failed: {e}")

          return graph

      async def _extract_from_chunk(
          self, chunk: TextChunk, entity_types: list[str], edge_types: list[str]
      ) -> dict:
          prompt = f"""다음 텍스트에서 엔티티와 관계를 추출하세요.

엔티티 타입: {', '.join(entity_types)}
관계 타입: {', '.join(edge_types)}

텍스트:
{chunk.text}

JSON 형식으로 응답:
{{
  "entities": [
    {{"type": "Person", "name": "이름", "description": "설명"}}
  ],
  "relations": [
    {{"source": "이름", "source_type": "Person",
      "target": "대상", "target_type": "Skill",
      "relation": "USES_SKILL", "confidence": 0.9}}
  ]
}}"""
          return await self._llm.chat_json([{"role": "user", "content": prompt}])

      def _merge_into_graph(self, graph: nx.DiGraph, result: dict, chunk: TextChunk):
          node_map: dict[str, str] = {}
          for entity in result.get("entities", []):
              etype = entity.get("type", "")
              name = entity.get("name", "").strip()
              if not etype or not name:
                  continue
              existing = self._find_existing_node(graph, etype, name)
              if existing:
                  node_id = existing
                  node = graph.nodes[node_id]
                  sources = set(node.get("source_files", []))
                  sources.add(chunk.source_file)
                  graph.nodes[node_id]["source_files"] = list(sources)
              else:
                  node_id = f"{etype}:{name}"
                  graph.add_node(node_id,
                      type=etype, name=name,
                      description=entity.get("description", ""),
                      source_files=[chunk.source_file],
                      attributes={},
                  )
              node_map[name] = node_id

          for rel in result.get("relations", []):
              src_name = rel.get("source", "")
              tgt_name = rel.get("target", "")
              relation = rel.get("relation", "")
              if not src_name or not tgt_name or not relation:
                  continue
              src_id = node_map.get(src_name)
              tgt_id = node_map.get(tgt_name)
              if src_id and tgt_id and src_id in graph and tgt_id in graph:
                  graph.add_edge(src_id, tgt_id,
                      relation=relation,
                      confidence=rel.get("confidence", 1.0),
                      source_chunk_id=chunk.chunk_id,
                  )

      def _find_existing_node(self, graph: nx.DiGraph, entity_type: str, name: str) -> str | None:
          for node_id in graph.nodes:
              node = graph.nodes[node_id]
              if node.get("type") == entity_type:
                  if self._fuzzy_match(node.get("name", ""), name):
                      return node_id
          return None

      def _fuzzy_match(self, a: str, b: str) -> bool:
          return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= self._fuzzy_threshold

      def save(self, graph: nx.DiGraph, path: str):
          Path(path).parent.mkdir(parents=True, exist_ok=True)
          data = nx.node_link_data(graph)
          Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))

      def get_stats(self, graph: nx.DiGraph) -> GraphStats:
          nodes_by_type: dict[str, int] = {}
          for n in graph.nodes:
              t = graph.nodes[n].get("type", "Unknown")
              nodes_by_type[t] = nodes_by_type.get(t, 0) + 1
          edges_by_type: dict[str, int] = {}
          for u, v, data in graph.edges(data=True):
              r = data.get("relation", "UNKNOWN")
              edges_by_type[r] = edges_by_type.get(r, 0) + 1
          return GraphStats(
              total_nodes=graph.number_of_nodes(),
              total_edges=graph.number_of_edges(),
              nodes_by_type=nodes_by_type,
              edges_by_type=edges_by_type,
          )
  ```
- [ ] Run tests → confirm they pass
- [ ] Commit: "feat: GraphBuilderAgent — NetworkX graph with fuzzy deduplication + incremental mode"

---

### Task 8: ProfileAgent

**Test first** (`backend/tests/test_agents/test_profile_agent.py`):
```python
import pytest
from unittest.mock import AsyncMock, patch
import networkx as nx
from app.agents.profile_agent import ProfileAgent

MOCK_PROFILE_RESPONSE = {
    "expertise": ["Machine Learning", "NLP"],
    "skills": ["Python", "PyTorch"],
    "projects": ["ProjectOS"],
    "organizations": ["KAIST"],
    "publications": [],
    "achievements": ["우수 논문상"],
    "persona_summary": "ML 전문 연구자로 NLP와 그래프 AI에 강점이 있다.",
    "timeline": [{"year": 2020, "event": "KAIST 입학"}]
}

@pytest.fixture
def sample_graph():
    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong", description="ML 연구자")
    g.add_node("Skill:Python", type="Skill", name="Python")
    g.add_node("Organization:KAIST", type="Organization", name="KAIST")
    g.add_edge("Person:Yang Pilseong", "Skill:Python", relation="USES_SKILL")
    g.add_edge("Person:Yang Pilseong", "Organization:KAIST", relation="WORKED_AT")
    return g

@pytest.mark.asyncio
async def test_profile_agent_creates_profile(sample_graph):
    agent = ProfileAgent()
    with patch.object(agent._llm, "chat_json", new=AsyncMock(return_value=MOCK_PROFILE_RESPONSE)):
        profiles = await agent.run(sample_graph)
    assert len(profiles) == 1
    assert profiles[0].name == "Yang Pilseong"
    assert "Python" in profiles[0].skills
```

- [ ] Run tests → confirm they fail
- [ ] Implement `backend/app/agents/profile_agent.py`:
  ```python
  import json
  import networkx as nx
  from app.models.graph import CareerProfile
  from app.utils.llm_client import LLMClient
  from app.utils.logger import get_logger

  logger = get_logger(__name__)

  class ProfileAgent:
      def __init__(self):
          self._llm = LLMClient()

      async def run(self, graph: nx.DiGraph) -> list[CareerProfile]:
          person_nodes = [
              (nid, data) for nid, data in graph.nodes(data=True)
              if data.get("type") == "Person"
          ]
          profiles = []
          for node_id, node_data in person_nodes:
              logger.info(f"ProfileAgent: building profile for {node_data['name']}")
              context = self._collect_context(graph, node_id)
              profile = await self._generate_profile(node_data["name"], context)
              profiles.append(profile)
          return profiles

      def _collect_context(self, graph: nx.DiGraph, person_id: str) -> dict:
          context: dict[str, list] = {
              "skills": [], "projects": [], "organizations": [],
              "publications": [], "achievements": [], "roles": [],
          }
          type_map = {
              "Skill": "skills", "Project": "projects",
              "Organization": "organizations", "Publication": "publications",
              "Achievement": "achievements", "Role": "roles",
          }
          visited = {person_id}
          queue = list(graph.successors(person_id)) + list(graph.predecessors(person_id))
          while queue:
              nid = queue.pop(0)
              if nid in visited:
                  continue
              visited.add(nid)
              ntype = graph.nodes[nid].get("type", "")
              name = graph.nodes[nid].get("name", "")
              key = type_map.get(ntype)
              if key and name not in context[key]:
                  context[key].append(name)
              if len(visited) < 50:
                  queue.extend(graph.successors(nid))
                  queue.extend(graph.predecessors(nid))
          return context

      async def _generate_profile(self, name: str, context: dict) -> CareerProfile:
          prompt = f"""다음 커리어 정보를 바탕으로 종합적인 커리어 프로필을 생성하세요.

이름: {name}
기술 스택: {', '.join(context['skills'])}
주요 프로젝트: {', '.join(context['projects'])}
소속 기관: {', '.join(context['organizations'])}
논문/출판물: {', '.join(context['publications'])}
성과: {', '.join(context['achievements'])}

JSON 형식으로 응답 (한국어 중심):
{{
  "expertise": ["주요 전문 분야 목록"],
  "skills": ["기술 스택 목록"],
  "projects": ["프로젝트 목록"],
  "organizations": ["기관 목록"],
  "publications": ["논문 목록"],
  "achievements": ["성과 목록"],
  "persona_summary": "2000자 내외 종합 커리어 요약 (한국어)",
  "timeline": [{{"year": 2020, "event": "사건"}}]
}}"""
          result = await self._llm.chat_json([{"role": "user", "content": prompt}])
          return CareerProfile(
              name=name,
              expertise=result.get("expertise", []),
              skills=result.get("skills", context["skills"]),
              projects=result.get("projects", context["projects"]),
              organizations=result.get("organizations", context["organizations"]),
              publications=result.get("publications", context["publications"]),
              achievements=result.get("achievements", context["achievements"]),
              persona_summary=result.get("persona_summary", ""),
              timeline=result.get("timeline", []),
          )
  ```
- [ ] Run tests → confirm they pass
- [ ] Commit: "feat: ProfileAgent — BFS context collection + LLM persona generation"

---

### Task 9: ObsidianWriterAgent

**Test first** (`backend/tests/test_agents/test_obsidian_writer_agent.py`):
```python
import pytest
import networkx as nx
from pathlib import Path
from app.agents.obsidian_writer_agent import ObsidianWriterAgent
from app.models.graph import CareerProfile

@pytest.fixture
def sample_graph():
    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong",
               description="ML 연구자", source_files=["cv.pdf"])
    g.add_node("Skill:Python", type="Skill", name="Python",
               description="프로그래밍 언어", source_files=["cv.pdf"])
    g.add_edge("Person:Yang Pilseong", "Skill:Python", relation="USES_SKILL")
    return g

@pytest.fixture
def sample_profile():
    return CareerProfile(
        name="Yang Pilseong", expertise=["ML"],
        skills=["Python"], projects=[], organizations=[],
        publications=[], achievements=[],
        persona_summary="ML 연구자", timeline=[]
    )

def test_obsidian_writer_creates_files(tmp_path, sample_graph, sample_profile):
    writer = ObsidianWriterAgent()
    writer.run(sample_graph, [sample_profile], vault_path=str(tmp_path))
    assert (tmp_path / "Career" / "Yang Pilseong.md").exists()
    assert (tmp_path / "Skills" / "Python.md").exists()
    assert (tmp_path / ".obsidian").exists()

def test_obsidian_note_has_frontmatter(tmp_path, sample_graph, sample_profile):
    writer = ObsidianWriterAgent()
    writer.run(sample_graph, [sample_profile], vault_path=str(tmp_path))
    content = (tmp_path / "Career" / "Yang Pilseong.md").read_text()
    assert "---" in content
    assert "type: Person" in content

def test_obsidian_note_has_wikilinks(tmp_path, sample_graph, sample_profile):
    writer = ObsidianWriterAgent()
    writer.run(sample_graph, [sample_profile], vault_path=str(tmp_path))
    content = (tmp_path / "Career" / "Yang Pilseong.md").read_text()
    assert "[[Python]]" in content
```

- [ ] Run tests → confirm they fail
- [ ] Implement `backend/app/agents/obsidian_writer_agent.py`:
  ```python
  import json
  import re
  from datetime import date
  from pathlib import Path
  import networkx as nx
  from app.models.graph import CareerProfile
  from app.config import config
  from app.utils.logger import get_logger

  logger = get_logger(__name__)

  TYPE_TO_FOLDER = {
      "Person": "Career", "Project": "Projects", "Skill": "Skills",
      "Organization": "Organizations", "Publication": "Publications",
      "Technology": "Technologies", "Role": "Roles",
      "Achievement": "Achievements", "Event": "Events", "Institution": "Institutions",
  }

  class ObsidianWriterAgent:
      def run(
          self,
          graph: nx.DiGraph,
          profiles: list[CareerProfile],
          vault_path: str | None = None,
          delta: bool = False,
      ):
          vault = Path(vault_path or config.VAULT_DIR)
          self._setup_vault(vault)
          profile_map = {p.name: p for p in profiles}

          for node_id, data in graph.nodes(data=True):
              ntype = data.get("type", "Unknown")
              folder = TYPE_TO_FOLDER.get(ntype, "Misc")
              folder_path = vault / folder
              folder_path.mkdir(parents=True, exist_ok=True)
              note_path = folder_path / f"{data['name']}.md"

              successors = [
                  (graph.nodes[s]["name"], graph.edges[node_id, s].get("relation", ""))
                  for s in graph.successors(node_id)
                  if "name" in graph.nodes[s]
              ]
              predecessors = [
                  (graph.nodes[p]["name"], graph.edges[p, node_id].get("relation", ""))
                  for p in graph.predecessors(node_id)
                  if "name" in graph.nodes[p]
              ]

              profile = profile_map.get(data["name"])
              content = self._render_note(data, successors, predecessors, profile)

              if delta and note_path.exists():
                  content = self._merge_note(note_path.read_text(), content)

              note_path.write_text(content, encoding="utf-8")
              logger.info(f"Written: {note_path}")

          self._write_canvas(vault, graph)

      def _setup_vault(self, vault: Path):
          vault.mkdir(parents=True, exist_ok=True)
          obsidian_dir = vault / ".obsidian"
          obsidian_dir.mkdir(exist_ok=True)
          (obsidian_dir / "app.json").write_text(
              json.dumps({"defaultViewMode": "source", "livePreview": True}, indent=2)
          )
          graph_config = {
              "colorGroups": [
                  {"query": f'tag:#{t.lower()}', "color": {"a": 1, "rgb": c}}
                  for t, c in [("person", 4756697), ("project", 6008155), ("skill", 15246392)]
              ]
          }
          (obsidian_dir / "graph.json").write_text(json.dumps(graph_config, indent=2))

      def _render_note(
          self, data: dict, successors: list, predecessors: list, profile: CareerProfile | None
      ) -> str:
          name = data["name"]
          ntype = data.get("type", "Unknown")
          desc = data.get("description", "")
          sources = data.get("source_files", [])
          today = date.today().isoformat()
          tags = [ntype.lower()]

          lines = [
              "---",
              f"type: {ntype}",
              f'name: "{name}"',
              f"tags: [{', '.join(tags)}]",
              f"created: {today}",
              f"sources: [{', '.join(sources)}]",
              "---",
              "",
              f"# {name}",
              "",
              "## Overview",
              desc or "(No description)",
              "",
          ]

          if profile:
              lines += [
                  "## Career Summary",
                  profile.persona_summary,
                  "",
                  "## Skills",
                  *[f"- [[{s}]]" for s in profile.skills],
                  "",
                  "## Timeline",
                  *[f"- **{t['year']}**: {t['event']}" for t in profile.timeline],
                  "",
              ]

          if successors or predecessors:
              lines += ["## Connections", ""]
              for target_name, relation in successors:
                  lines.append(f"- {relation}: [[{target_name}]]")
              for source_name, relation in predecessors:
                  lines.append(f"- ← {relation}: [[{source_name}]]")
              lines.append("")

          return "\n".join(lines)

      def _merge_note(self, existing: str, new_content: str) -> str:
          new_wikilinks = set(re.findall(r'\[\[([^\]]+)\]\]', new_content))
          existing_wikilinks = set(re.findall(r'\[\[([^\]]+)\]\]', existing))
          missing = new_wikilinks - existing_wikilinks
          if missing:
              additions = "\n".join(f"- [[{link}]]" for link in sorted(missing))
              existing = existing.rstrip() + f"\n\n## New Connections\n{additions}\n"
          return existing

      def _write_canvas(self, vault: Path, graph: nx.DiGraph):
          nodes_canvas = []
          edges_canvas = []
          positions: dict[str, tuple[float, float]] = {}
          x, y = 0.0, 0.0
          for i, node_id in enumerate(graph.nodes):
              x = (i % 10) * 250.0
              y = (i // 10) * 200.0
              positions[node_id] = (x, y)
              nodes_canvas.append({
                  "id": node_id.replace(":", "_"),
                  "type": "text",
                  "text": graph.nodes[node_id].get("name", node_id),
                  "x": x, "y": y, "width": 200, "height": 60,
              })
          for u, v, data in graph.edges(data=True):
              edges_canvas.append({
                  "id": f"{u}_{v}".replace(":", "_"),
                  "fromNode": u.replace(":", "_"),
                  "fromSide": "right",
                  "toNode": v.replace(":", "_"),
                  "toSide": "left",
                  "label": data.get("relation", ""),
              })
          canvas = {"nodes": nodes_canvas, "edges": edges_canvas}
          (vault / "_index.canvas").write_text(
              json.dumps(canvas, indent=2, ensure_ascii=False), encoding="utf-8"
          )
  ```
- [ ] Run tests → confirm they pass
- [ ] Commit: "feat: ObsidianWriterAgent — vault markdown with wikilinks, frontmatter, canvas"

---

### Task 10: QueryAgent

**Test first** (`backend/tests/test_agents/test_query_agent.py`):
```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import networkx as nx
from app.agents.query_agent import QueryAgent
from app.models.graph import TextChunk

@pytest.fixture
def sample_graph():
    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong")
    g.add_node("Skill:Python", type="Skill", name="Python")
    g.add_edge("Person:Yang Pilseong", "Skill:Python", relation="USES_SKILL")
    return g

@pytest.mark.asyncio
async def test_query_agent_returns_context(sample_graph):
    agent = QueryAgent()
    chunks = [TextChunk("id1", "Yang Pilseong은 Python 사용", "cv.pdf", "cv", 1, 0)]
    context = agent._search_graph(sample_graph, "Yang Pilseong Python")
    assert len(context["nodes"]) > 0

@pytest.mark.asyncio
async def test_query_agent_stream(sample_graph):
    agent = QueryAgent()
    chunks = [TextChunk("id1", "test", "cv.pdf", "cv", 1, 0)]

    async def mock_stream(*args, **kwargs):
        for token in ["답변", " 내용"]:
            yield token

    with patch.object(agent._llm, "stream", side_effect=mock_stream):
        tokens = []
        async for token in agent.stream("Python 기술은?", sample_graph, chunks):
            tokens.append(token)
    assert len(tokens) > 0
```

- [ ] Run tests → confirm they fail
- [ ] Implement `backend/app/agents/query_agent.py`:
  ```python
  import networkx as nx
  from app.models.graph import TextChunk
  from app.utils.llm_client import LLMClient
  from app.utils.logger import get_logger

  logger = get_logger(__name__)

  class QueryAgent:
      def __init__(self):
          self._llm = LLMClient()

      async def stream(
          self,
          question: str,
          graph: nx.DiGraph,
          chunks: list[TextChunk],
      ):
          context = self._search_graph(graph, question)
          relevant_chunks = self._find_relevant_chunks(chunks, question)
          prompt = self._build_prompt(question, context, relevant_chunks)
          async for token in self._llm.stream([{"role": "user", "content": prompt}]):
              yield token

      def _search_graph(self, graph: nx.DiGraph, query: str) -> dict:
          query_lower = query.lower()
          matched_nodes = []
          for node_id, data in graph.nodes(data=True):
              name = data.get("name", "").lower()
              desc = data.get("description", "").lower()
              if any(word in name or word in desc for word in query_lower.split()):
                  matched_nodes.append({
                      "id": node_id,
                      "type": data.get("type"),
                      "name": data.get("name"),
                      "description": data.get("description"),
                  })

          connected_edges = []
          node_ids = {n["id"] for n in matched_nodes}
          for u, v, data in graph.edges(data=True):
              if u in node_ids or v in node_ids:
                  connected_edges.append({
                      "source": graph.nodes[u].get("name"),
                      "target": graph.nodes[v].get("name"),
                      "relation": data.get("relation"),
                  })

          bfs_nodes = []
          for node_id in list(node_ids)[:3]:
              for neighbor in list(graph.successors(node_id)) + list(graph.predecessors(node_id)):
                  if neighbor not in node_ids:
                      ndata = graph.nodes[neighbor]
                      bfs_nodes.append({"type": ndata.get("type"), "name": ndata.get("name")})

          return {"nodes": matched_nodes, "edges": connected_edges, "related": bfs_nodes}

      def _find_relevant_chunks(self, chunks: list[TextChunk], query: str) -> list[str]:
          query_words = set(query.lower().split())
          scored = []
          for chunk in chunks:
              words = set(chunk.text.lower().split())
              score = len(query_words & words)
              if score > 0:
                  scored.append((score, chunk.text))
          scored.sort(reverse=True)
          return [text for _, text in scored[:3]]

      def _build_prompt(self, question: str, context: dict, chunks: list[str]) -> str:
          nodes_str = "\n".join(
              f"- [{n['type']}] {n['name']}: {n['description']}"
              for n in context["nodes"]
          )
          edges_str = "\n".join(
              f"- {e['source']} --{e['relation']}--> {e['target']}"
              for e in context["edges"]
          )
          chunks_str = "\n\n".join(chunks)
          return f"""다음 지식 그래프 컨텍스트와 원본 문서를 바탕으로 질문에 답하세요.

## 관련 노드
{nodes_str or "(없음)"}

## 관련 관계
{edges_str or "(없음)"}

## 원본 문서 발췌
{chunks_str or "(없음)"}

## 질문
{question}

한국어로 상세히 답변하세요. 그래프의 관계를 활용하여 연결된 정보를 포함하세요."""
  ```
- [ ] Run tests → confirm they pass
- [ ] Commit: "feat: QueryAgent — BFS graph search + SSE streaming chat"

---

## Phase 3: FastAPI Backend

### Task 11: Projects API

**Test first** (`backend/tests/test_api/test_projects.py`):
```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)

def test_create_project():
    r = client.post("/api/projects", json={"name": "Test", "description": "desc"})
    assert r.status_code == 201
    assert r.json()["name"] == "Test"
    assert "project_id" in r.json()

def test_list_projects():
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

def test_upload_files(tmp_path):
    proj = client.post("/api/projects", json={"name": "File Test"}).json()
    pid = proj["project_id"]
    content = b"test content"
    r = client.post(
        f"/api/projects/{pid}/files",
        files=[("files", ("test.txt", content, "text/plain"))],
        data={"file_type": "note"},
    )
    assert r.status_code == 200
    assert "task_id" in r.json()
```

- [ ] Run tests → confirm they fail
- [ ] Implement `backend/app/api/projects.py`:
  ```python
  import asyncio
  from fastapi import APIRouter, UploadFile, File, Form, HTTPException
  from fastapi.responses import FileResponse
  from pathlib import Path
  import aiofiles
  import zipfile
  import tempfile
  from app.services.project_store import project_store
  from app.services.task_manager import task_manager
  from app.agents.parser_agent import ParserAgent
  from app.models.project import TaskStatus
  from app.config import config

  router = APIRouter()

  @router.post("", status_code=201)
  async def create_project(body: dict):
      project = project_store.create(body["name"], body.get("description", ""))
      return project.model_dump()

  @router.get("")
  async def list_projects():
      return [p.model_dump() for p in project_store.list_all()]

  @router.get("/{project_id}")
  async def get_project(project_id: str):
      project = project_store.get(project_id)
      if not project:
          raise HTTPException(404, "Project not found")
      return project.model_dump()

  @router.delete("/{project_id}")
  async def delete_project(project_id: str):
      project = project_store.get(project_id)
      if not project:
          raise HTTPException(404, "Project not found")
      import shutil
      shutil.rmtree(Path(config.PROJECTS_DIR) / project_id, ignore_errors=True)
      return {"ok": True}

  @router.post("/{project_id}/files")
  async def upload_files(
      project_id: str,
      files: list[UploadFile] = File(...),
      file_type: str = Form("note"),
  ):
      project = project_store.get(project_id)
      if not project:
          raise HTTPException(404, "Project not found")
      files_dir = Path(config.PROJECTS_DIR) / project_id / "files"
      files_dir.mkdir(exist_ok=True)
      saved_paths = []
      for f in files:
          dest = files_dir / f.filename
          async with aiofiles.open(dest, "wb") as out:
              await out.write(await f.read())
          saved_paths.append(str(dest))

      task = task_manager.create(project_id, "parse")
      asyncio.create_task(_run_parse(task.task_id, project_id, saved_paths, file_type))
      return {"task_id": task.task_id, "files": [f.filename for f in files]}

  @router.post("/{project_id}/files/add")
  async def add_files(
      project_id: str,
      files: list[UploadFile] = File(...),
      file_type: str = Form("note"),
  ):
      return await upload_files(project_id, files=files, file_type=file_type)

  @router.get("/{project_id}/vault")
  async def get_vault_tree(project_id: str):
      vault = Path(config.VAULT_DIR)
      if not vault.exists():
          return []
      tree = _build_tree(vault)
      return tree

  @router.get("/{project_id}/vault/download")
  async def download_vault(project_id: str):
      vault = Path(config.VAULT_DIR)
      tmp = tempfile.mktemp(suffix=".zip")
      with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
          for f in vault.rglob("*"):
              if f.is_file():
                  zf.write(f, f.relative_to(vault))
      return FileResponse(tmp, filename="vault.zip", media_type="application/zip")

  def _build_tree(path: Path) -> list:
      result = []
      for child in sorted(path.iterdir()):
          if child.name.startswith("."):
              continue
          if child.is_dir():
              result.append({"name": child.name, "type": "folder", "children": _build_tree(child)})
          else:
              result.append({"name": child.name, "type": "file", "path": str(child)})
      return result

  async def _run_parse(task_id: str, project_id: str, paths: list[str], file_type: str):
      import json
      from pathlib import Path as P
      try:
          task_manager.update(task_id, status=TaskStatus.RUNNING, message="파싱 시작")
          agent = ParserAgent()
          chunks = agent.run(paths, file_type=file_type)
          out = P(config.PROJECTS_DIR) / project_id / "chunks.json"
          existing = json.loads(out.read_text()) if out.exists() else []
          combined = existing + [vars(c) for c in chunks]
          out.write_text(json.dumps(combined, indent=2, ensure_ascii=False))
          task_manager.update(task_id, status=TaskStatus.COMPLETED,
                              progress=100, message=f"{len(chunks)}개 청크 생성")
      except Exception as e:
          task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))
  ```
- [ ] Run tests → confirm they pass
- [ ] Commit: "feat: projects API — create, list, upload files with async parse"

---

### Task 12: Graph / Ontology API + SSE

- [ ] Implement `backend/app/api/graph.py`:
  ```python
  import asyncio
  import json
  from pathlib import Path
  from fastapi import APIRouter, HTTPException
  from fastapi.responses import StreamingResponse
  from app.services.project_store import project_store
  from app.services.task_manager import task_manager
  from app.models.project import TaskStatus
  from app.config import config

  router = APIRouter()

  @router.post("/{project_id}/ontology")
  async def run_ontology(project_id: str):
      project = project_store.get(project_id)
      if not project:
          raise HTTPException(404, "Project not found")
      task = task_manager.create(project_id, "ontology")
      asyncio.create_task(_run_ontology(task.task_id, project_id))
      return {"task_id": task.task_id}

  @router.get("/{project_id}/ontology")
  async def get_ontology(project_id: str):
      p = Path(config.PROJECTS_DIR) / project_id / "ontology.json"
      if not p.exists():
          raise HTTPException(404, "Ontology not built yet")
      return json.loads(p.read_text())

  @router.post("/{project_id}/graph")
  async def run_graph(project_id: str):
      project = project_store.get(project_id)
      if not project:
          raise HTTPException(404, "Project not found")
      task = task_manager.create(project_id, "graph")
      asyncio.create_task(_run_graph(task.task_id, project_id, incremental=False))
      return {"task_id": task.task_id}

  @router.post("/{project_id}/graph/incremental")
  async def run_graph_incremental(project_id: str):
      project = project_store.get(project_id)
      if not project:
          raise HTTPException(404, "Project not found")
      task = task_manager.create(project_id, "graph_incremental")
      asyncio.create_task(_run_graph(task.task_id, project_id, incremental=True))
      return {"task_id": task.task_id}

  @router.get("/{project_id}/graph")
  async def get_graph(project_id: str):
      p = Path(config.PROJECTS_DIR) / project_id / "graph.json"
      if not p.exists():
          raise HTTPException(404, "Graph not built yet")
      return json.loads(p.read_text())

  @router.get("/{project_id}/graph/stats")
  async def get_graph_stats(project_id: str):
      p = Path(config.PROJECTS_DIR) / project_id / "graph.json"
      if not p.exists():
          raise HTTPException(404, "Graph not built yet")
      import networkx as nx
      from app.agents.graph_builder_agent import GraphBuilderAgent
      data = json.loads(p.read_text())
      graph = nx.node_link_graph(data)
      agent = GraphBuilderAgent()
      stats = agent.get_stats(graph)
      return vars(stats)

  @router.get("/{project_id}/profiles")
  async def get_profiles(project_id: str):
      p = Path(config.PROJECTS_DIR) / project_id / "profiles.json"
      if not p.exists():
          raise HTTPException(404, "Profiles not built yet")
      return json.loads(p.read_text())

  async def _run_ontology(task_id: str, project_id: str):
      from app.agents.ontology_agent import OntologyAgent
      from app.models.graph import TextChunk
      import dataclasses
      try:
          task_manager.update(task_id, status=TaskStatus.RUNNING, message="온톨로지 분석 시작")
          chunks_path = Path(config.PROJECTS_DIR) / project_id / "chunks.json"
          if not chunks_path.exists():
              raise ValueError("chunks.json not found — upload files first")
          chunks_data = json.loads(chunks_path.read_text())
          chunks = [TextChunk(**c) for c in chunks_data]
          agent = OntologyAgent()
          ontology = await agent.run(chunks)
          out = Path(config.PROJECTS_DIR) / project_id / "ontology.json"
          out.write_text(json.dumps(dataclasses.asdict(ontology), indent=2, ensure_ascii=False))
          task_manager.update(task_id, status=TaskStatus.COMPLETED, progress=100,
                              message=f"{len(ontology.entity_types)}개 엔티티 타입 생성")
      except Exception as e:
          task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))

  async def _run_graph(task_id: str, project_id: str, incremental: bool):
      import dataclasses
      from app.agents.graph_builder_agent import GraphBuilderAgent
      from app.agents.profile_agent import ProfileAgent
      from app.agents.obsidian_writer_agent import ObsidianWriterAgent
      from app.models.graph import TextChunk, Ontology, EntityTypeDef, EdgeTypeDef
      try:
          task_manager.update(task_id, status=TaskStatus.RUNNING, message="그래프 구축 시작", progress=10)
          proj_dir = Path(config.PROJECTS_DIR) / project_id
          chunks_data = json.loads((proj_dir / "chunks.json").read_text())
          chunks = [TextChunk(**c) for c in chunks_data]
          ont_data = json.loads((proj_dir / "ontology.json").read_text())
          ontology = Ontology(
              entity_types=[EntityTypeDef(**e) for e in ont_data["entity_types"]],
              edge_types=[EdgeTypeDef(**e) for e in ont_data["edge_types"]],
              analysis_summary=ont_data["analysis_summary"],
          )
          graph_path = str(proj_dir / "graph.json")
          graph_agent = GraphBuilderAgent()
          task_manager.update(task_id, message="엔티티/관계 추출 중...", progress=30)
          graph = await graph_agent.run(chunks, ontology, incremental=incremental, graph_path=graph_path)
          graph_agent.save(graph, graph_path)
          task_manager.update(task_id, message="프로필 생성 중...", progress=70)
          profile_agent = ProfileAgent()
          profiles = await profile_agent.run(graph)
          profiles_data = [dataclasses.asdict(p) for p in profiles]
          (proj_dir / "profiles.json").write_text(json.dumps(profiles_data, indent=2, ensure_ascii=False))
          task_manager.update(task_id, message="Obsidian vault 작성 중...", progress=85)
          writer = ObsidianWriterAgent()
          writer.run(graph, profiles, vault_path=config.VAULT_DIR, delta=incremental)
          stats = graph_agent.get_stats(graph)
          task_manager.update(task_id, status=TaskStatus.COMPLETED, progress=100,
                              message=f"완료: 노드 {stats.total_nodes}개, 엣지 {stats.total_edges}개")
      except Exception as e:
          task_manager.update(task_id, status=TaskStatus.FAILED, error=str(e))
  ```
- [ ] Implement `backend/app/api/tasks.py`:
  ```python
  import asyncio
  import json
  from fastapi import APIRouter, HTTPException
  from fastapi.responses import StreamingResponse
  from app.services.task_manager import task_manager

  router = APIRouter()

  @router.get("/{task_id}")
  async def get_task(task_id: str):
      task = task_manager.get(task_id)
      if not task:
          raise HTTPException(404, "Task not found")
      return task.model_dump()

  @router.get("/{task_id}/stream")
  async def stream_task(task_id: str):
      async def generate():
          while True:
              task = task_manager.get(task_id)
              if not task:
                  yield f"data: {json.dumps({'error': 'task not found'})}\n\n"
                  break
              payload = {
                  "status": task.status,
                  "progress": task.progress,
                  "message": task.message,
                  "error": task.error,
              }
              yield f"data: {json.dumps(payload)}\n\n"
              if task.status in ("completed", "failed"):
                  break
              await asyncio.sleep(1)
      return StreamingResponse(
          generate(),
          media_type="text/event-stream",
          headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
      )
  ```
- [ ] Commit: "feat: graph/ontology API with SSE task streaming"

---

### Task 13: Chat API

- [ ] Implement `backend/app/api/chat.py`:
  ```python
  import json
  from pathlib import Path
  from fastapi import APIRouter, HTTPException
  from fastapi.responses import StreamingResponse
  from app.agents.query_agent import QueryAgent
  from app.models.graph import TextChunk
  from app.config import config
  import networkx as nx

  router = APIRouter()

  @router.post("/{project_id}/chat")
  async def chat(project_id: str, body: dict):
      question = body.get("question", "")
      if not question:
          raise HTTPException(400, "question is required")

      proj_dir = Path(config.PROJECTS_DIR) / project_id
      graph_path = proj_dir / "graph.json"
      chunks_path = proj_dir / "chunks.json"

      if not graph_path.exists():
          raise HTTPException(404, "Graph not built yet")

      graph_data = json.loads(graph_path.read_text())
      graph = nx.node_link_graph(graph_data)
      chunks = []
      if chunks_path.exists():
          chunks_data = json.loads(chunks_path.read_text())
          chunks = [TextChunk(**c) for c in chunks_data]

      agent = QueryAgent()

      async def generate():
          async for token in agent.stream(question, graph, chunks):
              yield f"data: {json.dumps({'token': token})}\n\n"
          yield f"data: {json.dumps({'done': True})}\n\n"

      return StreamingResponse(
          generate(),
          media_type="text/event-stream",
          headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
      )
  ```
- [ ] Commit: "feat: chat API — SSE streaming QueryAgent responses"

---

## Phase 4: Frontend

### Task 14: Vue Project Setup

- [ ] In `frontend/`, run: `npm create vite@latest . -- --template vue`
- [ ] Install dependencies:
  ```bash
  npm install element-plus @element-plus/icons-vue axios d3
  npm install -D @vitejs/plugin-vue
  ```
- [ ] Configure `frontend/vite.config.js`:
  ```js
  import { defineConfig } from 'vite'
  import vue from '@vitejs/plugin-vue'

  export default defineConfig({
    plugins: [vue()],
    server: {
      proxy: {
        '/api': 'http://localhost:8000',
        '/health': 'http://localhost:8000',
      }
    }
  })
  ```
- [ ] Configure `frontend/src/main.js`:
  ```js
  import { createApp } from 'vue'
  import ElementPlus from 'element-plus'
  import 'element-plus/dist/index.css'
  import * as ElementPlusIconsVue from '@element-plus/icons-vue'
  import App from './App.vue'

  const app = createApp(App)
  app.use(ElementPlus)
  for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
  }
  app.mount('#app')
  ```
- [ ] Commit: "feat: Vue 3 + Element Plus + D3.js frontend scaffold"

---

### Task 15: API Client

- [ ] Implement `frontend/src/api/client.js`:
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
  }

  export const tasksApi = {
    get: (taskId) => api.get(`/tasks/${taskId}`),
    streamUrl: (taskId) => `/api/tasks/${taskId}/stream`,
  }

  export const chatStreamUrl = (projectId) => `/api/projects/${projectId}/chat`

  export default api
  ```
- [ ] Commit: "feat: API client with all endpoints"

---

### Task 16: FileUpload Component

- [ ] Implement `frontend/src/components/FileUpload.vue`:
  ```vue
  <template>
    <div class="file-upload">
      <el-upload
        drag multiple
        :auto-upload="false"
        :on-change="onFileChange"
        :file-list="fileList"
        accept=".pdf,.docx,.txt,.md"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          파일을 드래그하거나 <em>클릭하여 선택</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">PDF, DOCX, TXT, MD 지원</div>
        </template>
      </el-upload>

      <div v-if="fileList.length" class="file-list">
        <div v-for="f in fileList" :key="f.uid" class="file-item">
          <el-tag :type="getFileTagType(f.name)" size="small">
            {{ getFileExt(f.name).toUpperCase() }}
          </el-tag>
          <span class="file-name">{{ f.name }}</span>
          <el-tag size="small" type="info">{{ fileTypeLabel }}</el-tag>
        </div>
      </div>

      <el-select v-model="selectedFileType" placeholder="파일 유형 선택" class="mt-2">
        <el-option label="이력서 (CV)" value="cv" />
        <el-option label="프로젝트 문서" value="project" />
        <el-option label="논문/출판물" value="publication" />
        <el-option label="기타 노트" value="note" />
      </el-select>

      <el-button type="primary" :disabled="!fileList.length" @click="upload" class="mt-2">
        업로드 및 파싱 시작
      </el-button>
    </div>
  </template>

  <script setup>
  import { ref, computed } from 'vue'

  const props = defineProps({ projectId: String })
  const emit = defineEmits(['uploaded'])

  const fileList = ref([])
  const selectedFileType = ref('cv')
  const fileTypeLabel = computed(() => ({
    cv: '이력서', project: '프로젝트', publication: '논문', note: '노트'
  })[selectedFileType.value])

  function onFileChange(file, files) { fileList.value = files }
  function getFileExt(name) { return name.split('.').pop() || 'file' }
  function getFileTagType(name) {
    const ext = getFileExt(name)
    return { pdf: 'danger', docx: 'primary', txt: 'success', md: 'warning' }[ext] || 'info'
  }

  async function upload() {
    const { projectsApi } = await import('../api/client.js')
    const formData = new FormData()
    fileList.value.forEach(f => formData.append('files', f.raw))
    formData.append('file_type', selectedFileType.value)
    const r = await projectsApi.uploadFiles(props.projectId, formData)
    emit('uploaded', r.data.task_id)
    fileList.value = []
  }
  </script>
  ```
- [ ] Commit: "feat: FileUpload component with drag-and-drop + file type badges"

---

### Task 17: ProgressPanel Component

- [ ] Implement `frontend/src/components/ProgressPanel.vue`:
  ```vue
  <template>
    <div class="progress-panel">
      <el-progress :percentage="progress" :status="progressStatus" :stroke-width="18" />
      <div class="progress-stats">
        <el-tag>{{ statusLabel }}</el-tag>
        <span class="message">{{ message }}</span>
      </div>
      <div class="log-area" ref="logEl">
        <div v-for="(log, i) in logs" :key="i" class="log-line">
          <span class="log-time">{{ log.time }}</span>
          <span :class="['log-msg', log.type]">{{ log.msg }}</span>
        </div>
      </div>
      <div v-if="error" class="error-msg">
        <el-alert :title="error" type="error" show-icon />
      </div>
    </div>
  </template>

  <script setup>
  import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
  import { tasksApi } from '../api/client.js'

  const props = defineProps({ taskId: String })
  const emit = defineEmits(['completed', 'failed'])

  const progress = ref(0)
  const status = ref('pending')
  const message = ref('')
  const error = ref('')
  const logs = ref([])
  const logEl = ref(null)
  let eventSource = null

  const progressStatus = computed(() => {
    if (status.value === 'completed') return 'success'
    if (status.value === 'failed') return 'exception'
    return ''
  })

  const statusLabel = computed(() => ({
    pending: '대기 중', running: '실행 중', completed: '완료', failed: '실패'
  })[status.value] || status.value)

  watch(() => props.taskId, (id) => {
    if (id) startStream(id)
  }, { immediate: true })

  function startStream(taskId) {
    if (eventSource) eventSource.close()
    eventSource = new EventSource(tasksApi.streamUrl(taskId))
    eventSource.onmessage = async (e) => {
      const data = JSON.parse(e.data)
      progress.value = data.progress || 0
      status.value = data.status
      message.value = data.message || ''
      error.value = data.error || ''
      addLog(data.message, data.status === 'failed' ? 'error' : 'info')
      if (data.status === 'completed') {
        eventSource.close()
        emit('completed')
      } else if (data.status === 'failed') {
        eventSource.close()
        emit('failed', data.error)
      }
    }
  }

  function addLog(msg, type = 'info') {
    if (!msg) return
    logs.value.push({ time: new Date().toLocaleTimeString(), msg, type })
    nextTick(() => {
      if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
    })
  }

  onUnmounted(() => { if (eventSource) eventSource.close() })
  </script>

  <style scoped>
  .log-area { height: 150px; overflow-y: auto; background: #1e1e1e; color: #ccc;
    padding: 8px; border-radius: 4px; font-family: monospace; font-size: 12px; }
  .log-time { color: #888; margin-right: 8px; }
  .log-msg.error { color: #f56c6c; }
  .progress-stats { display: flex; align-items: center; gap: 12px; margin: 8px 0; }
  </style>
  ```
- [ ] Commit: "feat: ProgressPanel component with SSE task streaming"

---

### Task 18: OntologyView Component

- [ ] Implement `frontend/src/components/OntologyView.vue`:
  ```vue
  <template>
    <div class="ontology-view">
      <div class="section-title">엔티티 타입 ({{ ontology.entity_types?.length || 0 }}종)</div>
      <div class="entity-grid">
        <el-card v-for="et in ontology.entity_types" :key="et.name" class="entity-card" shadow="hover">
          <template #header>
            <el-tag :color="getTypeColor(et.name)" effect="dark">{{ et.name }}</el-tag>
          </template>
          <p class="desc">{{ et.description }}</p>
          <div class="examples" v-if="et.examples?.length">
            <el-tag v-for="ex in et.examples.slice(0,3)" :key="ex" size="small" type="info">
              {{ ex }}
            </el-tag>
          </div>
        </el-card>
      </div>

      <el-divider />

      <div class="section-title">관계 타입 ({{ ontology.edge_types?.length || 0 }}종)</div>
      <el-table :data="ontology.edge_types" stripe>
        <el-table-column prop="name" label="관계" width="180">
          <template #default="{ row }">
            <el-tag type="warning">{{ row.name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="설명" />
        <el-table-column label="소스 → 대상" width="200">
          <template #default="{ row }">
            {{ row.source_types?.join(', ') }} → {{ row.target_types?.join(', ') }}
          </template>
        </el-table-column>
      </el-table>

      <div class="analysis-summary" v-if="ontology.analysis_summary">
        <el-divider />
        <div class="section-title">분석 요약</div>
        <p>{{ ontology.analysis_summary }}</p>
      </div>
    </div>
  </template>

  <script setup>
  defineProps({ ontology: { type: Object, default: () => ({}) } })

  const TYPE_COLORS = {
    Person: '#4A90D9', Project: '#5BA85B', Skill: '#E8A838',
    Organization: '#9B59B6', Publication: '#E74C3C',
    Technology: '#1ABC9C', default: '#95A5A6'
  }
  function getTypeColor(name) { return TYPE_COLORS[name] || TYPE_COLORS.default }
  </script>

  <style scoped>
  .entity-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
  .entity-card { min-height: 100px; }
  .section-title { font-weight: bold; font-size: 15px; margin-bottom: 12px; }
  .desc { font-size: 13px; color: #666; margin: 4px 0; }
  .examples { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 8px; }
  </style>
  ```
- [ ] Commit: "feat: OntologyView component — entity cards + edge table"

---

### Task 19: StatsPanel + ProfileCard Components

- [ ] Implement `frontend/src/components/StatsPanel.vue`:
  ```vue
  <template>
    <div class="stats-panel">
      <div class="stat-row">
        <el-statistic title="전체 노드" :value="stats.total_nodes" />
        <el-statistic title="전체 엣지" :value="stats.total_edges" />
      </div>
      <el-divider />
      <div class="section-label">노드 타입별</div>
      <div v-for="(count, type) in stats.nodes_by_type" :key="type" class="type-row">
        <el-tag :color="getColor(type)" effect="dark" size="small">{{ type }}</el-tag>
        <el-progress :percentage="nodePercent(count)" :stroke-width="10"
          :color="getColor(type)" style="flex: 1; margin-left: 8px" />
        <span class="count">{{ count }}</span>
      </div>
      <el-divider />
      <div class="section-label">관계 타입별</div>
      <div v-for="(count, rel) in stats.edges_by_type" :key="rel" class="type-row">
        <span class="rel-name">{{ rel }}</span>
        <span class="count">{{ count }}</span>
      </div>
    </div>
  </template>

  <script setup>
  import { computed } from 'vue'
  const props = defineProps({ stats: { type: Object, default: () => ({
    total_nodes: 0, total_edges: 0, nodes_by_type: {}, edges_by_type: {}
  }) } })

  const TYPE_COLORS = {
    Person: '#4A90D9', Project: '#5BA85B', Skill: '#E8A838',
    Organization: '#9B59B6', Publication: '#E74C3C', Technology: '#1ABC9C'
  }
  function getColor(t) { return TYPE_COLORS[t] || '#95A5A6' }
  function nodePercent(count) {
    const max = Math.max(...Object.values(props.stats.nodes_by_type || {}), 1)
    return Math.round((count / max) * 100)
  }
  </script>

  <style scoped>
  .stat-row { display: flex; gap: 24px; justify-content: center; padding: 12px 0; }
  .type-row { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
  .count { font-weight: bold; min-width: 30px; text-align: right; }
  .section-label { font-size: 12px; color: #999; margin-bottom: 4px; }
  .rel-name { font-size: 12px; flex: 1; color: #666; }
  </style>
  ```
- [ ] Implement `frontend/src/components/ProfileCard.vue`:
  ```vue
  <template>
    <div class="profile-card">
      <div class="profile-header">
        <el-avatar :size="56" icon="User" />
        <div class="profile-name">{{ profile.name }}</div>
      </div>

      <div class="expertise-section">
        <div class="section-label">전문 분야</div>
        <el-tag v-for="e in profile.expertise" :key="e" type="primary" class="tag">{{ e }}</el-tag>
      </div>

      <div class="skills-section">
        <div class="section-label">기술 스택</div>
        <el-tag v-for="s in profile.skills" :key="s" type="success" size="small" class="tag">{{ s }}</el-tag>
      </div>

      <el-collapse>
        <el-collapse-item title="프로젝트" name="projects">
          <ul><li v-for="p in profile.projects" :key="p">{{ p }}</li></ul>
        </el-collapse-item>
        <el-collapse-item title="소속 기관" name="orgs">
          <ul><li v-for="o in profile.organizations" :key="o">{{ o }}</li></ul>
        </el-collapse-item>
        <el-collapse-item title="성과" name="achievements">
          <ul><li v-for="a in profile.achievements" :key="a">{{ a }}</li></ul>
        </el-collapse-item>
        <el-collapse-item title="커리어 요약" name="summary">
          <p class="summary-text">{{ profile.persona_summary }}</p>
        </el-collapse-item>
        <el-collapse-item title="타임라인" name="timeline">
          <el-timeline>
            <el-timeline-item
              v-for="t in profile.timeline" :key="t.year"
              :timestamp="String(t.year)"
            >{{ t.event }}</el-timeline-item>
          </el-timeline>
        </el-collapse-item>
      </el-collapse>
    </div>
  </template>

  <script setup>
  defineProps({ profile: { type: Object, required: true } })
  </script>

  <style scoped>
  .profile-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
  .profile-name { font-size: 20px; font-weight: bold; }
  .section-label { font-size: 12px; color: #999; margin-bottom: 4px; }
  .tag { margin: 2px; }
  .summary-text { line-height: 1.7; color: #444; }
  </style>
  ```
- [ ] Commit: "feat: StatsPanel + ProfileCard components"

---

### Task 20: GraphView Component (D3.js)

- [ ] Implement `frontend/src/components/GraphView.vue`:
  ```vue
  <template>
    <div class="graph-view">
      <div class="graph-toolbar">
        <el-checkbox-group v-model="visibleTypes" @change="redraw">
          <el-checkbox v-for="t in allTypes" :key="t" :label="t">
            <el-tag :color="NODE_COLORS[t] || NODE_COLORS.default" effect="dark" size="small">{{ t }}</el-tag>
          </el-checkbox>
        </el-checkbox-group>
        <el-button size="small" @click="resetZoom">Reset</el-button>
      </div>
      <svg ref="svgEl" class="graph-svg" />
      <el-drawer v-model="drawerVisible" direction="rtl" size="360px" :title="selectedNode?.name">
        <div v-if="selectedNode">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="타입">
              <el-tag>{{ selectedNode.type }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="설명">{{ selectedNode.description }}</el-descriptions-item>
            <el-descriptions-item label="소스">
              {{ selectedNode.source_files?.join(', ') }}
            </el-descriptions-item>
          </el-descriptions>
          <div class="connected-section">
            <div class="section-label">연결 노드</div>
            <el-tag v-for="n in connectedNodes" :key="n.id" class="conn-tag">{{ n.name }}</el-tag>
          </div>
        </div>
      </el-drawer>
    </div>
  </template>

  <script setup>
  import { ref, onMounted, watch, computed } from 'vue'
  import * as d3 from 'd3'

  const props = defineProps({ graphData: { type: Object, default: null } })

  const svgEl = ref(null)
  const drawerVisible = ref(false)
  const selectedNode = ref(null)
  const connectedNodes = ref([])
  const visibleTypes = ref([])
  let simulation = null

  const NODE_COLORS = {
    Person: '#4A90D9', Project: '#5BA85B', Skill: '#E8A838',
    Organization: '#9B59B6', Publication: '#E74C3C',
    Technology: '#1ABC9C', default: '#95A5A6'
  }

  const allTypes = computed(() => {
    if (!props.graphData?.nodes) return []
    return [...new Set(props.graphData.nodes.map(n => n.type || 'Unknown'))]
  })

  watch(() => props.graphData, (data) => {
    if (data) {
      visibleTypes.value = allTypes.value
      draw(data)
    }
  }, { immediate: true })

  function draw(data) {
    if (!svgEl.value || !data) return
    const svg = d3.select(svgEl.value)
    svg.selectAll('*').remove()

    const width = svgEl.value.clientWidth || 800
    const height = svgEl.value.clientHeight || 600

    const filteredNodes = data.nodes.filter(n => visibleTypes.value.includes(n.type || 'Unknown'))
    const filteredIds = new Set(filteredNodes.map(n => n.id))
    const filteredLinks = (data.links || []).filter(
      l => filteredIds.has(l.source.id || l.source) && filteredIds.has(l.target.id || l.target)
    )

    const g = svg.append('g')
    const zoom = d3.zoom().scaleExtent([0.1, 4])
      .on('zoom', (e) => g.attr('transform', e.transform))
    svg.call(zoom)
    svgEl.value.__zoom = zoom
    svgEl.value.__svg = svg

    simulation = d3.forceSimulation(filteredNodes)
      .force('link', d3.forceLink(filteredLinks).id(d => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(20))

    const link = g.append('g').selectAll('line').data(filteredLinks).enter().append('line')
      .attr('stroke', '#ccc').attr('stroke-width', 1.5)
    const linkLabel = g.append('g').selectAll('text').data(filteredLinks).enter().append('text')
      .attr('font-size', 9).attr('fill', '#999').text(d => d.relation || '')

    const node = g.append('g').selectAll('g').data(filteredNodes).enter().append('g')
      .call(d3.drag()
        .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
        .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y })
        .on('end', (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null })
      )
      .on('click', (e, d) => { onNodeClick(d, data) })

    node.append('circle').attr('r', d => d.type === 'Person' ? 14 : 10)
      .attr('fill', d => NODE_COLORS[d.type] || NODE_COLORS.default)
      .attr('stroke', '#fff').attr('stroke-width', 2)
      .style('cursor', 'pointer')
    node.append('text').attr('dy', '0.35em').attr('text-anchor', 'middle')
      .attr('font-size', 9).attr('fill', '#fff')
      .text(d => (d.name || d.id || '').slice(0, 8))

    simulation.on('tick', () => {
      link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
      linkLabel.attr('x', d => (d.source.x + d.target.x) / 2)
        .attr('y', d => (d.source.y + d.target.y) / 2)
      node.attr('transform', d => `translate(${d.x},${d.y})`)
    })
  }

  function onNodeClick(d, data) {
    selectedNode.value = d
    const links = data.links || []
    const neighbors = links
      .filter(l => (l.source.id || l.source) === d.id || (l.target.id || l.target) === d.id)
      .map(l => {
        const otherId = (l.source.id || l.source) === d.id ? (l.target.id || l.target) : (l.source.id || l.source)
        const other = data.nodes.find(n => n.id === otherId)
        return other ? { id: otherId, name: other.name } : null
      }).filter(Boolean)
    connectedNodes.value = neighbors
    drawerVisible.value = true
  }

  function redraw() {
    if (props.graphData) draw(props.graphData)
  }

  function resetZoom() {
    if (svgEl.value?.__svg && svgEl.value?.__zoom) {
      d3.select(svgEl.value).call(svgEl.value.__zoom.transform, d3.zoomIdentity)
    }
  }
  </script>

  <style scoped>
  .graph-view { position: relative; height: 100%; display: flex; flex-direction: column; }
  .graph-svg { flex: 1; width: 100%; background: #fafafa; border-radius: 8px; }
  .graph-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px; }
  .connected-section { margin-top: 16px; }
  .section-label { font-size: 12px; color: #999; margin-bottom: 4px; }
  .conn-tag { margin: 2px; }
  </style>
  ```
- [ ] Commit: "feat: GraphView D3.js force-directed graph with node type filter + drawer"

---

### Task 21: ChatPanel Component

- [ ] Implement `frontend/src/components/ChatPanel.vue`:
  ```vue
  <template>
    <div class="chat-panel">
      <div class="chat-header">
        <el-icon><ChatDotRound /></el-icon>
        <span>그래프 채팅 (InsightForge)</span>
      </div>

      <div class="messages" ref="messagesEl">
        <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.role]">
          <div class="msg-bubble">
            <pre class="msg-text">{{ msg.content }}</pre>
          </div>
        </div>
        <div v-if="streaming" class="msg assistant">
          <div class="msg-bubble">
            <pre class="msg-text">{{ streamBuffer }}<span class="cursor">▌</span></pre>
          </div>
        </div>
      </div>

      <div class="chat-input">
        <el-input
          v-model="input" type="textarea" :rows="2"
          placeholder="그래프에 대해 질문하세요... (예: 내 ML 프로젝트는 몇 개인가요?)"
          @keydown.ctrl.enter="send"
          :disabled="streaming"
        />
        <el-button type="primary" :loading="streaming" @click="send" :disabled="!input.trim()">
          전송 (Ctrl+Enter)
        </el-button>
      </div>
    </div>
  </template>

  <script setup>
  import { ref, nextTick } from 'vue'
  import { chatStreamUrl } from '../api/client.js'

  const props = defineProps({ projectId: String })

  const messages = ref([])
  const input = ref('')
  const streaming = ref(false)
  const streamBuffer = ref('')
  const messagesEl = ref(null)

  async function send() {
    const question = input.value.trim()
    if (!question || streaming.value) return
    messages.value.push({ role: 'user', content: question })
    input.value = ''
    streaming.value = true
    streamBuffer.value = ''
    await scrollBottom()

    try {
      const resp = await fetch(chatStreamUrl(props.projectId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          try {
            const data = JSON.parse(line.slice(5).trim())
            if (data.token) {
              streamBuffer.value += data.token
              await scrollBottom()
            } else if (data.done) {
              messages.value.push({ role: 'assistant', content: streamBuffer.value })
              streamBuffer.value = ''
            }
          } catch {}
        }
      }
    } catch (e) {
      messages.value.push({ role: 'assistant', content: `오류: ${e.message}` })
    } finally {
      streaming.value = false
      if (streamBuffer.value) {
        messages.value.push({ role: 'assistant', content: streamBuffer.value })
        streamBuffer.value = ''
      }
      await scrollBottom()
    }
  }

  async function scrollBottom() {
    await nextTick()
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
  </script>

  <style scoped>
  .chat-panel { display: flex; flex-direction: column; height: 100%; }
  .chat-header { display: flex; align-items: center; gap: 8px; font-weight: bold;
    padding: 12px; border-bottom: 1px solid #eee; }
  .messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; }
  .msg { display: flex; }
  .msg.user { justify-content: flex-end; }
  .msg.assistant { justify-content: flex-start; }
  .msg-bubble { max-width: 80%; border-radius: 12px; padding: 10px 14px; }
  .msg.user .msg-bubble { background: #409eff; color: white; }
  .msg.assistant .msg-bubble { background: #f5f7fa; }
  .msg-text { white-space: pre-wrap; word-break: break-word; font-family: inherit; margin: 0; }
  .cursor { animation: blink 1s infinite; }
  @keyframes blink { 50% { opacity: 0; } }
  .chat-input { padding: 12px; border-top: 1px solid #eee; display: flex; flex-direction: column; gap: 8px; }
  </style>
  ```
- [ ] Commit: "feat: ChatPanel with SSE streaming (POST + ReadableStream)"

---

### Task 22: VaultTree Component

- [ ] Implement `frontend/src/components/VaultTree.vue`:
  ```vue
  <template>
    <div class="vault-tree">
      <div class="vault-actions">
        <el-button size="small" type="primary" @click="downloadZip">
          <el-icon><Download /></el-icon> ZIP 다운로드
        </el-button>
        <el-button size="small" @click="emit('add-files')">
          <el-icon><Plus /></el-icon> 파일 추가 (증분)
        </el-button>
      </div>

      <el-tree :data="treeData" :props="treeProps" @node-click="onNodeClick"
        highlight-current node-key="name" />

      <el-drawer v-model="previewVisible" direction="rtl" size="50%" :title="previewTitle">
        <pre class="preview-content">{{ previewContent }}</pre>
      </el-drawer>
    </div>
  </template>

  <script setup>
  import { ref, computed } from 'vue'
  import { projectsApi } from '../api/client.js'

  const props = defineProps({ projectId: String, vaultTree: { type: Array, default: () => [] } })
  const emit = defineEmits(['add-files'])

  const previewVisible = ref(false)
  const previewTitle = ref('')
  const previewContent = ref('')

  const treeProps = { label: 'name', children: 'children' }

  const treeData = computed(() => props.vaultTree)

  async function onNodeClick(node) {
    if (node.type === 'file' && node.name.endsWith('.md')) {
      previewTitle.value = node.name
      try {
        const r = await fetch(`/api/projects/${props.projectId}/vault/file?path=${encodeURIComponent(node.path)}`)
        previewContent.value = await r.text()
      } catch {
        previewContent.value = '(미리보기 불가)'
      }
      previewVisible.value = true
    }
  }

  function downloadZip() {
    window.open(projectsApi.downloadVault(props.projectId))
  }
  </script>

  <style scoped>
  .vault-tree { padding: 8px; }
  .vault-actions { display: flex; gap: 8px; margin-bottom: 12px; }
  .preview-content { white-space: pre-wrap; font-family: monospace; font-size: 13px; line-height: 1.6; }
  </style>
  ```
- [ ] Commit: "feat: VaultTree with file browser + markdown preview + ZIP download"

---

### Task 23: ProjectDetail View (Main Integration)

- [ ] Implement `frontend/src/views/ProjectDetail.vue`:
  ```vue
  <template>
    <div class="project-detail">
      <el-container>
        <!-- LEFT SIDEBAR -->
        <el-aside width="260px" class="sidebar">
          <div class="project-title">{{ project?.name }}</div>
          <el-divider />

          <div class="sidebar-section">
            <div class="sidebar-label">그래프 통계</div>
            <StatsPanel :stats="stats" />
          </div>

          <el-divider />
          <div class="sidebar-section" v-if="profiles.length">
            <div class="sidebar-label">커리어 프로필</div>
            <el-select v-model="selectedProfile" placeholder="프로필 선택">
              <el-option v-for="p in profiles" :key="p.name" :label="p.name" :value="p.name" />
            </el-select>
            <ProfileCard v-if="currentProfile" :profile="currentProfile" class="mt-2" />
          </div>

          <el-divider />
          <div class="sidebar-section">
            <div class="sidebar-label">Vault 파일</div>
            <VaultTree :project-id="projectId" :vault-tree="vaultTree" @add-files="goToUpload" />
          </div>
        </el-aside>

        <!-- MAIN PANEL -->
        <el-main class="main-panel">
          <el-steps :active="activeStep" align-center class="steps">
            <el-step title="파일 업로드" />
            <el-step title="온톨로지" />
            <el-step title="그래프 구축" />
            <el-step title="결과" />
            <el-step title="Vault" />
          </el-steps>

          <!-- Step 0: File Upload -->
          <div v-if="activeStep === 0" class="step-content">
            <h3>파일 업로드</h3>
            <FileUpload :project-id="projectId" @uploaded="onFilesUploaded" />
            <ProgressPanel v-if="currentTaskId" :task-id="currentTaskId"
              @completed="onParseCompleted" @failed="onTaskFailed" />
          </div>

          <!-- Step 1: Ontology -->
          <div v-else-if="activeStep === 1" class="step-content">
            <h3>온톨로지 검토</h3>
            <div v-if="!ontology">
              <el-button type="primary" :loading="running" @click="runOntology">
                온톨로지 생성
              </el-button>
              <ProgressPanel v-if="currentTaskId" :task-id="currentTaskId"
                @completed="onOntologyCompleted" @failed="onTaskFailed" />
            </div>
            <div v-else>
              <OntologyView :ontology="ontology" />
              <el-button type="primary" @click="activeStep = 2" class="mt-3">
                그래프 구축 →
              </el-button>
            </div>
          </div>

          <!-- Step 2: Graph Build -->
          <div v-else-if="activeStep === 2" class="step-content">
            <h3>그래프 구축</h3>
            <el-button type="primary" :loading="running" @click="runGraph">
              그래프 생성 시작
            </el-button>
            <ProgressPanel v-if="currentTaskId" :task-id="currentTaskId"
              @completed="onGraphCompleted" @failed="onTaskFailed" />
          </div>

          <!-- Step 3: Results -->
          <div v-else-if="activeStep === 3" class="step-content results-step">
            <el-tabs v-model="resultTab">
              <el-tab-pane label="그래프 시각화" name="graph">
                <GraphView :graph-data="graphData" style="height: 500px" />
              </el-tab-pane>
              <el-tab-pane label="채팅" name="chat">
                <ChatPanel :project-id="projectId" style="height: 500px" />
              </el-tab-pane>
            </el-tabs>
            <el-button @click="activeStep = 4" class="mt-3">Vault 내보내기 →</el-button>
          </div>

          <!-- Step 4: Vault -->
          <div v-else-if="activeStep === 4" class="step-content">
            <h3>Vault 내보내기</h3>
            <VaultTree :project-id="projectId" :vault-tree="vaultTree" @add-files="goToUpload" />
          </div>
        </el-main>
      </el-container>
    </div>
  </template>

  <script setup>
  import { ref, computed, onMounted } from 'vue'
  import { useRoute } from 'vue-router'
  import FileUpload from '../components/FileUpload.vue'
  import ProgressPanel from '../components/ProgressPanel.vue'
  import OntologyView from '../components/OntologyView.vue'
  import StatsPanel from '../components/StatsPanel.vue'
  import ProfileCard from '../components/ProfileCard.vue'
  import GraphView from '../components/GraphView.vue'
  import ChatPanel from '../components/ChatPanel.vue'
  import VaultTree from '../components/VaultTree.vue'
  import { projectsApi } from '../api/client.js'

  const route = useRoute()
  const projectId = computed(() => route.params.id)

  const project = ref(null)
  const activeStep = ref(0)
  const currentTaskId = ref(null)
  const running = ref(false)
  const ontology = ref(null)
  const graphData = ref(null)
  const stats = ref({ total_nodes: 0, total_edges: 0, nodes_by_type: {}, edges_by_type: {} })
  const profiles = ref([])
  const selectedProfile = ref(null)
  const vaultTree = ref([])
  const resultTab = ref('graph')

  const currentProfile = computed(() =>
    profiles.value.find(p => p.name === selectedProfile.value)
  )

  onMounted(async () => {
    const r = await projectsApi.get(projectId.value)
    project.value = r.data
    await loadGraphData()
  })

  async function loadGraphData() {
    try {
      const [statsR, profilesR, vaultR] = await Promise.allSettled([
        projectsApi.getGraphStats(projectId.value),
        projectsApi.getProfiles(projectId.value),
        projectsApi.getVaultTree(projectId.value),
      ])
      if (statsR.status === 'fulfilled') stats.value = statsR.value.data
      if (profilesR.status === 'fulfilled') {
        profiles.value = profilesR.value.data
        if (profiles.value.length) selectedProfile.value = profiles.value[0].name
      }
      if (vaultR.status === 'fulfilled') vaultTree.value = vaultR.value.data
    } catch {}
  }

  function onFilesUploaded(taskId) { currentTaskId.value = taskId }
  function onParseCompleted() { currentTaskId.value = null; activeStep.value = 1 }

  async function runOntology() {
    running.value = true
    const r = await projectsApi.runOntology(projectId.value)
    currentTaskId.value = r.data.task_id
    running.value = false
  }

  async function onOntologyCompleted() {
    currentTaskId.value = null
    const r = await projectsApi.getOntology(projectId.value)
    ontology.value = r.data
  }

  async function runGraph() {
    running.value = true
    const r = await projectsApi.runGraph(projectId.value)
    currentTaskId.value = r.data.task_id
    running.value = false
  }

  async function onGraphCompleted() {
    currentTaskId.value = null
    const [graphR] = await Promise.allSettled([projectsApi.getGraph(projectId.value)])
    if (graphR.status === 'fulfilled') graphData.value = graphR.value.data
    await loadGraphData()
    activeStep.value = 3
  }

  function onTaskFailed(err) { currentTaskId.value = null; running.value = false }
  function goToUpload() { activeStep.value = 0 }
  </script>

  <style scoped>
  .project-detail { height: 100vh; }
  .sidebar { border-right: 1px solid #eee; padding: 16px; overflow-y: auto; background: #fafafa; }
  .main-panel { padding: 24px; }
  .project-title { font-size: 18px; font-weight: bold; }
  .sidebar-label { font-size: 12px; color: #999; margin-bottom: 8px; }
  .sidebar-section { margin-bottom: 16px; }
  .steps { margin-bottom: 32px; }
  .step-content { max-width: 900px; }
  .results-step { height: calc(100vh - 200px); }
  .mt-2 { margin-top: 8px; }
  .mt-3 { margin-top: 16px; }
  </style>
  ```
- [ ] Add Vue Router in `frontend/src/main.js`:
  ```js
  import { createRouter, createWebHistory } from 'vue-router'
  import HomeView from './views/HomeView.vue'
  import ProjectDetail from './views/ProjectDetail.vue'

  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', component: HomeView },
      { path: '/projects/:id', component: ProjectDetail },
    ]
  })
  app.use(router)
  ```
- [ ] Implement `frontend/src/views/HomeView.vue` (project list + create dialog)
- [ ] Update `frontend/src/App.vue` to use router-view
- [ ] Commit: "feat: ProjectDetail view integrating all components into 5-step workflow"

---

### Task 24: docs + run.py

- [ ] Create `backend/run.py`:
  ```python
  import uvicorn
  if __name__ == "__main__":
      uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
  ```
- [ ] Create `docs/agents.md` (에이전트 상세 문서)
- [ ] Create `docs/api.md` (API 엔드포인트 문서)
- [ ] Create `.env.example`:
  ```env
  LLM_API_KEY=sk-...
  LLM_BASE_URL=https://api.openai.com/v1
  LLM_MODEL=gpt-4o
  CHUNK_SIZE=500
  CHUNK_OVERLAP=50
  FUZZY_MATCH_THRESHOLD=0.85
  MAX_ONTOLOGY_SAMPLE_CHARS=50000
  VAULT_DIR=./vault
  PROJECTS_DIR=./projects
  ```
- [ ] Commit: "docs: add agents.md, api.md, .env.example"

---

## Summary

| Phase | Tasks | Key Deliverables |
|---|---|---|
| Foundation | 1-4 | Scaffold, models, utils, FastAPI app |
| Agents | 5-10 | 6 agents: Parser, Ontology, GraphBuilder, Profile, ObsidianWriter, Query |
| Backend API | 11-13 | Projects, Graph/Ontology, Chat + SSE streaming |
| Frontend | 14-24 | Vue3 + 9 components + ProjectDetail 5-step workflow |

**Total tasks: 24 | TDD coverage: all backend agents + API layers**
