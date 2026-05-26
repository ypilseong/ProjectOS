# ProjectOS — 폴더 구조 재편 + About 페이지 설계

**날짜:** 2026-05-26
**범위:** 폴더 구조 재편, CLAUDE.md 세분화, 워크플로우 다이어그램 페이지 추가

---

## 목표

1. `backend/` + `frontend/` 를 `src/` 하위로 이동 (모노레포 표준 레이아웃)
2. 각 하위 폴더에 CLAUDE.md 세분화 작성
3. `/about` 라우트에 워크플로우 다이어그램 + 설명 페이지 추가

---

## 1. 폴더 구조 재편

### 목표 구조

```
ProjectOS/
  src/
    backend/
      app/
        agents/         ← 6개 에이전트
        api/            ← 4개 라우터
        models/         ← 데이터 모델
        services/       ← TaskManager, ProjectStore
        utils/          ← LLMClient, FileParser
        config.py
        main.py
        __init__.py
      tests/
        test_agents/
        test_api/
        test_models/
        conftest.py
      scripts/          ← 유틸리티 스크립트 (신규)
      projects/         ← 프로젝트 데이터 (기존 backend/projects/ 유지)
      vault/            ← Obsidian vault (기존 backend/vault/ 유지)
      pyproject.toml
      run.py
    frontend/
      src/
        api/
        components/
        router/
        views/
        App.vue
        main.js
      public/
      index.html
      package.json
      vite.config.js
  docs/
  .env.example
  .gitignore
  CLAUDE.md
```

> **참고:** `projects/`와 `vault/`는 `src/backend/` 하위에 유지. config.py의 `PROJECTS_DIR=./projects`, `VAULT_DIR=./vault`는 실행 디렉토리(`src/backend/`) 기준 상대경로이므로 변경 불필요. Syncthing 절대경로만 업데이트 필요.

### 이동 작업

| 현재 경로 | 새 경로 |
|-----------|---------|
| `backend/` | `src/backend/` |
| `frontend/` | `src/frontend/` |

### 영향 검토

- **`src/backend/run.py`** — `uvicorn app.main:app` 유지 (실행 디렉토리 `src/backend/` 기준)
- **`src/backend/pyproject.toml`** — `find_packages(where=".")` 유지, `pip install -e ".[dev]"` 경로만 변경
- **`src/frontend/vite.config.js`** — 내부 상대경로만 사용하므로 변경 없음
- **Syncthing vault 경로** — 절대경로 사용 중이므로 변경 없음
- **`.gitignore`** — `projects/**/*.json`, `vault/**/*.json` 경로 패턴 유지 (절대경로 아님)
- **`CLAUDE.md` Quick Start** — 경로를 `src/backend`, `src/frontend`로 업데이트

---

## 2. CLAUDE.md 세분화

### 파일별 내용

**`CLAUDE.md` (루트)**
- 프로젝트 개요 1문단
- Quick Start: `cd src/backend && ...` / `cd src/frontend && ...`
- 핵심 규칙 (MiroFish 읽기 전용, 로컬 그래프, TDD, 언어)
- 하위 CLAUDE.md 링크 목록

**`src/backend/CLAUDE.md`**
- 설치: `pip install -e ".[dev]"`
- 테스트: `python3 -m pytest tests/ -v`
- 실행: `python3 run.py`
- 패키지 구조 설명 (app/agents, app/api, app/services, app/utils)
- 에이전트 파이프라인 순서

**`src/backend/app/agents/CLAUDE.md`**
- 에이전트 추가 방법 (BaseClass 없음, 독립 클래스)
- LLM 호출 패턴 (`llm_client.chat_json()` / `llm_client.stream()`)
- 고정 엔티티/관계 타입 목록
- Fuzzy matching threshold (0.85)

**`src/backend/app/api/CLAUDE.md`**
- FastAPI 라우터 등록 방법
- SSE 스트리밍 패턴 (tasks SSE, chat SSE)
- 에이전트 지연 임포트 패턴 (circular import 방지)
- 배경 태스크 패턴 (`asyncio.create_task`)

**`src/frontend/CLAUDE.md`**
- 개발 서버: `npm run dev` (포트 5173)
- 빌드: `npm run build`
- 컴포넌트 작성 패턴 (`<script setup>`)
- API 클라이언트 사용법 (`projectsApi`, `tasksApi`, `chatStreamUrl`)
- SSE 구독 패턴 (EventSource / fetch+ReadableStream)

---

## 3. About 페이지 (`/about`)

### 파일

- `src/frontend/src/views/AboutView.vue` (신규)
- `src/frontend/src/router/index.js` — `/about` 라우트 추가
- `src/frontend/src/views/HomeView.vue` — 헤더에 "워크플로우" 링크 추가

