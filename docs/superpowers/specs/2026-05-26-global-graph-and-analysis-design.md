# Global Graph View & Document Analysis Design

**Date:** 2026-05-26  
**Status:** Approved

## Overview

두 가지 기능을 추가한다:

1. **전체 그래프 뷰** — 모든 프로젝트의 그래프를 런타임에 병합하여 하나의 통합 그래프로 시각화. 프로젝트 노드 클릭 시 해당 프로젝트 상세 페이지로 이동.
2. **문서 분석** — 프로젝트의 모든 파일을 대상으로 LLM이 약점과 개선 방향을 분석. 결과는 캐싱되며 사용자가 명시적으로 재분석을 요청할 때만 재실행.

## Architecture

### Data Flow

```
[전체 그래프]
HomeView → GET /graph/global
         ← 모든 projects/ 디렉토리 스캔
         ← graph.json 존재하는 프로젝트만 병합
         ← nodes에 project_id 네임스페이스 태깅
         ← 응답 반환

[문서 분석]
사이드바 버튼 → POST /projects/{id}/analysis
              → task_manager.create() → task_id 즉시 반환
              → asyncio.create_task(_run_analysis())
                  → AnalysisAgent.run(chunks, graph)
                      → LLM 호출 1: 약점 분석 (issues JSON)
                      → LLM 호출 2: 개선 초안 생성 (improved_draft)
                  → analysis.json 저장
              ← SSE 진행 스트림 (기존 tasks 라우터)
              ← GET /projects/{id}/analysis (캐시된 결과)
```

### Changed Files

```
Backend
├── app/agents/analysis_agent.py        [신규]
├── app/api/graph.py                    [변경] GET /graph/global 추가
├── app/api/projects.py                 [변경] POST/GET /{id}/analysis 추가
└── app/main.py                         [변경] /graph/global 라우터 등록

Frontend
├── src/views/HomeView.vue              [변경] 전체 그래프 탭 추가
├── src/views/ProjectDetail.vue         [변경] 사이드바 분석 섹션 추가
├── src/components/GraphView.vue        [변경] projectColors prop 추가
├── src/components/AnalysisDrawer.vue   [신규]
└── src/api/client.js                   [변경] 새 엔드포인트 메서드 추가
```

## Backend Design

### GET /graph/global

`app/api/graph.py`에 새 엔드포인트 추가. prefix는 기존 `/projects/{project_id}` 라우터와 분리하기 위해 별도 라우터(`/graph`)로 등록.

**응답 스키마:**

```json
{
  "nodes": [
    {
      "id": "abc123::node1",
      "name": "홍길동",
      "type": "Person",
      "project_id": "abc123",
      "project_name": "내 이력서"
    }
  ],
  "links": [
    {
      "source": "abc123::node1",
      "target": "abc123::node2",
      "relation": "USES_SKILL"
    }
  ],
  "projects": [
    { "id": "abc123", "name": "내 이력서", "color": "#4A90D9" }
  ]
}
```

**병합 로직:**
- `PROJECTS_DIR` 내 모든 서브디렉토리 스캔
- `graph.json`이 존재하는 디렉토리만 처리
- `meta.json`에서 프로젝트 이름 읽기
- 노드 ID: `{project_id}::{original_id}` 형태로 네임스페이스화
- 링크의 source/target도 동일하게 네임스페이스화
- 프로젝트별 색상: 고정 팔레트 순환 (`PROJECT_COLORS` 리스트)
- 그래프가 하나도 없으면 빈 응답 반환 (에러 아님)

**라우터 등록:** `app/main.py`에 `/graph` prefix로 별도 라우터 등록 (`app/api/graph_global.py` 신규 파일 또는 기존 `graph.py`에서 분리). `main.py` 변경 목록에 포함.

### AnalysisAgent (신규)

**파일:** `app/agents/analysis_agent.py`

```python
class AnalysisAgent:
    async def run(self, chunks: list[TextChunk], graph: nx.DiGraph) -> dict:
        ...
```

**LLM 호출 1 — 약점 분석:**

입력: 전체 청크 텍스트 + 그래프 통계(노드 수, 타입별 분포)  
프롬프트: 문서의 약점, 누락된 정보, 개선이 필요한 섹션을 한국어로 분석  
출력 형식:

```json
{
  "summary": "전반적 평가 2~3문장",
  "issues": [
    {
      "category": "기술 스택",
      "severity": "high",
      "description": "구체적 문제 설명",
      "suggestion": "개선 제안"
    }
  ]
}
```

severity 값: `"high"` | `"medium"` | `"low"`

**LLM 호출 2 — 개선 초안:**

