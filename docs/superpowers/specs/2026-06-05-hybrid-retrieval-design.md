# Hybrid Retrieval for QueryAgent — Design

**Date**: 2026-06-05
**Status**: Approved (구현 전)
**참고 대상**: [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) — sparse(BM25) + dense + cosine rerank, local-first
**개선 항목**: claude-obsidian 비교 개선점 #1 (검색 품질)

---

## 0. 한 줄 요약

QueryAgent의 검색을 순수 키워드/부분문자열 매칭에서 **하이브리드(키워드 sparse + BGE-M3 dense, RRF 융합)**로 업그레이드한다. 임베딩은 빌드 시 계산해 디스크에 캐시한다. 임베딩 인프라(`EmbeddingClient`)가 없거나 실패하면 현재 키워드 경로로 자동 폴백한다.

---

## 1. 배경 / 문제

`app/agents/query_agent.py`의 `_search_graph`(노드)와 `_find_relevant_chunks`(청크)는 substring 매칭만 사용한다.

- 동의어·패러프레이즈·의미 유사도를 못 잡는다 (예: "딥러닝" 질문이 "neural network" 청크를 못 찾음).
- `CLAUDE.md`에 기록된 한국어 조사 문제("Python을"/"Python이")를 substring hack으로 우회 중 — 근본 해결 아님.
- `EmbeddingClient`(BGE-M3, OpenAI 호환 endpoint)가 이미 있고 `semantic_dedup.py`/`entity_resolver.py`에서만 쓰인다. **쿼리 경로에서 놀고 있다.**

claude-obsidian은 sparse + dense + cosine rerank 하이브리드 검색을 핵심 차별점으로 둔다. 같은 정신을 ProjectOS 스택(substring=sparse, BGE-M3=dense)으로 흡수한다.

---

## 2. 범위

**적용 corpus**: 청크 + 그래프 노드 (사용자 결정).
- vault 페이지는 매칭된 노드를 통해 따라오므로 별도 임베딩하지 않는다 (현 `_find_relevant_pages` 동작 유지).

**비목표 (YAGNI)**:
- vault 페이지 임베딩, lazy/query-time 임베딩 캐시.
- BM25 정식 구현(현 substring 가중치 점수를 sparse 성분으로 충분히 사용).
- 외부 rerank API egress.
- 로컬 모델 fine-tune.

---

## 3. 아키텍처

신규 모듈 2개 + QueryAgent 연결.

### 3.1 `app/services/retrieval_index.py` — 빌드 시 임베딩 캐시

저장 위치: `projects/<id>/embeddings/`
- `chunks.npy` (float16, shape `[N, dim]`) + `chunks_meta.json` (`{"ids": [...], "model": "...", "dim": int}`)
- `nodes.npy` (float16) + `nodes_meta.json` (`{"ids": [...], "model": "...", "dim": int}`)

함수:
- `async build_chunk_index(project_id) -> dict | None`
  - `chunks.json` 로드 → `chunk.text` 임베딩(배치) → `chunks.npy`/`chunks_meta.json` 저장. id = `chunk_id`.
- `async build_node_index(project_id) -> dict | None`
  - `graph.json` 로드 → 노드별 `"{name}: {description}"` 임베딩 → `nodes.npy`/`nodes_meta.json` 저장. id = node_id.
- `load_index(project_id, kind) -> tuple[np.ndarray, list[str]] | None`
  - `kind ∈ {"chunks","nodes"}`. meta의 `model`/`dim`이 현재 `config.EMBEDDING_MODEL`과 다르면 `None` 반환(stale 무효화).
- 공통 정책: `config.EMBEDDING_BASE_URL`이 비어 있으면 즉시 `None` 반환(인덱스 미생성). 임베딩 호출 실패는 `logger.warning` 후 `None`. **빌드는 절대 실패시키지 않는다**(best-effort, digest/watcher trace와 동일 패턴).

저장 용량: BGE-M3 1024-d × float16 = 2KB/벡터. 청크 1,000개 ≈ 2MB. 무시 가능.

### 3.2 `app/utils/hybrid_retrieval.py` — 검색

순수 함수 + 얇은 async 진입점.

- `def keyword_scores(query, items) -> dict[id, float]`
  - 현재 `_search_graph`/`_find_relevant_chunks`의 가중치 substring 로직을 추출·재사용(노드는 name×2 + desc×1, 청크는 substring 카운트).
- `def rrf_fuse(rankings: list[list[id]], k: int = 60) -> list[id]`
  - 각 ranking(키워드 순위, dense cosine 순위)에 대해 `score[id] += 1/(k + rank)`. 내림차순 정렬된 id 리스트 반환.
