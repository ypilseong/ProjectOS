# Hot Cache — 세션 진입 컨텍스트 설계

> 개선 항목 #3. claude-obsidian의 `hot.md`에 대응하는, MCP 세션 진입 시점에 그래프 상태를 압축 요약한 컨텍스트를 결정적으로 생성한다.

**목표:** NetworkX 그래프를 입력으로 받아 "지금 이 프로젝트가 무엇에 관한 것인가"를 한눈에 보여주는 압축 컨텍스트(`hot.md`)를 LLM 없이 결정적으로 조립하고, vault에 빌드 시 생성하며 MCP 도구로도 노출한다.

**범위 결정 (사용자 확정):**
- 콘텐츠 범위: 신원(주요 인물) + 허브(타입별 top 엔티티) + 최근 활동(log) + 공백(고립 노드) + 요약 통계.
- 전달 방식: vault `hot.md` 생성(빌드 시, `_index.md`처럼) + `projectos_get_hot_context` MCP 도구.
- 생성 방식: 결정적(no-LLM). 기존 `_render_index`/`run_health_check` 패턴 미러링.
- 모듈 배치: 독립 모듈 `app/services/hot_context.py`. `ObsidianWriterAgent`와 MCP 도구가 각각 호출.

**기술 스택:** Python, NetworkX, 기존 `app/utils/graph_health.py` 헬퍼(`check_hub_nodes`, `check_isolated_nodes`) 재사용.

---

## 배경

ProjectOS는 MCP를 통해 Claude Desktop에 ~31개 `projectos_*` 도구를 노출한다. 하지만 세션이 시작될 때 모델은 그래프가 어떤 상태인지(주요 인물이 누구인지, 어떤 엔티티가 중심인지, 최근에 무엇이 바뀌었는지, 어디가 비어 있는지) 전혀 모른 채 출발한다. 매번 여러 도구를 호출해 상태를 재구성해야 한다.

claude-obsidian은 이를 `hot.md` — 세션 진입 시 읽는 압축 요약 파일 — 로 해결한다. ProjectOS에는 대응물이 없다.

이미 존재하는 자산:
- `app/utils/graph_health.py` — `check_hub_nodes(graph, max_degree)`(차수순 허브), `check_isolated_nodes(graph)`(고립 노드), `run_health_check`(요약 통계).
- `app/agents/obsidian_writer_agent.py` — `_render_index`(타입별 엔티티 목록), `_append_log`(log.md 빌드 이벤트), `build_payload`(demote+build_entity_details 적용한 렌더 그래프 산출).
- `app/services/vault_reconcile.py:_rendered_graph` — 원시 그래프에 demote+details를 적용해 렌더 그래프를 얻는 동일 패턴.

빠진 조각: 위 자산들을 한 장으로 압축하는 **조립기(composer)**.

## 접근 방식

**선택: 결정적 그래프 조립기 + 마크다운 렌더러.** 그래프 메트릭(차수, 고립, 카운트)과 log 꼬리는 모두 결정적으로 계산 가능하다. LLM 추출/요약은 비결정성·비용·환각 위험을 들이며, hot 컨텍스트는 "사실 스냅샷"이라 요약 문장이 필요 없다. 기존 health/index 헬퍼에 그대로 연결된다.

탈락:
- **LLM 요약** — 비결정성·비용. 매 빌드/세션마다 호출은 과함.
- **graph.json 그대로 덤프** — 압축이 목적인데 압축이 안 됨. 모델이 다시 파싱해야 함.

**렌더 그래프 기준:** hub/고립/통계는 사용자가 실제로 보는 페이지 집합과 일치해야 하므로, 원시 `graph.json`이 아니라 `demote_project_context_nodes`+`build_entity_details`를 적용한 **렌더 그래프 R**에서 계산한다(vault_reconcile와 동일 정책). Category·이름 없는 노드는 제외.

## 컴포넌트

신규 모듈 `app/services/hot_context.py`.

### 1. 조립기 (Composer)

