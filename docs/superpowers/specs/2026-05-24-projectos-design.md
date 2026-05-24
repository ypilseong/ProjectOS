# ProjectOS — Design Specification

**Date**: 2026-05-24  
**Language**: Korean / English  
**Status**: Approved

---

## 1. Overview / 개요

ProjectOS는 로컬 파일(이력서, 프로젝트 문서, 연구 논문)을 분석해  
개인 커리어와 프로젝트 관계를 Obsidian 기반 지식 그래프로 시각화하는 시스템입니다.

MiroFish(멀티에이전트 예측 엔진)의 아키텍처 패턴을 참고하되,  
**Zep Cloud → NetworkX(로컬 그래프)**, **소셜 시뮬레이션 → 커리어 시각화**로 전환합니다.

### Core Goals
- 로컬 파일 → LLM 기반 엔티티/관계 추출 → NetworkX 그래프
- 그래프 → Obsidian vault (.md + wikilinks + YAML frontmatter)
- FastAPI + Vue.js UI (MiroFish 수준의 정보량)
- LLM 기반 그래프 채팅 패널 (InsightForge 패턴)
- 증분 파일 업로드 → 실시간 vault 업데이트

---

## 2. Architecture / 아키텍처

### 2.1 System Overview

```
[Web Browser / Vue.js]
        ↕ HTTP/SSE
[FastAPI Backend]
        ↕
[Agent Orchestrator]
   ├── ParserAgent       : 파일 텍스트 추출 + 청크화
   ├── OntologyAgent     : LLM 엔티티/관계 타입 정의
   ├── GraphBuilderAgent : NetworkX 로컬 그래프 구축
   ├── ProfileAgent      : Person 엔티티 → 커리어 페르소나
   ├── ObsidianWriterAgent: 그래프 → Obsidian vault
   └── QueryAgent        : 그래프 기반 LLM 채팅
        ↕
[Local Storage]
   /projects/<project_id>/
     files/          - 업로드된 원본 파일
     chunks.json     - 텍스트 청크
     ontology.json   - 엔티티/관계 타입 정의
     graph.json      - NetworkX 직렬화 (node_link_data)
     profiles.json   - 커리어 페르소나
   /vault/           - Obsidian vault
     Career/
     Projects/
     Skills/
     Organizations/
     Publications/
     .obsidian/      - Obsidian 설정
```

### 2.2 MiroFish Comparison

| MiroFish | ProjectOS |
|---|---|
| Zep Cloud API (원격 그래프) | NetworkX (로컬 그래프) |
| `zep_entity_reader.py` | `GraphBuilderAgent` 내부 쿼리 |
| `zep_graph_memory_updater.py` | `ObsidianWriterAgent` (delta write) |
| `zep_tools.py` InsightForge | `QueryAgent` |
| OASIS 소셜 시뮬레이션 페르소나 | 커리어/프로젝트 페르소나 |
| 소셜 미디어 출력 | Obsidian vault 출력 |

---

## 3. Agent Specifications / 에이전트 상세 명세

### 3.1 ParserAgent

**Input**: `List[FilePath]`  
**Output**: `List[TextChunk]`

```python
@dataclass
class TextChunk:
    chunk_id: str       # UUID
    text: str
    source_file: str    # 원본 파일명
    file_type: str      # cv / project / publication
    page_num: int | None
    char_offset: int
```

- 지원 포맷: PDF (PyMuPDF), DOCX (python-docx), MD/TXT (charset-normalizer)
- 청크 크기: 500자, 오버랩: 50자 (MiroFish `text_processor.py` 동일)
- 청크별 출처 메타데이터 보존

### 3.2 OntologyAgent

**Input**: `List[TextChunk]` (최대 50,000자 샘플)  
**Output**: `Ontology`

```python
@dataclass
class Ontology:
    entity_types: List[EntityTypeDef]   # 10종 고정 + LLM 보완
    edge_types: List[EdgeTypeDef]
    analysis_summary: str
```

**고정 엔티티 타입 10종:**
`Person`, `Project`, `Skill`, `Organization`, `Publication`,  
`Technology`, `Role`, `Achievement`, `Event`, `Institution`

**주요 관계 타입:**
`WORKED_AT`, `DEVELOPED`, `USES_SKILL`, `AUTHORED`,  
`COLLABORATED_WITH`, `ACHIEVED`, `PARTICIPATED_IN`, `PUBLISHED_AT`,  
`MENTORED_BY`, `LED_BY`

- MiroFish `ontology_generator.py` 패턴 재사용 (도메인만 커리어로 변경)
- LLM 프롬프트: 소셜 미디어 행위자 대신 "커리어/프로젝트 행위자" 중심

### 3.3 GraphBuilderAgent

**Input**: `List[TextChunk]` + `Ontology`  
**Output**: `nx.DiGraph` + 통계

- LLM이 청크별 엔티티(노드) + 관계(엣지) 추출
- `networkx.DiGraph` 누적 → `nx.node_link_data()`로 `graph.json` 직렬화
- 중복 엔티티 병합: 이름 fuzzy match (difflib, threshold=0.85)
- 노드 속성: `type`, `name`, `description`, `source_files`, `attributes`
- 엣지 속성: `relation`, `confidence`, `source_chunk_id`

