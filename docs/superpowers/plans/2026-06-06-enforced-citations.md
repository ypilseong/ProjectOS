# Enforced Citations Implementation Plan

> **For agentic workers:** implement with focused TDD. Keep changes scoped to QueryAgent and its tests unless integration requires otherwise.

**Goal:** QueryAgent 답변 프롬프트에 source provenance를 보존하고, factual claim citation을 필수 규칙으로 만든다.

**Architecture:** `_find_relevant_chunks`는 hybrid retrieval 결과를 provenance dict로 반환한다. `_search_graph`는 node `source_files`를 유지한다. `_build_prompt`는 node/chunk source labels를 렌더하고, 답변 규칙을 citation required로 강화한다.

**Test path:** `cd /raid/home/a202121010/workspace/projects/ProjectOS/src/backend && python3 -m pytest tests/test_agents/test_query_agent.py tests/test_agents/test_query_agent_hybrid.py -q`

---

## Task 1: QueryAgent provenance 보존

Files:
- `src/backend/app/agents/query_agent.py`
- `src/backend/tests/test_agents/test_query_agent.py`
- `src/backend/tests/test_agents/test_query_agent_hybrid.py`

- [x] Add failing tests for node `source_files` preservation.
- [x] Add failing tests for chunk labels including `source_file`, `chunk_id`, optional page and char offset.
- [x] Implement `_chunk_label(chunk)` helper.
- [x] Change `_find_relevant_chunks` to return labeled excerpts instead of raw text.
- [x] Update existing tests that assumed raw strings.

## Task 2: Prompt citation contract

Files:
- `src/backend/app/agents/query_agent.py`
- `src/backend/tests/test_agents/test_query_agent.py`

- [x] Add tests that prompt contains chunk heading labels such as `[cv.pdf#id1 p.1 char:0]`.
- [x] Add tests that prompt renders node source files.
- [x] Replace citation suggestion with mandatory citation rules:
  - cite factual claims using provided labels;
  - use only labels present in context;
  - write `출처 불명` for unsupported claims.
- [x] Keep Korean answer requirement and graph relation guidance.

## Task 3: Verification and handoff

- [x] Run targeted QueryAgent tests.
- [x] Run backend test suite if targeted tests pass.
- [x] Update `docs/claude-code-handoff.md` with #4 completion status, changed files, test results, and any non-goals.
