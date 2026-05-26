# Restructure + About Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `backend/` and `frontend/` into `src/`, add CLAUDE.md files per subdirectory, and build a `/about` workflow diagram page.

**Architecture:** Three independent concerns executed in sequence: (1) folder migration via `git mv` with path fixups, (2) CLAUDE.md files written per subdirectory, (3) Vue `AboutView.vue` with CSS-only diagrams added to the frontend.

**Tech Stack:** Python/FastAPI, Vue 3/Element Plus, CSS Flexbox/Grid, Syncthing REST API

**Reference spec:** `docs/superpowers/specs/2026-05-26-restructure-and-about-page-design.md`

---

## File Map

### Created
- `src/` — new top-level directory (via git mv)
- `src/backend/` — moved from `backend/`
- `src/frontend/` — moved from `frontend/`
- `src/backend/CLAUDE.md`
- `src/backend/app/agents/CLAUDE.md`
- `src/backend/app/api/CLAUDE.md`
- `src/frontend/CLAUDE.md`
- `src/frontend/src/views/AboutView.vue`

### Modified
- `CLAUDE.md` — Quick Start paths + links updated
- `.gitignore` — vault/projects path patterns updated
- `src/frontend/src/router/index.js` — add `/about` route
- `src/frontend/src/views/HomeView.vue` — add header "워크플로우" link

---

## Task 1: Folder Migration

**Files:**
- Move: `backend/` → `src/backend/`
- Move: `frontend/` → `src/frontend/`
- Move: `vault/` → `src/backend/vault/`
- Modify: `.gitignore`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Create `src/` and move directories**

```bash
mkdir src
git mv backend src/backend
git mv frontend src/frontend
```

- [ ] **Step 2: Move vault to src/backend/vault/**

The vault root directory (used by Syncthing) is currently at project root. Move it under src/backend/ to match where the app writes to.

```bash
git mv vault src/backend/vault
```

- [ ] **Step 3: Update .gitignore path patterns**

Open `.gitignore` and replace:
```
projects/**/*.json
vault/**/*.json
```
with:
```
src/backend/projects/**/*.json
src/backend/vault/**/*.json
```

- [ ] **Step 4: Update root CLAUDE.md Quick Start**

Replace the Quick Start block:
```markdown
## Quick Start

```bash
# Backend
cd src/backend && pip install -e ".[dev]" && uvicorn app.main:app --reload

# Frontend
cd src/frontend && npm install && npm run dev
```
```

- [ ] **Step 5: Reinstall backend package from new path**

```bash
cd src/backend && pip install -e ".[dev]"
```

Expected: `Successfully installed projectos-backend-0.1.0`

- [ ] **Step 6: Run backend tests from new path**

```bash
cd src/backend && python3 -m pytest tests/ -v 2>&1 | tail -5
```

Expected: `59 passed`

- [ ] **Step 7: Verify frontend builds from new path**

```bash
cd src/frontend && npm run build 2>&1 | tail -3
```

Expected: `✓ built in N.NNs`

- [ ] **Step 8: Update Syncthing vault path via REST API**

The Syncthing folder config still points to the old vault path. Update it:

```bash
API_KEY="JkqaCLpdj5Yrp4aGUHaXPahXvG3Rqjek"
PROJECT_ROOT="/raid/home/a202121010/workspace/projects/ProjectOS"
NEW_VAULT="${PROJECT_ROOT}/src/backend/vault"

# Get current folder config
FOLDER=$(curl -s "http://127.0.0.1:8384/rest/config/folders/projectos-vault" \
  -H "X-API-Key: $API_KEY")