입력: issues 리스트 + 원본 텍스트  
프롬프트: issues를 반영하여 개선된 전체 문서 초안 생성  
출력: 마크다운 텍스트 (스트리밍 아님, 단일 응답)

**저장 포맷 (`analysis.json`):**

```json
{
  "generated_at": "2026-05-26T12:00:00",
  "summary": "...",
  "issues": [...],
  "improved_draft": "..."
}
```

### API 엔드포인트 (projects.py 추가)

| 메서드 | 경로 | 동작 |
|--------|------|------|
| `POST` | `/projects/{id}/analysis` | 분석 태스크 생성, `{"task_id": "..."}` 반환 |
| `GET` | `/projects/{id}/analysis` | `analysis.json` 반환, 없으면 404 |

`_run_analysis(task_id, project_id)` 내부 함수:
1. `chunks.json` 로드
2. `graph.json` 로드 (없으면 청크만으로 분석)
3. `AnalysisAgent().run(chunks, graph)` 호출
4. `analysis.json` 저장
5. TaskStatus.COMPLETED 업데이트

## Frontend Design

### HomeView.vue 변경

`el-tabs`로 "프로젝트 목록 | 전체 그래프" 전환:

- 탭 전환 시 `GET /graph/global` 호출 (첫 1회만, 이후 캐시)
- 기존 `GraphView` 컴포넌트 재사용
- `projectColors` prop으로 `{ [project_id]: color }` 맵 전달
- 전체 그래프 모드에서 툴바에 프로젝트 범례 표시
- `Project` 타입 노드 클릭 시 `router.push('/projects/{project_id}')` (단, 전체 그래프 모드일 때만)

### GraphView.vue 변경

새 prop 추가:

```js
defineProps({
  graphData: { type: Object, default: null },
  projectColors: { type: Object, default: null },   // { project_id: color }
  onProjectClick: { type: Function, default: null }, // 전체 그래프 모드 콜백
})
```

노드 색상 결정 우선순위:
1. `projectColors`가 있고 노드에 `project_id`가 있으면 → 프로젝트 색상
2. 없으면 → 기존 타입별 `NODE_COLORS`

### ProjectDetail.vue 변경 — 사이드바 분석 섹션

사이드바 하단 `el-divider` 이후에 추가:

```
[문서 분석]
상태별 버튼:
  - analysis.json 없음 + 태스크 미실행: [분석 실행] 버튼
  - 태스크 실행 중: ProgressPanel (SSE)
  - 완료: [분석 결과 보기] + [재분석] 버튼
```

로직:
- 마운트 시 `GET /projects/{id}/analysis` 호출 → 성공 시 `analysisData` 세팅
- "분석 실행" 클릭 → `POST /projects/{id}/analysis` → task_id → ProgressPanel
- 완료 시 자동으로 `AnalysisDrawer` 열림
- "재분석" 클릭 → 기존 analysisData 유지한 채 새 태스크 실행, 완료 후 갱신

### AnalysisDrawer.vue (신규)

`el-drawer` 기반, `size="480px"`, `direction="rtl"`:

```
제목: "문서 분석 결과"
───────────────────────
요약 텍스트 (summary 필드)

[개선 포인트] [개선 초안]  ← el-tabs
───────────────────────
개선 포인트 탭:
  el-tag (severity별 색상: high=#E74C3C, medium=#E8A838, low=#95A5A6)
  카테고리 + 설명 + 제안 카드 리스트

개선 초안 탭:
  improved_draft 마크다운 텍스트
  (el-scrollbar + pre 태그 또는 마크다운 렌더러)
```

Props: `{ analysisData: Object, visible: Boolean }`  
Emits: `update:visible`

### client.js 변경

```js
// 기존 projectsApi에 추가
runAnalysis: (id) => api.post(`/projects/${id}/analysis`),
getAnalysis: (id) => api.get(`/projects/${id}/analysis`),

// 신규 globalApi
export const globalApi = {
  getGraph: () => api.get('/graph/global'),
}
```

## Error Handling

- `GET /graph/global`: 그래프가 없는 프로젝트는 조용히 건너뜀. 모든 프로젝트에 그래프 없으면 빈 응답.
- `POST /projects/{id}/analysis`: `chunks.json` 없으면 즉시 실패 (400). `graph.json` 없으면 청크만으로 분석 진행.
- 분석 LLM 응답 파싱 실패 시 TaskStatus.FAILED로 업데이트.

## Testing

- `tests/test_agents/test_analysis_agent.py`: mock LLM으로 issues 구조 검증
- `tests/test_api/test_graph_global.py`: 프로젝트 없을 때 빈 응답, 여러 프로젝트 병합 시 네임스페이스 충돌 없는지 검증
- Frontend: 기존 GraphView 타입 필터 동작 유지 확인 (회귀 테스트)