### 페이지 구조

```
┌─ el-header: "ProjectOS 작동 원리" + [← 홈] 버튼 ─┐
│                                                    │
│  섹션 1: 시스템 아키텍처 다이어그램                  │
│  섹션 2: 에이전트 파이프라인 플로우차트               │
│  섹션 3: 5단계 사용 가이드                           │
│  섹션 4: 기술 상세 (el-collapse)                    │
└────────────────────────────────────────────────────┘
```

### 섹션 1: 시스템 아키텍처 다이어그램

CSS Grid 4-레이어 구조. 레이어 간 양방향 화살표 (`↕`) CSS로 표현.

| 레이어 | 색상 | 내용 |
|--------|------|------|
| Frontend (Vue 3) | 파란색 (`#409eff`) | HomeView · ProjectDetail · AboutView |
| Backend (FastAPI) | 초록색 (`#67c23a`) | /projects · /graph · /chat · /tasks |
| Agent Pipeline | 주황색 (`#e6a23c`) | Parser→Ontology→Graph→Profile→Vault + QueryAgent |
| Storage | 보라색 (`#909399`) | NetworkX DiGraph · Obsidian Vault · Syncthing |

### 섹션 2: 에이전트 파이프라인 플로우차트

가로 Flexbox. 각 노드: 에이전트명 + 한 줄 역할 + 입출력 배지.

```
[파일] → [ParserAgent] → [OntologyAgent] → [GraphBuilderAgent] → [ProfileAgent] → [ObsidianWriterAgent]
                                                    ↓
                                              [QueryAgent]
                                              채팅 스트리밍
```

노드 스타일: 흰 배경 카드, 주황 테두리, 그림자. 화살표: CSS `::after` pseudo-element.

### 섹션 3: 5단계 사용 가이드

`el-card` 5개, 번호 배지 + 제목 + 설명.

| 단계 | 제목 | 설명 |
|------|------|------|
| 1 | 파일 업로드 | 이력서(PDF/DOCX), 프로젝트 문서, 논문을 업로드합니다. |
| 2 | 온톨로지 생성 | LLM이 문서에서 엔티티 타입과 관계 타입을 추출합니다. |
| 3 | 그래프 구축 | NetworkX DiGraph에 노드/엣지를 생성하고 중복을 제거합니다. |
| 4 | 결과 확인 | D3.js 그래프 시각화와 LLM 채팅으로 지식을 탐색합니다. |
| 5 | Vault 내보내기 | Obsidian markdown으로 내보내고 Syncthing으로 Mac에 동기화합니다. |

### 섹션 4: 기술 상세 (el-collapse)

3개 패널 (기본 접힘):

**에이전트 스펙**
| 에이전트 | 입력 | 출력 | 핵심 로직 |
|----------|------|------|-----------|
| ParserAgent | 파일 경로 | TextChunk[] | CHUNK_SIZE=500, OVERLAP=50 |
| OntologyAgent | TextChunk[] | Ontology | LLM chat_json, 50000자 샘플 |
| GraphBuilderAgent | TextChunk[], Ontology | nx.DiGraph | Fuzzy dedup 0.85, incremental 지원 |
| ProfileAgent | nx.DiGraph | CareerProfile[] | BFS 50노드, Person 노드 기준 |
| ObsidianWriterAgent | nx.DiGraph, CareerProfile[] | vault/ | YAML frontmatter, [[wikilinks]], canvas |
| QueryAgent | 질문, graph, chunks | SSE stream | BFS 검색, 한국어 substring 매칭 |

**데이터 모델**

| 모델 | 주요 필드 |
|------|-----------|
| TextChunk | chunk_id, text, source_file, file_type, page_num?, char_offset |
| Ontology | entity_types: EntityTypeDef[], edge_types: EdgeTypeDef[] |
| CareerProfile | name, expertise[], skills[], projects[], organizations[], publications[], achievements[], persona_summary, timeline[] |
| GraphStats | total_nodes, total_edges, nodes_by_type: dict, edges_by_type: dict |

**API 엔드포인트**
현재 `docs/api.md` 내용을 표로 정리

---

## 구현 순서

1. **폴더 이동** — `git mv backend src/backend`, `git mv frontend src/frontend`
2. **경로 수정** — CLAUDE.md, .gitignore 내 경로 업데이트
3. **CLAUDE.md 생성** — 4개 하위 파일 작성
4. **AboutView 구현** — Vue 컴포넌트 + 라우터 + HomeView 링크
5. **검증** — 테스트 59개 통과, 프론트엔드 빌드 성공
6. **커밋**
