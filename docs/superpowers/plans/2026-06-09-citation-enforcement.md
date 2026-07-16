# Citation Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** MCP 비스트리밍 질의 답변이 citation 규칙을 위반하면 자동 재생성으로 강제한다.

**Architecture:** `QueryAgent.answer_with_enforced_citations`가 컨텍스트/allowed label을 한 번 산출하고, `_generate`(비스트리밍 LLM) → `validate_citations` → 실패 시 `_build_citation_correction_prompt`로 재생성하는 루프를 돈다. MCP 핸들러가 이를 호출한다.

**Tech Stack:** FastAPI, networkx, app.services.citation_validator, app.utils.llm_client.

---

### Task 1: QueryAgent enforced-citation 메서드

**Files:**
- Modify: `src/backend/app/agents/query_agent.py`
- Test: `src/backend/tests/test_agents/test_query_agent.py`

- [ ] **Step 1: 실패 테스트 작성** — 위 spec의 4개 테스트(`attempts==1`, invalid→valid `attempts==2`, 소진 시 마지막 답변, correction prompt 내용). `AsyncMock`으로 `QueryAgent._generate` patch.
- [ ] **Step 2: 테스트 실패 확인** — `pytest tests/test_agents/test_query_agent.py -k enforced -v` → AttributeError.
- [ ] **Step 3: 구현** — `_generate`, `answer_with_enforced_citations`, `_build_citation_correction_prompt` 추가.
- [ ] **Step 4: 테스트 통과 확인.**
- [ ] **Step 5: 커밋.**

### Task 2: MCP 통합

**Files:**
- Modify: `src/backend/app/mcp_tools.py`
- Test: `src/backend/tests/test_api/test_mcp_api.py`

- [ ] **Step 1: 테스트 갱신/추가** — 기존 report 테스트를 `_generate` mock으로 변경하고 `attempts` 확인. 신규 재생성 테스트 추가.
- [ ] **Step 2: 테스트 실패 확인.**
- [ ] **Step 3: 핸들러 교체 + `max_citation_retries` 인자/스키마 추가, validator import 제거.**
- [ ] **Step 4: 테스트 통과 확인.**
- [ ] **Step 5: 커밋.**

### Task 3: 회귀 + handoff

- [ ] 전체 `pytest tests/ -q`.
- [ ] `docs/claude-code-handoff.md` 갱신, 커밋.