# Update path
UPDATED=$(echo "$FOLDER" | python3 -c "
import sys, json
d = json.load(sys.stdin)
d['path'] = '${NEW_VAULT}'
print(json.dumps(d))
")

curl -s -o /dev/null -w "%{http_code}" -X PUT \
  "http://127.0.0.1:8384/rest/config/folders/projectos-vault" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "$UPDATED"
```

Expected output: `200`

- [ ] **Step 9: Verify Syncthing still shows vault folder**

```bash
curl -s "http://127.0.0.1:8384/rest/config/folders/projectos-vault" \
  -H "X-API-Key: JkqaCLpdj5Yrp4aGUHaXPahXvG3Rqjek" | python3 -c "
import sys, json; d = json.load(sys.stdin); print('path:', d['path'])
"
```

Expected: `path: /raid/home/a202121010/workspace/projects/ProjectOS/src/backend/vault`

- [ ] **Step 10: Commit**

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS
git add -A
git commit -m "refactor: move backend + frontend into src/ directory"
```

---

## Task 2: CLAUDE.md Sementation

**Files:**
- Modify: `CLAUDE.md`
- Create: `src/backend/CLAUDE.md`
- Create: `src/backend/app/agents/CLAUDE.md`
- Create: `src/backend/app/api/CLAUDE.md`
- Create: `src/frontend/CLAUDE.md`

- [ ] **Step 1: Update root CLAUDE.md**

Replace entire content of `CLAUDE.md`:

```markdown
# ProjectOS

로컬 파일(이력서, 프로젝트 문서, 논문) → LLM 분석 → NetworkX 그래프 → Obsidian vault

## Quick Start

```bash
# Backend
cd src/backend && pip install -e ".[dev]" && uvicorn app.main:app --reload

# Frontend
cd src/frontend && npm install && npm run dev
```

## Docs

- Architecture: docs/superpowers/specs/2026-05-24-projectos-design.md
- Agents: docs/agents.md
- API: docs/api.md

## Subdirectory CLAUDE.md

- [Backend](src/backend/CLAUDE.md) — 설치, 테스트, 패키지 구조
- [Agents](src/backend/app/agents/CLAUDE.md) — 에이전트 추가 방법, LLM 패턴
- [API](src/backend/app/api/CLAUDE.md) — 라우터 패턴, SSE, 순환 임포트 방지
- [Frontend](src/frontend/CLAUDE.md) — 빌드, 컴포넌트 패턴, API 클라이언트

## Key Rules

- MiroFish (../MiroFish/) is READ-ONLY reference
- Local graph only — no Zep Cloud
- TDD: write tests first
- Languages: Korean + English
```

- [ ] **Step 2: Create `src/backend/CLAUDE.md`**

```markdown
# Backend — ProjectOS

FastAPI 백엔드. 6개 에이전트 파이프라인 + 4개 API 라우터.

## 명령어

```bash
# 설치
pip install -e ".[dev]"

# 실행 (src/backend/ 에서)
python3 run.py
# 또는
uvicorn app.main:app --reload

# 테스트
python3 -m pytest tests/ -v

# 특정 테스트
python3 -m pytest tests/test_agents/test_parser_agent.py -v
```

## 패키지 구조

```
app/
  agents/     — 6개 에이전트 (parser, ontology, graph_builder, profile, obsidian_writer, query)
  api/        — 4개 라우터 (projects, graph, chat, tasks)
  models/     — 데이터 모델 (graph.py, project.py)
  services/   — TaskManager, ProjectStore (인메모리/파일시스템)
  utils/      — LLMClient (OpenAI SDK), FileParser (PDF/DOCX/TXT)
  config.py   — pydantic_settings BaseSettings 싱글톤
  main.py     — FastAPI 앱, CORS, 라우터 등록
```

## 에이전트 파이프라인 순서

ParserAgent → OntologyAgent → GraphBuilderAgent → ProfileAgent → ObsidianWriterAgent

QueryAgent는 독립 실행 (채팅 엔드포인트에서 호출).

## 환경 변수

`src/backend/` 에 `.env` 파일 생성 (`.env.example` 참고):
- `LLM_API_KEY` — OpenAI 호환 API 키 (필수)
- `LLM_BASE_URL` — 기본값 `https://api.openai.com/v1`
- `LLM_MODEL` — 기본값 `gpt-4o`
- `VAULT_DIR` — 기본값 `./vault` (Syncthing 절대경로 사용 권장)
- `PROJECTS_DIR` — 기본값 `./projects`
```

- [ ] **Step 3: Create `src/backend/app/agents/CLAUDE.md`**

```markdown
# Agents — ProjectOS

6개 독립 에이전트. 공통 기반 클래스 없음. 각각 `run()` 또는 `stream()` 메서드.

## 에이전트 목록

| 파일 | 클래스 | 주요 메서드 |
|------|--------|-------------|
| parser_agent.py | ParserAgent | `run(file_paths, file_type) → list[TextChunk]` |
| ontology_agent.py | OntologyAgent | `run(chunks) → Ontology` |
| graph_builder_agent.py | GraphBuilderAgent | `run(chunks, ontology, incremental, graph_path) → nx.DiGraph` |
| profile_agent.py | ProfileAgent | `run(graph) → list[CareerProfile]` |
| obsidian_writer_agent.py | ObsidianWriterAgent | `run(graph, profiles, vault_path, delta)` |
| query_agent.py | QueryAgent | `stream(question, graph, chunks)` async generator |

## LLM 호출 패턴

```python
from app.utils.llm_client import llm_client

# JSON 응답
result: dict = await llm_client.chat_json(prompt)

# 스트리밍
async for token in llm_client.stream(prompt):
    yield token
```

## 고정 타입 목록

엔티티 10개: Person, Project, Skill, Organization, Publication, Technology, Role, Achievement, Event, Institution

관계 10개: WORKED_AT, DEVELOPED, USES_SKILL, AUTHORED, COLLABORATED_WITH, ACHIEVED, PARTICIPATED_IN, PUBLISHED_AT, MENTORED_BY, LED_BY

## Fuzzy Matching

`difflib.SequenceMatcher` — threshold `config.FUZZY_MATCH_THRESHOLD` (기본 0.85).
타입 범위 내 매칭만 수행 (Person ↔ Person 등).

## 한국어 주의사항

`QueryAgent._find_relevant_chunks()` 는 단어 집합 교차가 아닌 substring 매칭 사용.
이유: 한국어 조사 ("Python을", "Python이") 때문에 단어 분리 시 매칭 실패.
```

- [ ] **Step 4: Create `src/backend/app/api/CLAUDE.md`**

```markdown
# API — ProjectOS

FastAPI 라우터 4개. `app/main.py` 에서 등록.

## 라우터 목록

| 파일 | prefix | 주요 엔드포인트 |
|------|--------|----------------|
| projects.py | /projects | CRUD, 파일 업로드, vault 트리 |
| graph.py | /projects/{id} | 온톨로지 생성, 그래프 구축, 통계 |
| chat.py | /projects/{id} | SSE 채팅 스트리밍 |
| tasks.py | /tasks | 태스크 상태, SSE 진행 스트림 |

## SSE 패턴 (tasks)

GET 방식. EventSource로 구독. 1초 폴링:

```python
async def task_stream(task_id: str):
    async def generate():
        while True:
            task = task_manager.get(task_id)
            yield f"data: {task.model_dump_json()}\n\n"
            if task.status in ("completed", "failed"):
                break
            await asyncio.sleep(1)
    return StreamingResponse(generate(), media_type="text/event-stream")
```

## SSE 패턴 (chat)

POST 방식. fetch + ReadableStream 으로 구독:

```python
async def chat_stream(project_id: str, body: ChatRequest):
    async def generate():
        async for token in query_agent.stream(...):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

## 에이전트 지연 임포트 (순환 임포트 방지)

에이전트를 모듈 상단에서 임포트하지 말 것. 함수 내부에서 임포트:

```python
async def run_graph(project_id: str, background_tasks: BackgroundTasks):
    async def _run():
        from app.agents.graph_builder_agent import GraphBuilderAgent  # 여기서 임포트
        agent = GraphBuilderAgent()
        ...
    background_tasks.add_task(_run)
```

## 배경 태스크 패턴

`BackgroundTasks` 또는 `asyncio.create_task` 사용. 태스크 ID를 즉시 반환하고 진행 상태는 SSE로 스트리밍.
```

- [ ] **Step 5: Create `src/frontend/CLAUDE.md`**

```markdown
# Frontend — ProjectOS

Vue 3 + Vite + Element Plus + D3.js.

## 명령어

```bash
# 개발 서버 (포트 5173)
npm run dev

# 프로덕션 빌드
npm run build

# 미리보기
npm run preview
```

## 디렉토리 구조

```
src/
  api/client.js      — axios 기반 API 클라이언트 (projectsApi, tasksApi, chatStreamUrl)
  components/        — 8개 재사용 컴포넌트
  views/             — 3개 페이지 뷰 (HomeView, ProjectDetail, AboutView)
  router/index.js    — Vue Router 설정
  App.vue            — 루트 컴포넌트 (router-view)
  main.js            — 앱 진입점
```

## 컴포넌트 작성 패턴

`<script setup>` Composition API 사용:

```vue
<script setup>
import { ref, computed, onMounted } from 'vue'
import { projectsApi } from '../api/client.js'

const data = ref(null)
onMounted(async () => {
  const r = await projectsApi.get(id)
  data.value = r.data
})
</script>
```

## API 클라이언트 사용법

```js
import { projectsApi, tasksApi, chatStreamUrl } from '../api/client.js'

// REST
const r = await projectsApi.list()        // GET /projects
const r = await projectsApi.create({...}) // POST /projects
const r = await projectsApi.runGraph(id)  // POST /projects/{id}/graph

// SSE — 태스크 진행 (EventSource)
const url = tasksApi.streamUrl(taskId)   // GET /tasks/{id}/stream

// SSE — 채팅 (fetch + ReadableStream)
const url = chatStreamUrl(projectId)     // POST /projects/{id}/chat
```

## SSE 수신 패턴

태스크 진행 (EventSource):
```js
const es = new EventSource(tasksApi.streamUrl(taskId))
es.onmessage = (e) => { const task = JSON.parse(e.data) }
```

채팅 스트리밍 (fetch):
```js
const res = await fetch(chatStreamUrl(projectId), { method: 'POST', body: JSON.stringify({question}) })
const reader = res.body.getReader()
// ReadableStream 읽기
```
```

- [ ] **Step 6: Commit**

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS
git add CLAUDE.md src/backend/CLAUDE.md src/backend/app/agents/CLAUDE.md \
        src/backend/app/api/CLAUDE.md src/frontend/CLAUDE.md
git commit -m "docs: add per-directory CLAUDE.md files"
```

---

## Task 3: AboutView — Routing + HomeView Link

**Files:**
- Create: `src/frontend/src/views/AboutView.vue` (skeleton)
- Modify: `src/frontend/src/router/index.js`
- Modify: `src/frontend/src/views/HomeView.vue`

- [ ] **Step 1: Create AboutView skeleton**

Create `src/frontend/src/views/AboutView.vue`:

```vue
<template>
  <div class="about">
    <el-container>
      <el-header class="about-header" height="60px">
        <el-button text @click="router.push('/')">
          <el-icon><ArrowLeft /></el-icon> 홈
        </el-button>
        <h1 class="header-title">ProjectOS 작동 원리</h1>
        <div style="width: 80px" />
      </el-header>

      <el-main class="about-main">
        <!-- 섹션들은 Task 4, 5에서 추가 -->
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
const router = useRouter()
</script>

<style scoped>
.about { min-height: 100vh; background: #f5f7fa; }
.about-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; background: #303133; color: white;
}
.header-title { font-size: 18px; font-weight: bold; color: white; }
.about-main { max-width: 1000px; margin: 0 auto; padding: 40px 24px; }
</style>
```

- [ ] **Step 2: Add `/about` route**

Edit `src/frontend/src/router/index.js`:

```js
import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import ProjectDetail from '../views/ProjectDetail.vue'
import AboutView from '../views/AboutView.vue'

const routes = [
  { path: '/', component: HomeView },
  { path: '/projects/:id', component: ProjectDetail },
  { path: '/about', component: AboutView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
```

- [ ] **Step 3: Add "워크플로우" link to HomeView header**

In `src/frontend/src/views/HomeView.vue`, find the header section and add a link button. The header currently looks like:

```vue
<el-header class="header" height="60px">
  <div class="header-left">
    <h1 class="app-title">ProjectOS</h1>
    <span class="app-subtitle">로컬 파일 → 커리어 지식 그래프</span>
  </div>
  <el-button type="primary" @click="createDialogVisible = true">
```

Change to:

```vue
<el-header class="header" height="60px">
  <div class="header-left">
    <h1 class="app-title">ProjectOS</h1>
    <span class="app-subtitle">로컬 파일 → 커리어 지식 그래프</span>
  </div>
  <div class="header-right">
    <el-button text style="color: white" @click="router.push('/about')">워크플로우</el-button>
    <el-button type="primary" @click="createDialogVisible = true">
```

Also close the new `<div class="header-right">` after the create button, and add CSS:

```css
.header-right { display: flex; align-items: center; gap: 8px; }
```

- [ ] **Step 4: Verify build**

```bash
cd src/frontend && npm run build 2>&1 | tail -3
```

Expected: `✓ built in N.NNs`

- [ ] **Step 5: Commit**

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS
git add src/frontend/src/views/AboutView.vue \
        src/frontend/src/router/index.js \
        src/frontend/src/views/HomeView.vue
git commit -m "feat: add /about route and HomeView header link"
```

---

## Task 4: AboutView — Architecture Diagram + Pipeline Flowchart

**Files:**
- Modify: `src/frontend/src/views/AboutView.vue`

- [ ] **Step 1: Add Section 1 — System Architecture Diagram**

Replace `<!-- 섹션들은 Task 4, 5에서 추가 -->` with:

```vue
<!-- 섹션 1: 시스템 아키텍처 -->
<section class="section">
  <h2 class="section-title">시스템 아키텍처</h2>
  <p class="section-desc">4개 레이어로 구성된 풀스택 AI 파이프라인</p>
  <div class="arch-diagram">
    <div class="arch-layer layer-frontend">
      <div class="layer-header">
        <span class="layer-badge">Frontend</span>
        <span class="layer-tech">Vue 3 + Element Plus + D3.js</span>
      </div>
      <div class="layer-chips">
        <span class="chip">HomeView</span>
        <span class="chip">ProjectDetail</span>
        <span class="chip">AboutView</span>
        <span class="chip">GraphView</span>
        <span class="chip">ChatPanel</span>
        <span class="chip">VaultTree</span>
      </div>
    </div>
    <div class="arch-connector"><span class="connector-label">REST API + SSE 스트리밍</span></div>
    <div class="arch-layer layer-backend">
      <div class="layer-header">
        <span class="layer-badge">Backend</span>
        <span class="layer-tech">FastAPI + Python 3.14</span>
      </div>
      <div class="layer-chips">
        <span class="chip">/projects</span>
        <span class="chip">/graph</span>
        <span class="chip">/chat</span>
        <span class="chip">/tasks</span>
      </div>
    </div>
    <div class="arch-connector"><span class="connector-label">에이전트 파이프라인 호출</span></div>
    <div class="arch-layer layer-agents">
      <div class="layer-header">
        <span class="layer-badge">Agent Pipeline</span>
        <span class="layer-tech">OpenAI SDK + NetworkX</span>
      </div>
      <div class="layer-chips">
        <span class="chip">ParserAgent</span>
        <span class="chip">OntologyAgent</span>
        <span class="chip">GraphBuilderAgent</span>
        <span class="chip">ProfileAgent</span>
        <span class="chip">ObsidianWriterAgent</span>
        <span class="chip">QueryAgent</span>
      </div>
    </div>
    <div class="arch-connector"><span class="connector-label">읽기 / 쓰기</span></div>
    <div class="arch-layer layer-storage">
      <div class="layer-header">
        <span class="layer-badge">Storage</span>
        <span class="layer-tech">로컬 파일시스템</span>
      </div>
      <div class="layer-chips">
        <span class="chip">NetworkX DiGraph (graph.json)</span>
        <span class="chip">Obsidian Vault (Markdown)</span>
        <span class="chip">Syncthing → Mac</span>
      </div>
    </div>
  </div>
</section>

<!-- 섹션 2: 에이전트 파이프라인 -->
<section class="section">
  <h2 class="section-title">에이전트 파이프라인</h2>
  <p class="section-desc">파일 업로드부터 Obsidian vault 생성까지의 데이터 흐름</p>
  <div class="pipeline-wrapper">
    <div class="pipeline-main">
      <div class="pipe-node node-input">
        <div class="node-name">파일 입력</div>
        <div class="node-io">PDF · DOCX · TXT</div>
      </div>
      <div class="pipe-arrow">→</div>
      <div class="pipe-node">
        <div class="node-name">ParserAgent</div>
        <div class="node-io">TextChunk[]</div>
      </div>
      <div class="pipe-arrow">→</div>
      <div class="pipe-node">
        <div class="node-name">OntologyAgent</div>
        <div class="node-io">Ontology</div>
      </div>
      <div class="pipe-arrow">→</div>
      <div class="pipe-node node-center" ref="graphNodeRef">
        <div class="node-name">GraphBuilderAgent</div>
        <div class="node-io">nx.DiGraph</div>
      </div>
      <div class="pipe-arrow">→</div>
      <div class="pipe-node">
        <div class="node-name">ProfileAgent</div>
        <div class="node-io">CareerProfile[]</div>
      </div>
      <div class="pipe-arrow">→</div>
      <div class="pipe-node node-output">
        <div class="node-name">ObsidianWriterAgent</div>
        <div class="node-io">vault/ Markdown</div>
      </div>
    </div>
    <div class="pipeline-branch">
      <div class="branch-line"></div>
      <div class="pipe-node node-query">
        <div class="node-name">QueryAgent</div>
        <div class="node-io">SSE 채팅 스트리밍</div>
      </div>
    </div>
  </div>
</section>

<!-- 섹션 3, 4는 Task 5에서 추가 -->
```

- [ ] **Step 2: Add CSS for sections 1 & 2**

Add to `<style scoped>`:

```css
.section { margin-bottom: 48px; }
.section-title { font-size: 22px; font-weight: bold; color: #303133; margin-bottom: 8px; }
.section-desc { color: #909399; font-size: 14px; margin-bottom: 24px; }

/* Architecture Diagram */
.arch-diagram { display: flex; flex-direction: column; gap: 0; max-width: 800px; }
.arch-layer {
  border-radius: 10px; padding: 16px 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.layer-frontend { background: #ecf5ff; border: 2px solid #409eff; }
.layer-backend  { background: #f0f9eb; border: 2px solid #67c23a; }
.layer-agents   { background: #fdf6ec; border: 2px solid #e6a23c; }
.layer-storage  { background: #f5f5f5; border: 2px solid #909399; }
.layer-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.layer-badge {
  font-size: 12px; font-weight: bold; padding: 2px 10px; border-radius: 12px;
  background: white; color: #303133; border: 1px solid currentColor;
}
.layer-frontend .layer-badge { color: #409eff; }
.layer-backend .layer-badge  { color: #67c23a; }
.layer-agents .layer-badge   { color: #e6a23c; }
.layer-storage .layer-badge  { color: #909399; }
.layer-tech { font-size: 12px; color: #606266; }
.layer-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  background: white; border: 1px solid #dcdfe6; border-radius: 4px;
  padding: 3px 10px; font-size: 12px; color: #606266;
}
.arch-connector {
  display: flex; align-items: center; justify-content: center;
  height: 36px; position: relative;
}
.arch-connector::before {
  content: ''; position: absolute; left: 50%; top: 0;
  width: 2px; height: 100%; background: #dcdfe6; transform: translateX(-50%);
}
.connector-label {
  background: #f5f7fa; padding: 2px 10px; font-size: 11px;
  color: #909399; border-radius: 10px; border: 1px solid #dcdfe6;
  position: relative; z-index: 1;
}

/* Pipeline Flowchart */
.pipeline-wrapper { display: flex; flex-direction: column; gap: 0; }
.pipeline-main {
  display: flex; align-items: center; gap: 4px; flex-wrap: wrap;
  background: white; border-radius: 10px; padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06); border: 1px solid #ebeef5;
}
.pipe-node {
  background: white; border: 2px solid #e6a23c; border-radius: 8px;
  padding: 10px 14px; text-align: center; min-width: 120px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.node-input  { border-color: #409eff; }
.node-output { border-color: #67c23a; }
.node-query  { border-color: #9b59b6; }
.node-name { font-size: 13px; font-weight: bold; color: #303133; margin-bottom: 4px; }
.node-io { font-size: 11px; color: #909399; }
.pipe-arrow { font-size: 18px; color: #c0c4cc; flex-shrink: 0; }
.pipeline-branch {
  display: flex; align-items: center; gap: 0;
  padding-left: 20px; margin-top: 0;
}
.branch-line {
  width: 2px; height: 32px; background: #dcdfe6;
  margin-left: 300px;
}
```

- [ ] **Step 3: Verify build**

```bash
cd src/frontend && npm run build 2>&1 | tail -3
```

Expected: `✓ built in N.NNs`

---

## Task 5: AboutView — User Guide + Technical Details

**Files:**
- Modify: `src/frontend/src/views/AboutView.vue`

- [ ] **Step 1: Add Section 3 — 5-step user guide**

Replace `<!-- 섹션 3, 4는 Task 5에서 추가 -->` with:

```vue
<!-- 섹션 3: 5단계 사용 가이드 -->
<section class="section">
  <h2 class="section-title">5단계 사용 가이드</h2>
  <p class="section-desc">ProjectOS를 처음 사용하는 방법</p>
  <div class="guide-grid">
    <div class="guide-card" v-for="step in steps" :key="step.num">
      <div class="step-badge">{{ step.num }}</div>
      <div class="step-content">
        <div class="step-title">{{ step.title }}</div>
        <div class="step-desc">{{ step.desc }}</div>
        <div class="step-detail">{{ step.detail }}</div>
      </div>
    </div>
  </div>
</section>

<!-- 섹션 4: 기술 상세 -->
<section class="section">
  <h2 class="section-title">기술 상세</h2>
  <el-collapse>
    <el-collapse-item title="에이전트 스펙" name="agents">
      <el-table :data="agentSpecs" border size="small">
        <el-table-column prop="name" label="에이전트" width="180" />
        <el-table-column prop="input" label="입력" />
        <el-table-column prop="output" label="출력" />
        <el-table-column prop="logic" label="핵심 로직" />
      </el-table>
    </el-collapse-item>
    <el-collapse-item title="데이터 모델" name="models">
      <el-table :data="modelSpecs" border size="small">
        <el-table-column prop="name" label="모델" width="160" />
        <el-table-column prop="fields" label="주요 필드" />
      </el-table>
    </el-collapse-item>
    <el-collapse-item title="API 엔드포인트" name="api">
      <el-table :data="apiSpecs" border size="small">
        <el-table-column prop="method" label="Method" width="80" />
        <el-table-column prop="path" label="Path" width="280" />
        <el-table-column prop="desc" label="설명" />
      </el-table>
    </el-collapse-item>
  </el-collapse>
</section>
```

- [ ] **Step 2: Add data arrays in `<script setup>`**

Add after `const router = useRouter()`:

```js
const steps = [
  {
    num: '1', title: '파일 업로드',
    desc: '이력서, 프로젝트 문서, 논문을 업로드합니다.',
    detail: 'PDF, DOCX, TXT 지원. 파일 타입(이력서/프로젝트/논문/노트)을 선택하면 에이전트가 맥락을 파악합니다.',
  },
  {
    num: '2', title: '온톨로지 생성',
    desc: 'LLM이 문서에서 엔티티와 관계 타입을 추출합니다.',
    detail: 'Person, Project, Skill 등 10가지 고정 엔티티 타입과 WORKED_AT, DEVELOPED 등 10가지 관계 타입을 확인할 수 있습니다.',
  },
  {
    num: '3', title: '그래프 구축',
    desc: 'NetworkX DiGraph에 노드와 엣지를 생성합니다.',
    detail: 'Fuzzy matching(유사도 0.85)으로 중복 엔티티를 자동 병합합니다. 기존 그래프에 파일을 추가하는 증분(incremental) 업데이트도 지원합니다.',
  },
  {
    num: '4', title: '결과 확인',
    desc: 'D3.js 그래프 시각화와 LLM 채팅으로 지식을 탐색합니다.',
    detail: '노드 타입별 필터링, 줌/패닝, 클릭으로 연결 정보 확인. 채팅창에서 "Python 관련 프로젝트 알려줘" 같은 자연어 질문이 가능합니다.',
  },
  {
    num: '5', title: 'Vault 내보내기',
    desc: 'Obsidian markdown으로 내보내고 Syncthing으로 Mac에 동기화합니다.',
    detail: 'YAML frontmatter, [[wikilinks]], _index.canvas 자동 생성. Syncthing 설정 시 파일 변경 즉시 Mac Obsidian에 반영됩니다.',
  },
]

const agentSpecs = [
  { name: 'ParserAgent',          input: '파일 경로[]',           output: 'TextChunk[]',      logic: 'CHUNK_SIZE=500, OVERLAP=50' },
  { name: 'OntologyAgent',        input: 'TextChunk[]',           output: 'Ontology',         logic: 'LLM chat_json, 50,000자 샘플' },
  { name: 'GraphBuilderAgent',    input: 'TextChunk[], Ontology', output: 'nx.DiGraph',       logic: 'Fuzzy dedup 0.85, incremental' },
  { name: 'ProfileAgent',         input: 'nx.DiGraph',            output: 'CareerProfile[]',  logic: 'BFS 50노드, Person 기준' },
  { name: 'ObsidianWriterAgent',  input: 'DiGraph, Profile[]',    output: 'vault/ Markdown',  logic: 'YAML frontmatter, wikilinks, canvas' },
  { name: 'QueryAgent',           input: '질문, graph, chunks',   output: 'SSE stream',       logic: 'BFS 검색, 한국어 substring 매칭' },
]

const modelSpecs = [
  { name: 'TextChunk',     fields: 'chunk_id, text, source_file, file_type, page_num?, char_offset' },
  { name: 'Ontology',      fields: 'entity_types: EntityTypeDef[], edge_types: EdgeTypeDef[]' },
  { name: 'CareerProfile', fields: 'name, expertise[], skills[], projects[], organizations[], publications[], achievements[], persona_summary, timeline[]' },
  { name: 'GraphStats',    fields: 'total_nodes, total_edges, nodes_by_type: dict, edges_by_type: dict' },
]

const apiSpecs = [
  { method: 'POST',   path: '/projects',                          desc: '프로젝트 생성' },
  { method: 'GET',    path: '/projects',                          desc: '프로젝트 목록' },
  { method: 'DELETE', path: '/projects/{id}',                     desc: '프로젝트 삭제' },
  { method: 'POST',   path: '/projects/{id}/files',               desc: '파일 업로드 → 파싱 태스크 시작' },
  { method: 'POST',   path: '/projects/{id}/ontology',            desc: '온톨로지 생성 태스크 시작' },
  { method: 'GET',    path: '/projects/{id}/ontology',            desc: '온톨로지 조회' },
  { method: 'POST',   path: '/projects/{id}/graph',               desc: '그래프 구축 태스크 시작' },
  { method: 'GET',    path: '/projects/{id}/graph',               desc: '그래프 데이터 조회' },
  { method: 'GET',    path: '/projects/{id}/graph/stats',         desc: '그래프 통계' },
  { method: 'GET',    path: '/projects/{id}/profiles',            desc: '커리어 프로필 목록' },
  { method: 'GET',    path: '/projects/{id}/vault',               desc: 'Vault 파일 트리' },
  { method: 'GET',    path: '/projects/{id}/vault/download',      desc: 'Vault ZIP 다운로드' },
  { method: 'POST',   path: '/projects/{id}/chat',                desc: 'SSE 채팅 스트리밍' },
  { method: 'GET',    path: '/tasks/{id}',                        desc: '태스크 상태 조회' },
  { method: 'GET',    path: '/tasks/{id}/stream',                 desc: '태스크 진행 SSE 스트림' },
]
```

- [ ] **Step 3: Add CSS for sections 3 & 4**

Add to `<style scoped>`:

```css
/* User Guide */
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.guide-card {
  display: flex; gap: 16px; background: white; border-radius: 10px;
  padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border: 1px solid #ebeef5;
}
.step-badge {
  width: 36px; height: 36px; border-radius: 50%; background: #409eff;
  color: white; font-size: 16px; font-weight: bold;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.step-title { font-size: 15px; font-weight: bold; color: #303133; margin-bottom: 6px; }
.step-desc { font-size: 13px; color: #606266; margin-bottom: 6px; }
.step-detail { font-size: 12px; color: #909399; line-height: 1.6; }
```

- [ ] **Step 4: Verify build**

```bash
cd src/frontend && npm run build 2>&1 | tail -3
```

Expected: `✓ built in N.NNs`

- [ ] **Step 5: Commit**

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS
git add src/frontend/src/views/AboutView.vue
git commit -m "feat: AboutView — workflow diagram and full description page"
```

---

## 완료 검증

모든 태스크 완료 후 확인:

```bash
# 백엔드 테스트 59개 통과
cd src/backend && python3 -m pytest tests/ -v 2>&1 | tail -3

# 프론트엔드 빌드 성공
cd src/frontend && npm run build 2>&1 | tail -3
```

---

## 요약

| 태스크 | 범위 | 커밋 |
|--------|------|------|
| Task 1 | git mv + Syncthing 경로 + .gitignore | `refactor: move backend + frontend into src/` |
| Task 2 | CLAUDE.md 5개 파일 | `docs: add per-directory CLAUDE.md files` |
| Task 3 | AboutView 스켈레톤 + 라우터 + HomeView 링크 | `feat: add /about route and HomeView header link` |
| Task 4 | 아키텍처 다이어그램 + 파이프라인 플로우차트 | *(Task 5와 합산)* |
| Task 5 | 사용 가이드 5단계 + 기술 상세 + 커밋 | `feat: AboutView — workflow diagram and full description page` |
