# Autoresearch Implementation Plan

> **For agentic workers:** implement with focused TDD. Keep the first cut deterministic and read-only.

**Goal:** 그래프의 약점에서 research/backfill/review 후보를 구조화해 반환한다.

**Architecture:** 신규 `app/services/autoresearch.py`에 순수 함수 `generate_autoresearch_candidates(graph, ...)`를 둔다. API/MCP 연결은 서비스 검증 후 별도 단계에서 붙인다.

**Test path:** `cd /raid/home/a202121010/workspace/projects/ProjectOS/src/backend && python3 -m pytest tests/test_services/test_autoresearch.py -q`

---

## Task 1: Deterministic Candidate Generator

Files:
- `src/backend/app/services/autoresearch.py`
- `src/backend/tests/test_services/test_autoresearch.py`

- [x] Add tests for isolated node candidate.
- [x] Add tests for missing source candidate.
- [x] Add tests for sparse important node candidate and Category exclusion.
- [x] Add tests for small weak component candidate.
- [x] Add tests for duplicate review candidate.
- [x] Add tests for `max_candidates` and empty graph.
- [x] Implement `generate_autoresearch_candidates`.
- [x] Run focused service tests.

## Task 2: MCP Read Tool

Files:
- `src/backend/app/mcp_tools.py`
- `src/backend/tests/test_api/test_mcp_api.py`

- [x] Add `projectos_get_research_candidates` to `tools/list`.
- [x] Implement tool call by loading graph and calling `generate_autoresearch_candidates`.
- [x] Return structured content and concise text summary.
- [x] Add MCP tests for tool list and successful call.
- [x] Run MCP targeted tests.

## Task 3: Verification and Handoff

- [x] Run backend tests.
- [x] Update `docs/claude-code-handoff.md`.
- [x] Record non-goals: no live web search, no automatic graph mutation.
