# 토큰 절약 그래프 조회 도구 설계 (`get_subgraph` + `get_node_context`)

작성일: 2026-06-08
브랜치: `hybrid-retrieval`
관련 핸드오프 후보: "token 절약 subgraph/node-context 도구 설계" (반복 지목된 다음 후보)

## 배경 / 목적

ProjectOS는 Claude Desktop을 "고품질 검수자"로, local LLM/backend를 "대량 처리자"로 분리한다.
현재 Claude Desktop이 그래프를 보려면 전체 graph.json 수준의 context를 받아야 해서 토큰 비용이 크다.

이 작업은 Claude Desktop이 **전체 그래프 대신 필요한 이웃/단일 노드만** 받아볼 수 있는
read-only·결정적 MCP 도구 2종을 추가한다. 사용자가 강조한 "효율성"(토큰 절약)에 가장 직접적인 개선이다.

- `projectos_get_node_context` — 단일 노드 심층 조회 (속성·간선·source evidence opt-in).
- `projectos_get_subgraph` — seed 노드 주변 N-hop 이웃 그래프(상한 적용).

기존 `projectos_get_hot_context`(persona/hubs/gaps/stats 요약)와 역할이 겹치지 않는다.
graph_summary는 hot_context와 중복되어 **비범위**로 둔다.

## 비목표 (YAGNI)

- `projectos_get_graph_summary` (hot_context와 중복).
- 가중치 기반 노드 랭킹, shortest-path/경로 탐색.
- graph mutation(이 도구들은 전부 read-only).
- evidence를 항상 포함하는 동작(기본은 저토큰, opt-in으로만 발췌).
- simulation graph delta/report section 도구(별도 후속 후보).

## 아키텍처

순수 결정적 코어 + 얇은 async MCP 래퍼로 분리한다. 기존 autoresearch/graph_review와 동일한 패턴.

- **신규 서비스 모듈** `app/services/graph_context.py`
  - 순수·동기·결정적. 파일 I/O 없음, 임베딩 호출 없음.
  - 입력은 이미 로드된 `nx.DiGraph`(+ node_context evidence는 사전 조회된 리스트를 주입받음).
  - 단위 테스트가 임베딩/파일 없이 가능.
- **MCP 래퍼** `app/mcp_tools.py`
  - graph.json 로드(`_load_graph`), evidence 필요 시 async `hybrid_search`만 담당.
  - 결과를 `structuredContent` + 짧은 summary text로 반환.

### 렌더 그래프 정책

hot_context/vault_reconcile와 동일하게 **렌더 그래프**(`vault_reconcile._rendered_graph`로
demote+details 적용본)를 기본 입력으로 사용한다. 이유: Category/무명 synthetic 노드는
vault 페이지가 없고 사용자가 보는 그래프와 불일치하므로, 조회 결과도 렌더 그래프 기준이어야
Claude가 보는 노드와 일치한다. demote 노드/Category 노드는 결과에서 제외되거나 합성 형태로만 노출된다.

## 컴포넌트

### 1. `resolve_node_ref(graph, ref) -> dict` (공통)

노드 지정은 **name 우선 + id 폴백**. 불투명한 id(예: `a0dfcffa`) 직접 사용을 강제하지 않는다.

해상도 우선순위:
1. 정확 node id 일치.
2. 정확 name 일치(공백 trim).
3. 대소문자 무시 name 일치.
4. substring name 부분 일치 → 후보 목록.

반환:
```
{
  "node_id": str | None,   # 단일 확정 시
  "candidates": [{"id": str, "name": str, "type": str}],  # 0개=미발견, 2+=모호
  "ambiguous": bool        # 2+ 후보일 때 true
}
```
단일 확정이면 `node_id` 설정, `candidates`는 그 1개. 미발견/모호는 `node_id=None`이고
호출 측이 후보를 사용자/Claude에게 되돌려 재지정하게 한다(에러 아님).

### 2. `build_node_context(graph, node_id, evidence=None) -> dict`

```
{
  "node": {"id", "type", "name", "description", "source_files": [..]},
  "edges_out": [{"relation", "neighbor_id", "neighbor_name", "neighbor_type"}],
  "edges_in":  [{"relation", "neighbor_id", "neighbor_name", "neighbor_type"}],
  "degree": int,                  # in+out
  "source_file_count": int,
  "evidence": [{"label", "text"}] # evidence 인자가 주어졌을 때만 포함
}
```
- `evidence`는 사전 조회된 `[{"label","text"}]` 리스트(미주입 시 키 생략).
- evidence label 형식은 QueryAgent와 동일(`[file#chunk p.N char:off]`)해 citation 라벨과 호환.

### 3. `build_subgraph(graph, seed_ids, depth=1, max_nodes=30) -> dict`