**Incremental Mode:**
- `incremental=True` 시 기존 `graph.json` 로드 → 신규 노드/엣지만 추가
- 기존 노드와 fuzzy match 후 병합 (덮어쓰기 아닌 속성 병합)

### 3.4 ProfileAgent

**Input**: `nx.DiGraph` (Person 노드 중심)  
**Output**: `List[CareerProfile]`

```python
@dataclass
class CareerProfile:
    name: str
    expertise: List[str]      # 주요 전문 분야
    skills: List[str]         # 기술 스택
    projects: List[str]       # 주요 프로젝트
    organizations: List[str]  # 소속 기관
    publications: List[str]   # 논문/보고서
    achievements: List[str]   # 성과
    persona_summary: str      # LLM 생성 종합 요약 (2000자)
    timeline: List[dict]      # 시간순 이력
```

- MiroFish `oasis_profile_generator.py` 패턴 참고
- 병렬 처리: `asyncio.gather` 또는 ThreadPoolExecutor

### 3.5 ObsidianWriterAgent

**Input**: `nx.DiGraph` + `List[CareerProfile]`  
**Output**: `/vault/` 디렉터리

**Vault 구조:**
```
vault/
  .obsidian/
    app.json          - 기본 설정
    graph.json        - graph view 설정 (color by type)
  Career/
    <name>.md         - Person 노드 (메인 프로필)
  Projects/
    <project>.md      - Project 노드
  Skills/
    <skill>.md        - Skill 노드
  Organizations/
    <org>.md          - Organization 노드
  Publications/
    <pub>.md          - Publication 노드
  _index.canvas       - 전체 그래프 Canvas 파일
```

**노트 포맷:**
```markdown
---
type: Project
name: "딥러닝 기반 이상탐지"
tags: [project, deep-learning, anomaly-detection]
created: 2026-05-24
skills: [PyTorch, Python, LSTM]
organizations: [KAIST]
---

# 딥러닝 기반 이상탐지

## Overview
...LLM 생성 설명...

## Connections
- Person: [[양필성]]
- Skills: [[PyTorch]], [[LSTM]]
- Organization: [[KAIST]]
```

**Delta Write**: 파일 존재 시 frontmatter 병합 + 새 wikilinks 추가 (덮어쓰기 없음)

### 3.6 QueryAgent

**Input**: 사용자 질문 (자연어) + `nx.DiGraph` + `List[TextChunk]`  
**Output**: LLM 생성 답변 (스트리밍 SSE)

**3단계 검색 (MiroFish InsightForge 패턴):**
1. **SubQuery**: LLM이 원래 질문을 2-3개 서브쿼리로 분해
2. **Graph Search**: 각 서브쿼리로 NetworkX BFS + 키워드 매칭
3. **Synthesis**: 관련 노드/엣지 + 원본 청크 → LLM 종합 답변

---

## 4. API Design / API 설계

### FastAPI Endpoints

```
POST /api/projects                    - 프로젝트 생성
GET  /api/projects                    - 프로젝트 목록
GET  /api/projects/{id}               - 프로젝트 상세
DELETE /api/projects/{id}             - 프로젝트 삭제

POST /api/projects/{id}/files         - 파일 업로드 (초기)
POST /api/projects/{id}/files/add     - 파일 추가 (증분)

POST /api/projects/{id}/ontology      - OntologyAgent 실행
GET  /api/projects/{id}/ontology      - 온톨로지 조회

POST /api/projects/{id}/graph         - GraphBuilderAgent + ProfileAgent 실행
POST /api/projects/{id}/graph/incremental - 증분 그래프 업데이트
GET  /api/projects/{id}/graph         - 그래프 조회 (nodes/edges)
GET  /api/projects/{id}/graph/stats   - 그래프 통계

GET  /api/projects/{id}/profiles      - 프로필 목록
GET  /api/projects/{id}/vault         - vault 파일 트리
GET  /api/projects/{id}/vault/download - vault zip 다운로드

POST /api/projects/{id}/chat          - QueryAgent 채팅 (SSE 스트리밍)

GET  /api/tasks/{task_id}             - 백그라운드 작업 상태
GET  /api/tasks/{task_id}/stream      - 실시간 진행률 SSE
```

---

## 5. Frontend Design / 프론트엔드 설계

**Stack**: Vue.js 3 (Composition API) + Vite + Element Plus

**레이아웃 (MiroFish 수준 정보량):**