- `async hybrid_search(query, project_id, kind, items, top_n) -> list[id]`
  - `items`: `{id: text}` (호출자가 노드/청크에서 구성).
  - 키워드 순위 계산.
  - `load_index(project_id, kind)` 성공 시: 질문 1회 임베딩 → cosine(정규화된 행렬곱) → dense 순위. RRF 융합.
  - 인덱스 없거나 임베딩 실패: **키워드 순위만** 반환(현재 동작과 동일).
  - 항상 `top_n` 절단.

### 3.3 QueryAgent 연결

`query_agent.py`:
- `_search_graph`: 노드 `{id: "{name}: {desc}"}` 구성 → `hybrid_search(..., kind="nodes")`로 top 노드 id 획득 → 기존 edge 수집·BFS 확장·dict 구성은 그대로.
- `_find_relevant_chunks`: 청크 `{chunk_id: text}` 구성 → `hybrid_search(..., kind="chunks")` → top 3 텍스트.
- `stream()`이 async라 hybrid_search await 가능. 프롬프트 빌드/`_load_wiki_context`는 변경 없음.

### 3.4 파이프라인 통합 (인덱스 빌드 호출 지점)

- `app/api/projects.py` 파싱 태스크: `chunks.json` 저장 직후 `await build_chunk_index(project_id)` (best-effort).
- `app/api/graph.py` `_run_graph`: `graph.json` 저장 직후 `await build_node_index(project_id)` (best-effort). 청크 인덱스도 여기서 재빌드(증분/워처 재파싱 반영).
- 둘 다 try/except로 감싸 실패해도 파이프라인 진행.

---

## 4. 데이터 흐름

```
parse → chunks.json 저장 → build_chunk_index → chunks.npy
graph build → graph.json 저장 → build_node_index + build_chunk_index → nodes.npy/chunks.npy
query → hybrid_search(질문 임베딩 1회) → load_index → keyword순위 + cosine순위 → RRF → top-k → 프롬프트
```

---

## 5. 에러 처리 / 폴백

| 상황 | 동작 |
|---|---|
| `EMBEDDING_BASE_URL` 미설정 | 인덱스 미생성, 검색은 키워드만 (현 동작) |
| 임베딩 호출 실패(빌드) | warning, 인덱스 미생성 |
| 임베딩 호출 실패(쿼리) | warning, 키워드 순위만 |
| 인덱스 stale(모델 변경) | `load_index`가 None → 키워드만, 다음 빌드에서 갱신 |
| `.npy`/meta 불일치·손상 | None 취급, 키워드 폴백 |

핵심 불변식: **하이브리드 실패가 쿼리·빌드를 깨뜨리지 않는다.**

---

## 6. 테스트 (TDD)

`tests/test_utils/test_hybrid_retrieval.py`:
- `rrf_fuse`: 두 ranking 융합 순서, 한쪽에만 등장하는 id 처리, 동점.
- `keyword_scores`: name 가중치 > desc, 매칭 없음 0.
- `hybrid_search`: 인덱스 없을 때 키워드 순위와 동일. stub 임베딩 주입 시 dense가 순위에 반영.

`tests/test_services/test_retrieval_index.py`:
- `build_chunk_index`/`build_node_index`: `.npy`+meta 저장, id 정합, `EMBEDDING_BASE_URL` 빈값이면 None·파일 미생성.
- `load_index`: 모델 변경 meta면 None.

`tests/test_agents/test_query_agent.py` (없으면 신규):
- 인덱스 존재 시 hybrid 경로, 부재 시 키워드 폴백. `EmbeddingClient`는 mock(고정 벡터)으로 결정적 테스트.

전체 회귀: `python3 -m pytest src/backend/tests -q` 그린 유지.

---

## 7. 영향 / 변경 파일

- 신규: `app/services/retrieval_index.py`, `app/utils/hybrid_retrieval.py`, 테스트 3종.
- 수정: `app/agents/query_agent.py`(검색 2함수), `app/api/projects.py`(파싱 후 인덱스), `app/api/graph.py`(`_run_graph` 후 인덱스).
- config 추가 없음(`EMBEDDING_BASE_URL`/`EMBEDDING_MODEL` 재사용). 신규 외부 의존 없음(numpy 기존 사용).

---

## 8. 리스크

- **임베딩 endpoint 미가동 환경**: 폴백으로 기능 저하 없이 동작(현 수준 유지). 개선은 endpoint 있을 때만 발현 — 의도된 graceful degradation.
- **증분 빌드 후 인덱스 불일치**: `_run_graph`에서 청크/노드 인덱스를 항상 재빌드해 정합 유지.
- **대용량 corpus 임베딩 시간**: 빌드 시 1회 배치, 개인 규모에서 수용 가능. 쿼리는 질문 1벡터만 임베딩.
