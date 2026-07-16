# Citation Validator — QueryAgent 후처리 검증 설계

> #4 출처 인용 강제화 후속. 프롬프트에 citation을 요구하는 것에서 끝내지 않고, 답변이 제공된 출처 라벨만 사용했는지 결정적으로 검사한다.

**목표:** QueryAgent/RAG 답변의 citation 품질을 read-only report로 반환한다. 모델 답변을 자동 수정하지 않고, unknown citation과 citation 누락 후보를 사용자/Claude Desktop이 확인할 수 있게 한다.

**범위 결정:**
- 1차 구현은 deterministic citation validator + MCP query structured report.
- Chat SSE token stream은 호환성 때문에 그대로 유지한다.
- LLM fact-check, 답변 자동 재작성, graph patch/simulation citation enforcement는 비범위.

---

## 접근 방식

신규 서비스 `app/services/citation_validator.py`가 답변과 허용 label set을 받아 report를 만든다.

```python
def validate_citations(
    answer: str,
    allowed_labels: Iterable[str],
    *,
    require_citation: bool = True,
) -> dict:
```

반환:

```python
{
    "valid": false,
    "used_labels": ["[cv.pdf]"],
    "unknown_labels": ["[made-up.pdf]"],
    "missing_citation_sentences": ["Python을 사용합니다."],
    "unsupported_count": 1,
    "summary": {
        "allowed_label_count": 3,
        "used_label_count": 1,
        "unknown_label_count": 1,
        "missing_citation_count": 1,
        "unsupported_count": 1,
    },
}
```

`출처 불명`은 unsupported marker로 인정한다. 사실 주장에 citation이 없지만 `출처 불명`이 있으면 missing citation으로 보지 않는다.

## Allowed Labels

QueryAgent는 이미 prompt에 다음 label을 렌더한다.

- chunk label: `[cv.pdf#id1 p.1 char:0]`
- node source label: `[cv.pdf]`
- unsupported marker: `출처 불명`

QueryAgent에 `collect_allowed_citation_labels(context, chunks, wiki_context=None)` 같은 helper를 추가해 prompt에 제공한 라벨과 같은 label set을 얻는다.

## MCP 통합

`projectos_query_career_graph`는 답변을 내부에서 문자열로 모으므로 structuredContent에 citation report를 추가한다.

```python
{"answer": answer, "citation_report": report}
```

허용 label은 QueryAgent의 검색/프롬프트 컨텍스트와 동일하게 산출한다. 답변 본문은 수정하지 않는다.

## 안전 원칙

- read-only.
- validator 실패가 답변 생성을 막지 않는다.
- unknown label은 report로 노출한다.
- citation 없는 문장은 heuristic 후보일 뿐 fact verdict가 아니다.

## 테스트

`tests/test_services/test_citation_validator.py`:
- allowed labels only.
- unknown label.
- missing citation sentence.
- `출처 불명` marker 허용.
- deterministic output.
- empty answer.

`tests/test_agents/test_query_agent.py`:
- allowed citation labels helper가 node/chunk/wiki labels를 수집한다.

`tests/test_api/test_mcp_api.py`:
- `projectos_query_career_graph` structuredContent에 citation_report 포함.

## 비범위

- 스트리밍 SSE의 마지막 이벤트에 citation report 추가.
- LLM 기반 fact-check.
- 답변 자동 rewrite/retry.
- simulation/report/graph patch citation enforcement.