```python
def compose_hot_context(
    graph: nx.DiGraph,
    project_id: str | None = None,
    recent_log: list[str] | None = None,
    top_n: int = 5,
    recent_n: int = 5,
) -> dict
```

입력은 **렌더 그래프**(이미 demote+details 적용됨)로 가정한다. 반환:

```python
{
    "project_id": str | None,
    "persona": [{"name": str, "type": "Person", "degree": int, "description": str}],   # 최고 차수 Person top_n
    "hubs_by_type": {                                                                   # 타입별 최고 차수 top_n (Person 제외)
        "Project": [{"name": str, "degree": int}],
        "Skill": [...],
        ...
    },
    "recent_activity": [str],   # recent_log 꼬리 recent_n 줄 (## 헤더 라인만), 없으면 []
    "gaps": [{"name": str, "type": str}],   # 고립 노드(이름 있는 것), 최대 top_n*2
    "stats": {"total_nodes": int, "total_edges": int, "by_type": {type: count}},
}
```

규칙:
- **persona**: `type == "Person"`인 노드를 `graph.degree` 내림차순 정렬, 동률 시 이름 오름차순(결정성). top_n개. description은 `data.get("description","")`의 앞 80자.
- **hubs_by_type**: Person·Category·이름 없는 노드 제외. 타입별로 차수 내림차순(동률 이름 오름차순) top_n. 빈 타입은 키 생략.
- **recent_activity**: `recent_log`(호출자가 vault/log.md에서 읽어 전달)에서 `## `로 시작하는 빌드 이벤트 헤더 라인만 추려 최근 recent_n개. log 없으면 빈 리스트.
- **gaps**: `check_isolated_nodes(graph)` 중 이름 있는 것, 이름 오름차순, 최대 `top_n*2`개.
- **stats**: 전체 노드/엣지 수(Category 포함 원시 R 기준은 혼동되므로, 페이지 대상 노드 = 비-Category·이름 있는 노드 기준으로 집계). `by_type`은 비-Category 타입별 카운트.

순수 함수 — 파일 I/O 없음. `recent_log`는 호출자가 주입(테스트 용이, writer/MCP가 vault 경로 차이를 흡수).

### 2. 마크다운 렌더러

```python
def render_hot_markdown(ctx: dict) -> str
```

`compose_hot_context` 결과를 결정적 마크다운으로 변환:

```markdown
# Hot Context — {project_id}

_Auto-generated session primer. Do not edit manually._

## 주요 인물
- [[{name}]] (deg {degree}) — {description}

## 핵심 엔티티
### {type}
- [[{name}]] (deg {degree})

## 최근 활동
- {recent header line}

## 공백 (연결 보강 후보)
- [[{name}]] ({type})

## 요약
- Nodes: {total_nodes}, Edges: {total_edges}
- {type}: {count}, ...
```

빈 섹션(persona 없음 등)은 "- (없음)" 한 줄로 표기해 구조 유지. 엔티티 이름은 `[[...]]` 위키링크로 렌더(Obsidian 그래프뷰 연동).

### 3. Writer 통합

`ObsidianWriterAgent`에 hot.md 생성 연결:
- `VaultPayload`에 `rendered_graph: nx.DiGraph` 필드 추가. `build_payload`가 demote+details 적용 후의 graph를 여기에 담는다(이미 지역 변수로 존재).
- `run()`에서 `write_payload` 완료(=`_append_log`로 log.md 갱신 완료) 후 `_write_hot(vault, payload.rendered_graph, project_id)` 호출. 이 시점에 log.md가 최신이라 recent_activity가 이번 빌드를 포함한다.
- `_write_hot(vault, graph, project_id)`: `recent_log = (vault/log.md).read_text().splitlines()` (없으면 None) → `compose_hot_context` → `render_hot_markdown` → `(vault/"hot.md").write_text(...)`.

