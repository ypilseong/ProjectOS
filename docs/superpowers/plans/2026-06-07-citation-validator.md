# Citation Validator Implementation Plan

> **For agentic workers:** keep validation deterministic and read-only. Do not rewrite answers automatically.

**Goal:** QueryAgent 답변이 제공된 citation label만 사용하는지 검사하고 MCP structuredContent에 report를 포함한다.

**Architecture:** 신규 `app/services/citation_validator.py`에 순수 validator를 둔다. QueryAgent는 prompt에 제공한 label set을 수집하는 helper를 제공한다. MCP query tool은 답변과 citation report를 함께 반환한다.

**Test paths:**
- `cd /raid/home/a202121010/workspace/projects/ProjectOS/src/backend && python3 -m pytest tests/test_services/test_citation_validator.py -q`
- `cd /raid/home/a202121010/workspace/projects/ProjectOS/src/backend && python3 -m pytest tests/test_agents/test_query_agent.py tests/test_api/test_mcp_api.py -q`

---

## Task 1: Validator Service

Files:
- `src/backend/app/services/citation_validator.py`
- `src/backend/tests/test_services/test_citation_validator.py`

- [x] Add tests for allowed labels.
- [x] Add tests for unknown labels.
- [x] Add tests for missing citation sentence candidates.
- [x] Add tests for `출처 불명` marker.
- [x] Add deterministic and empty answer tests.
- [x] Implement `validate_citations`.
- [x] Run focused service tests.

## Task 2: QueryAgent Label Collection

Files:
- `src/backend/app/agents/query_agent.py`
- `src/backend/tests/test_agents/test_query_agent.py`

- [x] Add helper to collect allowed citation labels from context/chunk excerpts/wiki context.
- [x] Keep prompt rendering behavior unchanged.
- [x] Add tests for chunk labels, node source labels, and wiki source labels.
- [x] Run QueryAgent tests.

## Task 3: MCP Query Report

Files:
- `src/backend/app/mcp_tools.py`
- `src/backend/tests/test_api/test_mcp_api.py`

- [x] Add citation report to `projectos_query_career_graph` structuredContent.
- [x] Keep answer text unchanged.
- [x] Add MCP test for report fields.
- [x] Run MCP tests.

## Task 4: Verification and Handoff

- [x] Run backend tests.
- [x] Update `docs/claude-code-handoff.md`.
- [x] Record non-goals: no SSE report, no auto rewrite/retry, no LLM fact-check.
