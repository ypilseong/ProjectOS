# Graph Review Comparison Experiment Runbook

> 목적: graph 품질 검수 방식을 바로 targeted review로 고정하지 않고, `A. full Claude review`와 `B. deterministic pre-filter + targeted Claude review`를 같은 기준으로 비교해 운영 전환 여부를 결정한다.

**상태:** 운영 절차 문서. 코드/MCP/Claude Desktop 자동화 추가는 비범위.

**연결 workflow:** `projectos_review_graph(project_id, max_candidates=8, min_degree=1, component_size_threshold=3)`가 반환하는 `projectos-review-graph` structured payload를 B 모드의 표준 입력으로 사용한다.

---

## 목적

이 실험은 Claude Desktop을 graph 품질 검수자로 사용할 때 다음 두 방식의 품질과 비용을 비교한다.

- A 모드가 만든 검수 결과를 품질 기준선으로 삼는다.
- B 모드가 A 대비 주요 graph 품질 이슈를 얼마나 놓치지 않는지 확인한다.
- B 모드가 Claude token/context 사용량과 검수 시간을 충분히 줄이는지 확인한다.
- 비교 결과가 전환 기준을 만족할 때만 targeted review를 기본 운영 방식으로 채택한다.

## 대상 프로젝트 선정

한 번의 실험 batch는 3~5개 프로젝트로 구성한다. 각 프로젝트는 이미 graph와 chunks가 생성되어 있고, 가능한 경우 vault도 최신이어야 한다.

선정 기준:

- **소형 프로젝트:** 30개 이하 node. full review가 현실적으로 가능한 기준선 샘플.
- **중형 프로젝트:** 31~150개 node. targeted review의 token 절감 효과를 확인할 주 샘플.
- **문제 신호가 있는 프로젝트:** isolated, duplicate, missing source, weak component 후보가 1개 이상 있는 프로젝트.
- **문제 신호가 적은 프로젝트:** candidate가 없거나 적은 프로젝트. B 모드가 빈 후보 상황에서 과도하게 안심하지 않는지 확인.

제외 기준:

- graph/chunks 생성이 실패했거나 `projectos_review_graph`를 호출할 수 없는 프로젝트.
- 사용자가 아직 ingest/parse 결과를 승인하지 않은 프로젝트.
- Simulation/Inbox/Claude 검수 방향 코드 수정이 필요한 프로젝트. 이 실험은 운영 비교만 수행한다.

## A/B 모드 정의

### A. Full Claude Review

Claude Desktop이 graph, source index, 필요한 source snippets를 넓게 보고 직접 품질 이슈를 찾는 baseline이다.

운영 원칙:

- graph 전체 또는 큰 subgraph를 볼 수 있으나, source evidence 없는 판단은 accepted issue로 세지 않는다.
- Claude가 발견한 이슈는 duplicate, wrong type, missing relation, unsupported claim, noisy/generic entity, source mismatch로 분류한다.
- 실제 graph 수정은 하지 않는다. 결과는 score sheet와 proposed decisions로만 남긴다.

장점:

- deterministic pre-filter가 놓치는 이슈를 찾을 가능성이 높다.
- 품질 기준선으로 적합하다.

위험:

- token 사용량이 높다.
- 후보 선정이 재현 가능하지 않을 수 있다.
- 큰 프로젝트에서는 full context를 한 번에 넣기 어렵다.

### B. Deterministic Pre-filter + Targeted Claude Review

ProjectOS backend가 deterministic하게 후보를 만들고, Claude Desktop은 후보와 evidence 중심으로 최종 판단한다.

표준 입력은 `projectos_review_graph` payload다.

사용할 payload 필드:

- `macro`: `projectos-review-graph`인지 확인.
- `read_only`: `true`인지 확인.
- `inputs`: graph/chunk/candidate 요약.
- `mode_comparison`: A/B mode 정의와 권장 mode.
- `evaluation_metrics`: graph health와 candidate count 기준값.
- `targeted_review_candidates`: Claude가 검수할 ranked candidate queue.
- `recommended_checklist`: 후보 검수 체크리스트.
- `token_saving_guidance`: Claude에 보낼 필드와 생략할 필드.

운영 원칙:

- 먼저 `targeted_review_candidates`만 검수한다.
- 후보별로 source_files, suggested_query, review_focus를 확인한다.
- 필요한 경우에만 해당 node 주변 subgraph 또는 source snippet을 추가 요청한다.
- 실제 graph 수정은 하지 않는다. accepted decision은 별도 patch 초안으로만 기록한다.