`build_payload`는 순수 유지(파일 I/O 없음). hot.md 쓰기는 `run()` 경로에서만. delta/full 빌드 모두 동일하게 갱신(hot은 항상 전체 재계산이라 delta 머지 불필요).

### 4. MCP 도구

`app/mcp_tools.py`에 `projectos_get_hot_context(project_id)` 등록 — `projectos_run_health_check` 패턴 미러링:
- `_require_project(project_id)`로 존재 검증.
- `graph.json` 로드 → `_rendered_graph` 동등 변환(demote+details) → `compose_hot_context(rendered, project_id, recent_log=<vault/{project_id}/log.md tail>)`.
- 반환: `_text_result(render_hot_markdown(ctx), ctx)` — 마크다운 텍스트 + 구조화 dict 동시 제공.
- 그래프 미빌드 시 graph_patch/reconcile 도구와 동일하게 명확한 에러.

렌더 그래프 변환은 `vault_reconcile._rendered_graph`와 중복되므로, 해당 헬퍼를 재사용하거나(import) hot_context에 동등 헬퍼를 두지 않고 mcp_tools에서 직접 조립. **결정: `vault_reconcile._rendered_graph`를 import해 재사용**(이미 검증된 동일 정책, DRY).

## 데이터 흐름

```
빌드 경로:
  graph ──demote+details──> R ──build_payload──> VaultPayload(rendered_graph=R)
                                                      │ write_payload → _index.md, log.md
                                                      ▼
                                     run(): _write_hot(vault, R, pid)
                                                      │ read vault/log.md tail
                                                      ▼
                              compose_hot_context → render_hot_markdown → hot.md

MCP 경로:
  graph.json ──load──> G ──_rendered_graph──> R
                                                │ read vault/{pid}/log.md tail
                                                ▼
                          compose_hot_context → {structured + markdown} → 도구 응답
```

## 에러 처리

- graph.json 부재(MCP) → 명확한 에러(hot 만들 그래프 없음).
- log.md 부재 → recent_activity 빈 리스트, 전체는 정상 진행.
- 빈 그래프 → 모든 섹션 "(없음)", stats 0. 에러 아님.
- writer hot.md 쓰기 실패는 빌드를 실패시키지 않도록 처리(로그 경고). _index.md/log.md와 동일 best-effort.

## 테스트 (TDD)

`tests/test_services/test_hot_context.py`:

1. `compose_hot_context` — persona: 최고 차수 Person이 차수 내림차순으로, top_n 제한.
2. `compose_hot_context` — hubs_by_type: 타입별 top 허브, Person/Category 제외.
3. `compose_hot_context` — gaps: 고립 노드만, 이름 오름차순.
4. `compose_hot_context` — recent_activity: recent_log의 `## ` 헤더만 최근 recent_n개.
5. `compose_hot_context` — stats: 비-Category 노드/엣지/타입별 카운트.
6. `compose_hot_context` — 빈 그래프: 모든 섹션 빈 값, 에러 없음.
7. `render_hot_markdown` — 섹션 헤더·위키링크·빈 섹션 "(없음)" 렌더.
8. `render_hot_markdown` — 결정성: 같은 입력 두 번 호출 시 동일 출력.

`tests/test_agents/test_obsidian_writer_agent.py` (기존 파일 추가):

9. writer `run()` — 빌드 후 vault에 hot.md 생성, 주요 섹션 포함.
10. writer — recent_activity가 이번 빌드 log 엔트리를 포함(append_log 이후 생성 순서 검증).

`tests/test_api/test_mcp_api.py` (기존 파일 추가):

11. `projectos_get_hot_context` — 도구 목록 등록 + 호출 시 structuredContent에 persona/hubs/stats 포함.
12. `projectos_get_hot_context` — 미빌드 프로젝트 시 isError.

## 비범위 (YAGNI)

- LLM 기반 요약/내러티브.
- hot.md 수동 편집 역반영(읽기 전용 산출물).
- 세션 외 자동 푸시/알림.
- 도메인별 가중치 튜닝(차수 외 중요도 점수).
