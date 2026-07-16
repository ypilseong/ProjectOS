# Citation Enforcement — 재생성 루프 설계

> citation-validator 후속. validator는 답변의 citation 품질을 read-only report로만 반환했다(`답변 자동 rewrite/retry`는 명시적 비범위). 이번 단계는 검증 실패 시 LLM에 구체적 피드백을 주고 재생성하여 citation 규칙을 실제로 강제한다.

**목표:** MCP 비스트리밍 질의 경로에서 답변이 허용된 출처 라벨만 사용하고 사실 주장마다 인용하도록, 검증 실패 시 자동 재생성으로 품질을 끌어올린다.

**범위 결정 (사용자 승인):**
- enforcement 전략: **재생성 루프** — 검증 실패 시 구체적 피드백(unknown label 제거, 미인용 문장 수정)을 주고 최대 N회 재생성. 최종 답변 + report + attempts 반환.
- 적용 경로: **MCP 비스트리밍만** (`projectos_query_career_graph`). 재사용 가능한 `QueryAgent` 메서드로 구현. SSE 스트리밍 채팅(`QueryAgent.stream`)은 호환성 위해 그대로 유지.
- 비범위: SSE 스트리밍 enforcement, 결정적 strip, LLM fact-check, simulation/graph patch citation 강제화.

---

## 접근 방식

신규 메서드 `QueryAgent.answer_with_enforced_citations(...)`:

1. 기존 helper(`_search_graph`, `_find_relevant_chunks`, `_load_wiki_context`, `_build_prompt`, `collect_allowed_citation_labels`)로 컨텍스트와 base prompt, allowed label set을 **한 번** 산출.
2. `_generate(prompt)`로 답변 생성 (비스트리밍, `self._llm.chat`).
3. `validate_citations(answer, allowed_labels)`로 검증.
4. `valid`이거나 시도 횟수 소진 시 종료. 아니면 `_build_citation_correction_prompt(...)`로 교정 프롬프트를 만들어 재생성.
5. `{answer, citation_report, allowed_citation_labels, attempts}` 반환.

`_generate`는 테스트 seam이다 (기존 테스트가 `stream`을 클래스 레벨에서 patch하는 패턴과 동일하게 patch 가능).

`max_retries` 의미: `max_attempts = max(1, max_retries + 1)`. `max_retries=0`이면 1회 생성 + report만(기존 동작과 유사). 기본 `1`.

## 교정 프롬프트

base prompt 전체 + 다음 섹션을 덧붙인다.
- 이전 답변(규칙 위반) 원문.
- 문제 목록: unknown_labels 나열("제거/교체 또는 출처 불명"), missing_citation_sentences 상위 5개 나열("라벨 추가 또는 출처 불명").
- 허용된 라벨 목록.
- "허용된 라벨만 사용, 근거 없으면 출처 불명" 재지시.

## 데이터 구조

```python
{
    "answer": str,
    "citation_report": dict,          # validate_citations 최종 결과
    "allowed_citation_labels": list[str],
    "attempts": int,                  # 총 생성 횟수 (1 = 재생성 불필요)
}
```

## MCP 통합

`projectos_query_career_graph`를 새 메서드 호출로 교체한다. 인자 `max_citation_retries`(int, 0–3, 기본 1) 추가. structuredContent는 위 반환 dict + `project_id`. 본문 텍스트는 최종 `answer`.

## 테스트

`tests/test_agents/test_query_agent.py`:
- 유효 답변이면 `attempts == 1`, `_generate` 1회 호출.
- 첫 답변 invalid(unknown label) → 둘째 valid면 `attempts == 2`, 최종 valid, 답변은 교정본.
- 재시도 소진 후에도 invalid면 마지막 답변 + invalid report + `attempts == max_retries+1`.
- `_build_citation_correction_prompt`가 base/이전답변/unknown label/미인용 문장/허용 라벨을 포함.

`tests/test_api/test_mcp_api.py`:
- 기존 report 테스트를 `_generate` mock으로 갱신, `attempts` 포함 확인.
- 신규: invalid→valid 재생성으로 최종 valid + `attempts == 2`.

## 안전 원칙

- validator는 read-only 유지. enforcement는 답변 생성 단계에서만 재시도.
- 재생성 실패해도 답변 생성을 막지 않고 마지막 답변 + invalid report 반환(차단 아님).
- 결정적 검증(validate_citations) 재사용. 재생성만 비결정적(LLM).

## 비범위

- SSE 스트리밍 enforcement / 후처리 버퍼링.
- 결정적 unknown-label strip.
- LLM 기반 fact-check, 답변 차단(block/refuse).
- simulation/report/graph patch citation enforcement.