seed에서 무방향 BFS로 depth-hop 이웃 수집. `max_nodes` 도달 시 확장 중단하고 `truncated=true`.

```
{
  "nodes": [{"id", "type", "name", "source_files": [..]}],
  "edges": [{"source", "target", "relation"}],   # source/target = neighbor name
  "node_count": int,
  "truncated": bool
}
```
- 수집된 노드 집합 내부 간선만 포함(경계 밖으로 나가는 간선 제외).
- seed가 0개로 resolve되면 빈 nodes/edges 반환.

## MCP 도구 (async 래퍼)

### `projectos_get_node_context`
입력: `project_id`(required), `node`(required, name 우선/id 폴백),
`include_evidence`(default false), `max_evidence`(default 3).

동작:
1. 렌더 그래프 로드. `resolve_node_ref`.
2. 미해결/모호 → `{resolved:false, candidates, ambiguous}` 반환(isError 아님).
3. 해결 → `build_node_context`.
4. `include_evidence=true`면 chunks.json 로드, `hybrid_search(query=name+" "+description, kind="chunks", top_n=max_evidence)`로
   top-k 청크를 라벨과 함께 `evidence`로 주입. 임베딩/인덱스 없으면 키워드 폴백(기존 불변식).
5. `structuredContent`로 반환, summary text는 `"<name> (<type>): out N, in M, sources K"`.

### `projectos_get_subgraph`
입력: `project_id`(required), `nodes`(required, name/id 리스트),
`depth`(default 1), `max_nodes`(default 30).

동작:
1. 렌더 그래프 로드. 각 seed `resolve_node_ref`. **단일 확정된 seed만** BFS seed로 사용하고, 모호하거나 미발견인 seed는 원본 ref 문자열을 `seeds_unresolved`에 기록한다(BFS에 사용하지 않음).
2. `build_subgraph(graph, resolved_seed_ids, depth, max_nodes)`.
3. `structuredContent`로 `{..., seeds_resolved, seeds_unresolved}` 반환. summary text는 `"<node_count> nodes, <edge_count> edges (truncated=<bool>)"`.

두 도구 모두 **웹 검색/LLM 호출/graph mutation 없음**.

## 데이터 흐름

```
Claude Desktop
  → projectos_get_node_context(project_id, node, include_evidence?)
    → _load_graph + _rendered_graph
    → resolve_node_ref
    → (opt) hybrid_search over chunks  ── 폴백: 키워드 전용
    → build_node_context
    → structuredContent

  → projectos_get_subgraph(project_id, nodes, depth, max_nodes)
    → _load_graph + _rendered_graph
    → resolve_node_ref (per seed)
    → build_subgraph (bounded BFS)
    → structuredContent
```

## 에러 처리 / 불변식

- 노드 미해결은 **에러가 아니라 candidates 반환** — Claude가 재지정하도록 유도.
- evidence 경로는 기존 hybrid_search 폴백 불변식을 그대로 상속(인덱스 없음/임베딩 실패 → 키워드 전용, 그래도 실패 시 evidence 빈 리스트).
- graph.json 없음/손상 → MCP `CallToolResult.isError=true` + 메시지.
- 순수 코어 함수는 예외를 던지지 않고 빈 구조를 반환(빈 graph, 빈 seed 등).

## 테스트 (TDD)

### `tests/test_services/test_graph_context.py`
- resolve: 정확 id / 정확 name / 대소문자 무시 / substring 다수(ambiguous) / 미발견.
- build_node_context: edges_out/in 방향 정확, degree 합산, source_files 보존, evidence 주입 시 포함·미주입 시 키 생략.
- build_subgraph: depth=1 이웃, depth=2 확장, max_nodes 상한 → truncated=true, 경계 밖 간선 제외, 빈 seed.
- 렌더 그래프 일관성: Category/demote 노드 제외 동작.

### `tests/test_api/test_mcp_api.py`
- tools/list에 `projectos_get_node_context`, `projectos_get_subgraph` 노출.
- node_context: 기본(저토큰, evidence 없음) / include_evidence=true(라벨 포함) / 모호 후보 반환 / 미발견.
- subgraph: 기본 이웃 / depth 증가 / max_nodes truncated / seed 일부 미해결(seeds_unresolved).

## 검증

- `python3 -m pytest tests/test_services/test_graph_context.py tests/test_api/test_mcp_api.py -q`
- `python3 -m pytest tests/ -q` (전체 회귀, 현재 baseline 437 passed)

## 미커밋 정책

`mcp_tools.py`/`test_mcp_api.py`에 사용자 WIP가 섞여 있으므로, 신규 서비스 모듈
`graph_context.py`와 그 단위 테스트는 깨끗이 커밋하고, MCP 래퍼 배선은 기존 #1~#5 정책대로
사용자 WIP과 함께 커밋되도록 working tree에 남길 수 있다(핸드오프에 명시).
