# Autoresearch — 능동적 지식 보강 설계

> 개선 항목 #5. 그래프의 고립 노드, provenance 누락, 약한 연결, 중복 후보를 바탕으로 "무엇을 보강해야 하는지"를 결정적으로 제안한다.

**목표:** ProjectOS가 사용자나 Claude Desktop이 묻기 전에 그래프의 약점을 찾아 research/backfill 후보를 제시한다. 후보는 바로 graph를 수정하지 않고, source evidence를 확보한 뒤 `graph_patch`로 반영할 수 있게 만든다.

**범위 결정:**
- 1차 구현은 deterministic candidate generator.
- live web search, Google/Drive 자동 수집, LLM 요약, 자동 patch apply는 비범위.
- 출력은 MCP/Claude Desktop이 검수하기 쉬운 구조화 후보 리스트 + 짧은 text summary로 확장 가능해야 한다.

---

## 배경

ProjectOS에는 이미 그래프 약점 신호가 있다.

- `graph_health.check_isolated_nodes` — 연결 없는 노드.
- `graph_health.check_weak_components` — 분리된 컴포넌트.
- `graph_health.check_duplicate_candidates` — 이름 유사 중복 후보.
- `wiki_graph_lint.missing_source_nodes` — provenance 없는 노드.
- `digest._reinforcement_suggestions` — 사람이 읽는 보강 제안.

하지만 이 신호들은 사람이 읽는 health/digest 수준에 머물고, Claude Desktop이 "다음에 무엇을 조사해야 하는지"를 안정적으로 orchestrate하기 위한 구조화 candidate가 없다.

## 접근 방식

**선택: 결정적 후보 생성기.**

신규 서비스 `app/services/autoresearch.py`가 NetworkX graph를 입력받아 research/backfill/review 후보를 만든다.

```python
def generate_autoresearch_candidates(
    graph: nx.DiGraph,
    chunks: Iterable[Any] | None = None,
    health: dict | None = None,
    *,
    max_candidates: int = 20,
    min_degree: int = 1,
    component_size_threshold: int = 3,
    duplicate_threshold: float = 0.85,
) -> list[dict]
```

반환:

```python
[
    {
        "id": "isolated:Skill:Python",
        "kind": "research",
        "priority": 90,
        "node_id": "Skill:Python",
        "name": "Python",
        "type": "Skill",
        "reason": "Node has no non-category graph connections.",
        "suggested_query": "Find source evidence and graph relationships for Python Skill.",
        "source_files": ["cv.pdf"],
        "evidence": {"source_files": ["cv.pdf"]},
    }
]
```

후보 종류:

- `isolated:*` — degree 0, Category 제외. 최우선. 이미 source가 있으면 연결 관계 보강, source가 없으면 provenance 보강도 필요.
- `missing_source:*` — `source_files`가 없는 non-Category node. 외부/원문 evidence 확보 필요.
- `sparse_node:*` — 중요 타입(Person/Project/Organization/Publication/Achievement/Skill/Technology)인데 degree가 `min_degree` 이하. 연결이 약한 핵심 노드.
- `weak_component:*` — 작은 weak component. 메인 컴포넌트와 분리되어 있을 가능성.
- `duplicate:*` — `kind=review_needed`. research가 아니라 review 후보. 자동 보강보다 merge/delete 판단이 필요.

정렬:
- priority 내림차순.
- kind, type/name, node id 오름차순으로 tie-break.
- deterministic output 유지.

## 안전 원칙

- 후보 생성은 read-only.
- `Category`와 이름 없는 synthetic node는 제외.
- graph patch는 생성하지 않는다. patch는 source evidence가 확인된 뒤 별도 `projectos_apply_graph_patch`로만 적용한다.
- duplicate는 "research"가 아니라 "review"로 표시한다. 중복 후보를 외부 검색으로 보강하면 오히려 오염될 수 있다.
- suggested query는 검색 실행 명령이 아니라 사람이/Claude가 다음 단계에서 사용할 질의 초안이다.

## MCP 확장 후보

`projectos_get_research_candidates(project_id, max_candidates=20)` 도구를 추가한다.

동작:
- `_require_project(project_id)`
- graph load
- `run_health_check(graph)`와 `_load_chunks(project_id)`로 기존 evidence를 함께 전달.
- `generate_autoresearch_candidates(graph, chunks, health, max_candidates=...)`
- `_text_result(text_summary, {"project_id", "candidates", "summary"})`

이 도구는 전체 graph를 Claude Desktop에 덤프하지 않고 약점 후보만 전달하는 token 절약 도구 역할도 한다.

## 테스트

`tests/test_services/test_autoresearch.py`:
- isolated node 후보 생성 및 높은 priority.
- missing source 후보 생성.
- sparse important node 후보 생성, Category 제외.
- small component 후보 생성.
- duplicate review 후보 생성.
- max_candidates 제한과 deterministic 정렬.
- empty graph는 빈 후보.

## 비범위

- web search/browser 실행.
- Google Drive/Gmail 자동 검색.
- LLM fact synthesis.
- graph patch 자동 적용.
- 사용자 확인 없는 source 추가.