## 입력 Artifact

공통 입력:

- `project_id`
- 현재 graph summary: node count, edge count, type counts.
- chunk/source availability: chunk count, source file labels.
- graph health summary: isolated, duplicate, component, missing source counts.
- 검수자가 사용한 Claude Desktop 대화 transcript 또는 요약 log.

A 모드 추가 입력:

- full graph JSON 또는 충분히 넓은 graph export.
- source index 또는 relevant chunks.
- 필요한 경우 high-degree nodes, weak components, duplicate-looking names 목록.

B 모드 추가 입력:

- `projectos_review_graph` structuredContent 전체.
- payload 내 `targeted_review_candidates`.
- 후보별 source snippets 또는 node neighborhood. 단, 후보 검수에 필요할 때만 추가한다.

## 출력 Artifact

프로젝트별로 다음 결과를 남긴다.

- `experiment_id`: 예. `graph-review-ab-2026-06-07-{project_id}`.
- `project_id`, 실행일, reviewer, mode.
- A/B별 issue list.
- A/B별 accepted issue count와 rejected issue count.
- 후보별 decision: `keep`, `merge`, `enrich`, `remove`, `ignore`, `needs_user`.
- evidence reference: source file, chunk label, graph node id, edge id.
- score sheet.
- token/time 측정값.
- 전환 판정: `adopt_targeted`, `repeat_experiment`, `keep_full_review_for_now`.

## 실행 순서

1. 대상 프로젝트를 선정하고 graph/chunks/vault가 최신인지 확인한다.
2. 각 프로젝트에서 `projectos_review_graph(project_id, max_candidates=8)`를 호출해 B 모드 payload를 확보한다.
3. payload의 `read_only=true`, `macro=projectos-review-graph`, `evaluation_metrics`, `targeted_review_candidates`를 확인한다.
4. A 모드를 먼저 실행한다. Claude에게 넓은 graph/source context를 제공하고 품질 이슈를 자유 탐색하게 한다.
5. A 모드 결과를 issue category와 evidence 기준으로 정리한다.
6. 새 Claude context 또는 명확히 분리된 transcript에서 B 모드를 실행한다. `token_saving_guidance.send_to_claude`에 있는 필드를 우선 제공한다.
7. B 모드는 `targeted_review_candidates` 순서대로 검수하고, 후보 밖 이슈 탐색은 별도 "spillover"로 기록한다.
8. 같은 rubric으로 A/B 결과를 채점한다.
9. A에서 발견하고 B에서 놓친 accepted issue를 `missed_by_targeted`로 표시한다.
10. B에서 발견하고 A에서 놓친 accepted issue를 `found_by_targeted_only`로 표시한다.
11. token 사용량, 소요 시간, 사용자 재확인 수를 기록한다.
12. 프로젝트별 판정과 batch 전체 판정을 작성한다.

## 평가 Rubric / Metrics

품질 metric:

- `duplicate_node_detection`: 실제 중복 node 또는 merge 후보를 발견했는가.
- `wrong_entity_type_detection`: entity type이 잘못된 node를 발견했는가.
- `missing_relation_detection`: 중요한 relation 누락을 발견했는가.
- `unsupported_claim_detection`: source evidence가 부족한 node/edge/description을 발견했는가.
- `noisy_entity_removal`: generic/noisy entity를 제거 또는 무시 후보로 식별했는가.
- `source_evidence_accuracy`: 판단에 사용한 source label이 실제 claim을 뒷받침하는가.

비용/운영 metric:

- `graph_health_delta_estimate`: accepted decisions 적용 시 isolated/missing source/duplicate count가 개선될 예상치.
- `claude_token_usage`: mode별 input+output token 또는 Claude Desktop 사용량 추정.
- `elapsed_time_minutes`: 준비부터 score sheet 완료까지 걸린 시간.
- `user_confirmation_count`: 사용자 확인이 필요했던 항목 수.
- `context_round_trips`: 추가 artifact 요청 횟수.

채점 기준:

- 0점: 발견하지 못함 또는 evidence 없음.
- 1점: 후보를 언급했지만 판단이 불완전함.
- 2점: evidence와 함께 올바르게 판단함.
- 3점: 올바른 판단과 실행 가능한 decision까지 제시함.

## 점수표 양식

프로젝트별 score sheet:

| Metric | A score | B score | B/A ratio | Evidence notes |
| --- | ---: | ---: | ---: | --- |
| duplicate_node_detection |  |  |  |  |
| wrong_entity_type_detection |  |  |  |  |
| missing_relation_detection |  |  |  |  |
| unsupported_claim_detection |  |  |  |  |
| noisy_entity_removal |  |  |  |  |
| source_evidence_accuracy |  |  |  |  |

운영 score sheet:

| Metric | A value | B value | Target | Notes |
| --- | ---: | ---: | ---: | --- |
| accepted_issue_count |  |  | B >= 90% of A |  |
| critical_missed_by_B |  |  | 0 |  |
| claude_token_usage |  |  | B <= 50% of A |  |
| elapsed_time_minutes |  |  | B <= 70% of A |  |
| user_confirmation_count |  |  | B <= A |  |
| context_round_trips |  |  | B <= A |  |

후보 decision sheet:

| Candidate id | Kind | Priority | Decision | Accepted | Evidence | Notes |
| --- | --- | ---: | --- | --- | --- | --- |
|  |  |  | keep/merge/enrich/remove/ignore/needs_user | yes/no |  |  |

## 전환 기준

batch 전체에서 다음 조건을 모두 만족하면 B 모드를 기본 운영 방식으로 채택한다.

- B의 accepted issue count가 A의 90% 이상이다.
- B가 놓친 critical issue가 0개다. Critical은 source evidence 오류, 중요한 relation 누락, 잘못된 merge/delete 판단이다.
- `source_evidence_accuracy`가 A와 같거나 더 높다.
- B의 Claude token 사용량이 A 대비 50% 이하이거나, 중형 이상 프로젝트에서 context round trip이 명확히 감소한다.
- B의 소요 시간이 A 대비 70% 이하이다.
- 사용자 재확인 수가 A보다 증가하지 않는다.

조건부 전환:

- duplicate/missing source는 B가 충분히 잡지만 missing relation을 반복적으로 놓치면, targeted review는 채택하되 node-context/subgraph 도구 설계를 다음 작업으로 올린다.
- candidate가 없는 프로젝트에서 B가 품질 이슈를 계속 놓치면, B 실행 후 high-degree node spot check를 필수 단계로 추가한다.

## 실패 / 중단 기준

다음 중 하나라도 발생하면 해당 프로젝트 실험을 중단하고 `repeat_experiment`로 표시한다.

- `projectos_review_graph` 호출 실패 또는 payload schema 불일치.
- `read_only`가 `true`가 아니거나, 실험 중 graph/vault 파일 수정이 필요한 상황.
- A 또는 B 어느 한쪽에 source evidence가 충분히 제공되지 않아 공정 비교가 불가능함.
- Claude context가 넘쳐 A 모드가 일관된 baseline을 만들 수 없음.
- B가 critical issue를 1개 이상 놓침.
- accepted decision의 evidence를 재검증할 수 없음.
- 사용자 승인 없이 patch 적용, graph mutation, Simulation/Inbox/Claude 검수 방향 코드 수정을 요구하는 흐름으로 번짐.

## 주의사항

Token/context:

- B 모드에서는 `token_saving_guidance.send_to_claude` 필드만 먼저 보낸다.
- full graph JSON, raw chunks, low-priority candidates는 기본 생략한다.
- 후보 검수 중 필요한 경우에만 source snippet 또는 local neighborhood를 추가한다.
- A와 B는 같은 Claude context에서 이어서 실행하지 않는 것이 좋다. A 결과가 B 판단에 새어 들어갈 수 있다.

Evidence:

- evidence 없는 이슈는 accepted issue로 세지 않는다.
- source label이 claim을 직접 뒷받침하지 않으면 `source_evidence_accuracy`에서 감점한다.
- duplicate 후보는 자동 merge/delete가 아니라 검수 후보로만 취급한다.

운영:

- 실험은 read-only다.
- accepted decision은 별도 graph patch 후보로 기록하되 적용하지 않는다.
- B 모드가 후보 밖에서 발견한 이슈는 `spillover`로 기록해 pre-filter 개선 후보로 삼는다.
- candidate 수가 너무 많으면 `max_candidates=8` 기본값을 유지하고 남은 후보는 skipped low-priority로 기록한다.

## 비범위

- Claude Desktop 자동화 스크립트 또는 prompt file 생성.
- MCP 도구 추가/수정.
- `projectos_review_graph` payload schema 변경.
- graph patch 자동 생성/적용.
- Simulation result schema/UI 변경.
- Inbox/Claude 검수 방향 코드 수정.
- live web/browser search 또는 외부 fact-check 자동화.