```
┌─────────────────────────────────────────────────┐
│  ProjectOS                        [KO | EN]     │
├──────────────┬──────────────────────────────────┤
│  LEFT PANEL  │  MAIN PANEL                      │
│              │                                  │
│  ■ Projects  │  [STEP 탭: 파일→온톨로지→그래프→결과]│
│  ■ Stats     │                                  │
│    N: 42     │  STEP 1: 파일 업로드              │
│    E: 87     │    Drag & Drop + 파일 타입 배지   │
│    Skill:15  │    파일별 상태 (파싱 완료/대기)   │
│    Proj: 8   │    [Generate Ontology →]         │
│    Org: 5    │                                  │
│              │  STEP 2: 온톨로지 검토            │
│  ■ Profile   │    엔티티 타입 카드 그리드         │
│  [이름]       │    관계 타입 테이블               │
│  [전문분야]   │    [Build Graph →]               │
│  [기술스택]   │                                  │
│  [프로젝트수] │  STEP 3: 빌딩 진행률             │
│              │    실시간 SSE 진행바              │
│  ■ Vault     │    처리 로그 (스크롤)             │
│  파일 트리뷰  │    노드/엣지 실시간 카운터         │
│              │                                  │
│              │  STEP 4: 결과 탭                  │
│              │  ┌──Graph View─┬──Chat──────────┐│
│              │  │ D3.js 인터  │ InsightForge   ││
│              │  │ 랙티브 그래 │ Q: 내 ML 프로젝││
│              │  │ 프 (타입별  │ A: 총 3개:...  ││
│              │  │ 색상 구분)  │                ││
│              │  │ 노드 클릭   │ [질문 입력]    ││
│              │  │ →상세패널   │                ││
│              │  └────────────┴────────────────┘│
│              │                                  │
│              │  STEP 5: Vault 내보내기           │
│              │    파일 트리 미리보기              │
│              │    [Download ZIP] [+파일 추가]   │
└──────────────┴──────────────────────────────────┘
```

**그래프 시각화**: D3.js force-directed graph
- 노드: 타입별 색상 (Person=파랑, Project=초록, Skill=주황, ...)
- 엣지: 관계 타입 레이블
- 클릭: 우측 상세 패널 (속성 + 연결 노드 목록)
- 필터: 타입별 표시/숨기기

---

## 6. Data Flow / 데이터 흐름

```
파일 업로드
    → ParserAgent (청크화)
    → chunks.json 저장

OntologyAgent
    → chunks.json 읽기 (샘플 50K자)
    → LLM 온톨로지 생성
    → ontology.json 저장

GraphBuilderAgent + ProfileAgent (병렬 실행 가능)
    → chunks.json + ontology.json 읽기
    → LLM 엔티티/관계 추출
    → NetworkX 그래프 구축
    → graph.json + profiles.json 저장

ObsidianWriterAgent
    → graph.json + profiles.json 읽기
    → vault/*.md 생성 (wikilinks + frontmatter)
    → _index.canvas 생성

[증분 업데이트]
새 파일 업로드
    → ParserAgent (신규만)
    → GraphBuilderAgent (incremental=True)
    → ObsidianWriterAgent (delta write: 변경된 노드만)
```

---

## 7. Project Structure / 프로젝트 구조

```
ProjectOS/
├── CLAUDE.md                  - 간단한 프로젝트 가이드
├── docs/
│   ├── agents.md              - 에이전트 상세 설명
│   ├── api.md                 - API 엔드포인트 문서
│   └── superpowers/specs/     - 설계 문서
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── projects.py
│   │   │   ├── graph.py
│   │   │   └── chat.py
│   │   ├── agents/
│   │   │   ├── parser_agent.py
│   │   │   ├── ontology_agent.py
│   │   │   ├── graph_builder_agent.py
│   │   │   ├── profile_agent.py
│   │   │   ├── obsidian_writer_agent.py
│   │   │   └── query_agent.py
│   │   ├── models/
│   │   │   ├── project.py
│   │   │   └── graph.py
│   │   ├── utils/
│   │   │   ├── file_parser.py   (MiroFish 참고)
│   │   │   ├── llm_client.py    (MiroFish 참고)
│   │   │   └── logger.py
│   │   └── config.py
│   ├── pyproject.toml
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── App.vue
│   │   ├── components/
│   │   │   ├── FileUpload.vue
│   │   │   ├── OntologyView.vue
│   │   │   ├── GraphView.vue       (D3.js)
│   │   │   ├── ChatPanel.vue
│   │   │   ├── ProfileCard.vue
│   │   │   └── VaultTree.vue
│   │   └── views/
│   │       └── ProjectDetail.vue
│   ├── package.json
│   └── vite.config.js
├── projects/                  - 프로젝트별 데이터 저장
└── vault/                     - Obsidian vault (기본)
```

---

## 8. Configuration / 설정

**`.env` 파일:**
```env
# LLM (OpenAI-compatible)
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# Graph
CHUNK_SIZE=500
CHUNK_OVERLAP=50
FUZZY_MATCH_THRESHOLD=0.85
MAX_ONTOLOGY_SAMPLE_CHARS=50000

# Vault
VAULT_PATH=./vault
PROJECTS_PATH=./projects
```

---

## 9. Non-Goals / 범위 외

- Zep Cloud / 외부 그래프 DB 연동 없음
- OASIS / 소셜 시뮬레이션 없음
- 실시간 다중 사용자 지원 없음
- MiroFish 파일 수정 없음 (읽기 참고만)
