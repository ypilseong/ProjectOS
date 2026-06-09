# Graph Review Workflow Implementation Plan

> **For agentic workers:** keep this read-only and deterministic. Do not touch simulation/inbox/google flows.

**Goal:** Claude Desktop이 graph 품질 검수를 수행할 때 full baseline과 targeted review를 같은 기준으로 비교할 수 있는 workflow payload를 제공한다.

**Architecture:** 신규 `app/services/graph_review.py`에 순수 함수 `build_graph_review_workflow`를 둔다. MCP `projectos_review_graph`는 graph/health/autoresearch를 읽어 payload를 반환한다.

**Test paths:**
- `cd /raid/home/a202121010/workspace/projects/ProjectOS/src/backend && python3 -m pytest tests/test_services/test_graph_review.py -q`
- `cd /raid/home/a202121010/workspace/projects/ProjectOS/src/backend && python3 -m pytest tests/test_api/test_mcp_api.py -q`

---

## Task 1: Workflow Builder

Files:
- `src/backend/app/services/graph_review.py`
- `src/backend/tests/test_services/test_graph_review.py`

- [x] Add deterministic service tests.
- [x] Add read-only/no graph mutation test.
- [x] Include mode comparison for `full_review` and `targeted_review`.
- [x] Include evaluation metrics.
- [x] Include targeted candidate summary/checklist/next steps.
- [x] Include token-saving guidance.
- [x] Implement `build_graph_review_workflow`.
- [x] Run focused service tests.

## Task 2: MCP Read Tool

Files:
- `src/backend/app/mcp_tools.py`
- `src/backend/tests/test_api/test_mcp_api.py`

- [x] Add `projectos_review_graph` to `tools/list`.
- [x] Implement tool call by loading graph, chunks, health, and autoresearch candidates.
- [x] Return concise text summary and structured workflow payload.
- [x] Add MCP list/call tests.
- [x] Run MCP targeted tests.

## Task 3: Verification and Handoff

- [x] Run backend tests.
- [x] Update `docs/claude-code-handoff.md`.
- [x] Record non-goals: no web search, no graph mutation, no simulation UI/schema changes.
