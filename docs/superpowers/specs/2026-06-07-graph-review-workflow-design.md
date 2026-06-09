# Graph Review Workflow — `projectos-review-graph` 설계

> #5 autoresearch 이후 후속 작업. Claude Desktop이 전체 graph를 무작정 읽기 전에, backend가 검수 workflow와 후보/evidence를 작게 묶어 전달한다.

**목표:** graph 품질 검수를 바로 targeted 방식으로 고정하지 않고, `A. full Claude review`와 `B. deterministic pre-filter + targeted Claude review`를 같은 기준으로 비교할 수 있는 read-only workflow payload를 제공한다.

**범위 결정:**
- 1차 구현은 deterministic workflow builder + MCP read tool.
- 기존 `graph_health`와 `autoresearch` 후보를 재사용한다.
- 웹 검색, LLM 검수, graph patch 생성/적용, simulation 결과 처리는 비범위.

---

## 배경

handoff에는 graph 품질 검수 방식을 비교해야 한다는 판단이 남아 있다.

- **A. Claude full/review-heavy baseline** — Claude가 graph/index/trace를 넓게 보고 직접 검수한다.
- **B. Backend deterministic pre-filter + Claude targeted review** — backend가 duplicate/noisy/isolated/missing-evidence 후보를 추리고 Claude는 후보와 source evidence 중심으로 판단한다.

#5 `projectos_get_research_candidates`는 targeted 후보를 만들지만, Claude Desktop이 어떤 순서와 기준으로 검수해야 하는지까지는 정의하지 않는다.

## 접근 방식

신규 서비스 `app/services/graph_review.py`가 graph, health, candidates를 받아 작은 workflow payload를 만든다.

```python
def build_graph_review_workflow(
    graph: nx.Graph,
    candidates: Iterable[dict] | None = None,
    health: dict | None = None,
    *,
    project_id: str | None = None,
    max_candidates: int = 20,
) -> dict:
```

반환 구조:

```python
{
    "project_id": "project-id",
    "summary": {
        "node_count": 42,
        "edge_count": 81,
        "candidate_count": 12,
        "health": {"isolated_count": 3, "...": 0},
    },
    "modes": [
        {"id": "full_review", "purpose": "...", "inputs": [...], "expected_cost": "high"},
        {"id": "targeted_review", "purpose": "...", "inputs": [...], "expected_cost": "low"},
    ],
    "evaluation_metrics": [...],
    "targeted_candidates": [...],
    "checklist": [...],
    "token_saving_guidance": [...],
    "next_steps": [...],
}
```

## Workflow Semantics

`full_review`는 품질 기준선을 만들기 위한 mode다. 전체 graph를 직접 반환하지 않고, Claude Desktop에게 어떤 artifact를 별도 요청해야 하는지 알려준다.

`targeted_review`는 현재 기본 권장 mode다. backend가 계산한 후보를 우선순위대로 보며 duplicate, unsupported node, missing relation, weak component를 검수한다.

두 mode 모두 read-only이며, 수정은 별도 사용자 승인 뒤 `projectos_apply_graph_patch`로만 진행한다.

## 평가 기준

workflow payload는 다음 metric id를 고정한다.

- `duplicate_node_detection`
- `wrong_entity_type_detection`
- `missing_relation_detection`
- `unsupported_claim_detection`
- `noisy_entity_removal`
- `source_evidence_accuracy`
- `graph_health_delta`
- `claude_token_usage`
- `elapsed_time`
- `user_confirmation_count`

## MCP 확장

`projectos_review_graph(project_id, max_candidates=20)` 도구를 추가한다.

동작:
- `_require_project(project_id)`
- graph load
- `_load_chunks(project_id)`
- `run_health_check(graph, vault_path=...)`
- `generate_autoresearch_candidates(...)`
- `build_graph_review_workflow(...)`
- `_text_result(summary_text, payload)`

텍스트 summary는 후보 수와 권장 mode만 짧게 보여준다. 실제 검수 정보는 structuredContent로 전달한다.

## 안전 원칙

- read-only. graph/vault/files를 수정하지 않는다.
- full graph dump를 기본 반환하지 않는다.
- 후보가 없더라도 workflow/checklist/metrics는 반환한다.
- hallucinated citation이나 unsupported patch를 자동 수용하지 않는다.
- duplicate 후보는 research가 아니라 merge/delete 검수 후보로 취급한다.

## 테스트

`tests/test_services/test_graph_review.py`:
- deterministic output.
- 입력 graph를 mutate하지 않는다.
- candidate summary, modes, metrics, checklist, token guidance 포함.
- candidate 정렬/제한이 priority와 id 기준으로 안정적.

`tests/test_api/test_mcp_api.py`:
- tools/list에 `projectos_review_graph` 포함.
- tool call이 graph/health/autoresearch/workflow structuredContent를 반환.

## 비범위

- Claude Desktop prompt file 생성.
- live web/browser search.
- graph patch 자동 생성/적용.
- simulation result schema/UI 변경.
