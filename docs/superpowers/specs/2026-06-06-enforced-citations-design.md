# Enforced Citations — QueryAgent 출처 인용 강제화 설계

> 개선 항목 #4. QueryAgent 답변이 원본 문서와 그래프 provenance를 실제로 인용할 수 있도록 컨텍스트에 출처 라벨을 포함하고, 답변 규칙을 "권유"에서 "필수"로 강화한다.

**목표:** ProjectOS RAG 답변에서 사실 주장마다 사용 가능한 출처 라벨을 붙이게 한다. 모델이 인용할 근거가 없으면 임의로 꾸미지 않고 `출처 불명`을 명시하게 한다.

**범위 결정:**
- 대상: `QueryAgent`의 graph/chunk/wiki 기반 답변 프롬프트.
- 데이터: `TextChunk.source_file`, `chunk_id`, `page_num`, `char_offset`, graph node `source_files`.
- 방식: retrieval 결과를 provenance 포함 구조로 유지하고, `_build_prompt`가 출처 라벨을 렌더한다.
- 비범위: 응답 후 citation parser/validator, graph patch/simulation report citation 강제화, vault `Sources` 역파싱 강화.

---

## 배경

현재 `QueryAgent._build_prompt`는 "가능하면 ... 출처 파일/청크를 함께 언급하세요"라고 권유만 한다. 더 큰 문제는 `_find_relevant_chunks`가 `TextChunk`에서 본문만 추출해 반환한다는 점이다. 모델은 프롬프트에서 `source_file`, `chunk_id`, `page_num`을 볼 수 없으므로 인용을 정확히 할 수 없다.

이미 존재하는 provenance:
- `TextChunk`: `chunk_id`, `source_file`, `file_type`, `page_num`, `char_offset`.
- graph node: `source_files` 리스트.
- Obsidian page: `## Sources` 섹션.

병목은 provenance가 검색 결과에서 프롬프트로 전달되지 않는 것이다.

## 접근 방식

**선택: QueryAgent 컨텍스트 라벨링 + 강제 프롬프트.**

`_find_relevant_chunks`는 기존처럼 hybrid retrieval로 top 3 청크를 고르되, 반환값에 원본 라벨을 포함한다. `_search_graph`는 matched node에 `source_files`를 보존한다. `_build_prompt`는 다음 형식으로 렌더한다.

```text
## 관련 노드
- [Skill] Python: ...
  출처: [cv.pdf], [readme.md]

## 원본 문서 발췌
### [cv.pdf#id1 p.1 char:0]
Yang Pilseong은 Python을 주로 사용합니다.
```

답변 지시는 다음으로 강화한다.
- 사실 주장에는 반드시 제공된 출처 라벨을 붙인다.
- 같은 문단에서 여러 근거가 쓰이면 여러 라벨을 붙인다.
- 컨텍스트에 근거가 없는 내용은 추측하지 말고 `출처 불명`으로 표시한다.
- 출처 라벨은 프롬프트에 제공된 라벨만 사용한다.

탈락:
- **응답 후 검증기** — 유효한 label set과 정규식 검사는 가능하지만, 스트리밍 응답 경로에 후처리 버퍼링을 추가한다. 이번 목표는 citation 가능성과 프롬프트 강제화까지로 제한한다.
- **LLM 재검수 패스** — 비용과 지연 증가. `#5 autoresearch`나 graph review workflow에서 별도 다룰 수 있다.

## 데이터 구조

신규 public dataclass 없이 QueryAgent 내부 dict로 충분하다.

```python
{
    "label": "cv.pdf#id1 p.1 char:0",
    "source_file": "cv.pdf",
    "chunk_id": "id1",
    "page_num": 1,
    "char_offset": 0,
    "text": "...",
}
```

node:

```python
{
    "id": "Skill:Python",
    "type": "Skill",
    "name": "Python",
    "description": "...",
    "source_files": ["cv.pdf"],
}
```

라벨 규칙:
- 항상 `source_file#chunk_id`.
- `page_num`이 있으면 `p.{page_num}` 추가.
- `char_offset`이 `None`이 아니면 `char:{char_offset}` 추가.
- node source는 파일 단위라 `[source_file]` 형태.

## 테스트

`tests/test_agents/test_query_agent.py`:
- `_search_graph`가 matched node의 `source_files`를 반환한다.
- `_find_relevant_chunks`가 본문뿐 아니라 source label/source_file/chunk_id/page/offset을 포함한다.
- `_build_prompt`가 chunk label과 node source를 렌더한다.
- `_build_prompt` 마지막 지시가 인용 필수와 `출처 불명` 정책을 포함한다.

`tests/test_agents/test_query_agent_hybrid.py`:
- async hybrid retrieval 경로가 유지되고, 기존 substring assertions가 라벨 구조에서도 통과한다.

## 호환성

내부 테스트가 `_find_relevant_chunks` 반환값에 대해 `"Python" in c`처럼 문자열 포함 검사를 한다. dict 반환으로 바꾸면 깨질 수 있으므로 테스트와 구현을 함께 갱신한다. 외부 API는 `QueryAgent.stream()`이 문자열 token만 방출하므로 변경 없다.

## 비범위

- citation hallucination 후처리 차단.
- wiki page `Sources` 섹션 parsing/normalization.
- MCP structured response에 used citations 별도 필드 추가.
- simulation/report/graph patch citation enforcement.
