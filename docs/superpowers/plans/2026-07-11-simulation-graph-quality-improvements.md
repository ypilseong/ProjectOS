# Simulation & Graph Quality Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sim_20260628_152220_230888` 리뷰에서 발견한 6개 결함(증거 ref 해석 불가, delta 중복 제안, proposed delta 사장, merge 후보 오탐, debate 합의 집계 누락, career layer 과대 전파)을 수정한다.

**Architecture:** 백엔드는 `src/backend`의 FastAPI + NetworkX 구조를 그대로 따른다. 시뮬레이션 delta 검토 플로우는 이미 검증된 merge-candidates apply/reject 패턴(서비스 함수 + POST 엔드포인트 + 프론트 버튼)을 재사용한다. LLM 출력 품질 문제는 (1) 프롬프트 계약 강화와 (2) 결정론적 후처리 검증의 이중 방어로 해결한다.

**Tech Stack:** Python 3.14 / FastAPI / NetworkX / pytest, Vue 3 + Element Plus / Vitest

## Global Constraints

- 백엔드 테스트: `cd src/backend && python3 -m pytest tests/ -q` (전체), 개별 파일은 `-v`
- 프론트엔드 테스트: `cd src/frontend && npx vitest run`, 빌드는 `npm run build`
- TDD: 테스트 먼저 작성 → 실패 확인 → 구현 → 통과 확인 → 커밋
- 엔티티 타입 9종 고정: Person, Project, Skill, Organization, Publication, Role, Achievement, Event, Institution
- 관계 10종 고정: WORKED_AT, DEVELOPED, USES_SKILL, AUTHORED, COLLABORATED_WITH, ACHIEVED, PARTICIPATED_IN, PUBLISHED_AT, MENTORED_BY, LED_BY (+ 빌더가 실제 사용하는 INCLUDES, HAS, HAS_ROLE, RELATED_TO)
- 커밋 메시지는 기존 히스토리 스타일: `feat(sim): ...`, `fix(merge): ...`, `docs(handoff): ...`
- `../MiroFish/`는 READ-ONLY. `vite.config.js` proxy 변경은 커밋 금지
- 서버 포트: backend 8001, frontend 5174 (dgx02에서 8000/5173 점유됨)
- 모든 작업 완료 후 `docs/claude-code-handoff.md` 업데이트 필수 (Task 10)
- Task 1–2 (증거 ref), Task 3 (delta 검증), Task 4–6 (delta 검토 플로우), Task 7 (merge 가드), Task 8 (debate 집계), Task 9 (layer)는 서로 독립적으로 실행·리뷰 가능. Task 5는 Task 4에, Task 6은 Task 5에 의존.

## 배경: 리뷰에서 확인된 사실 (2026-07-07)

- 최근 실행 `sim_20260628_152220_230888` (project `21fc2ce5`)의 고유 evidence ref 22개 중 `_resolve_ref`가 요구하는 접두사(`node:`/`chunk:`/`event:`)를 가진 것이 0개. 10개는 `Person:양필성` 같은 bare 노드 ID, 12개는 자유 텍스트. `Organization:KAIST`처럼 타입을 잘못 쓴 ref도 존재(실제 노드는 `Institution:KAIST`).
- delta가 `Skill:Cross-Impact Balance (CIB)` 신규 추가를 제안했지만 그래프에 `Skill:Cross-Impact Balance`, `Skill:probabilistic CIB`가 이미 존재. 적용 시 dedup은 exact-name뿐.
- delta 엣지 relation에 스키마 밖 타입(`TARGET_COMPETENCE`, `USES_METHODOLOGY`) 등장.
- `apply_graph=False` 실행 시 7개 delta가 전부 `proposed`로 남는데 이를 나중에 승인/거부할 API가 없음.
- merge_candidates 8건 중 `simulation↔estimation`(0.8), `AI↔AMI`, `cpWER↔cpCER`, 서로 다른 arXiv URL 2건이 오탐.
- `_build_debate`가 debate 레벨 `agreements`/`disagreements`/`unresolved_questions`를 빈 배열로 하드코딩 (턴 레벨 unresolved_questions 30개 존재).
- career layer가 313개 분석 노드 중 187개(60%), Skill 168개 중 108개. `USES_SKILL`이 `_OWNERSHIP_RELATIONS`에 포함되어 career Project를 거쳐 과대 전파.

---

### Task 1: `_resolve_ref` bare 노드 ID fallback

**Files:**
- Modify: `src/backend/app/services/simulation_context.py:508-579`
- Test: `src/backend/tests/test_services/test_simulation_context.py`

**Interfaces:**
- Consumes: 기존 `_resolve_ref(ref, *, chunks, graph, events, sections, max_chars) -> dict`
- Produces: 동일 시그니처. 추가 동작 — `node:` 접두사 없는 `Type:Name` ref, 타입이 틀렸지만 이름이 유일하게 일치하는 ref도 `kind: "node"`로 해석. 새 헬퍼 `_node_payload(ref: str, node_id: str, data: dict) -> dict[str, Any]`, `_resolve_bare_node_ref(ref: str, graph: nx.DiGraph) -> dict[str, Any] | None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_services/test_simulation_context.py`에 추가 (파일 상단에 `from app.services.simulation_context import _resolve_ref` 및 `import networkx as nx`가 없으면 추가):

```python
def _graph_with_kaist():
    graph = nx.DiGraph()
    graph.add_node(
        "Institution:KAIST", type="Institution", name="KAIST",
        description="대학", source_files=["resume.pdf"], evidence=[],
    )
    graph.add_node(
        "Skill:Python", type="Skill", name="Python",
        description="언어", source_files=["resume.pdf"], evidence=[],
    )
    return graph


def test_resolve_ref_accepts_bare_node_id():
    item = _resolve_ref(
        "Skill:Python",
        chunks=[], graph=_graph_with_kaist(), events={}, sections={}, max_chars=500,
    )
    assert item["resolved"] is True
    assert item["kind"] == "node"
    assert item["node_id"] == "Skill:Python"


def test_resolve_ref_recovers_wrong_type_prefix_by_unique_name():
    item = _resolve_ref(
        "Organization:KAIST",
        chunks=[], graph=_graph_with_kaist(), events={}, sections={}, max_chars=500,
    )
    assert item["resolved"] is True
    assert item["node_id"] == "Institution:KAIST"


def test_resolve_ref_ambiguous_name_stays_unresolved():
    graph = _graph_with_kaist()
    graph.add_node("Organization:Python", type="Organization", name="Python")
    item = _resolve_ref(
        "Publication:Python",
        chunks=[], graph=graph, events={}, sections={}, max_chars=500,
    )
    assert item["resolved"] is False


def test_resolve_ref_free_text_stays_unresolved():
    item = _resolve_ref(
        "agent_3, agent_1의 뉴로-심볼릭 아키텍처 제안",
        chunks=[], graph=_graph_with_kaist(), events={}, sections={}, max_chars=500,
    )
    assert item["resolved"] is False
    assert item["kind"] == "unknown"
```

- [ ] **Step 2: 실패 확인**

Run: `cd src/backend && python3 -m pytest tests/test_services/test_simulation_context.py -q -k "bare_node or wrong_type or ambiguous_name or free_text"`
Expected: FAIL — `test_resolve_ref_accepts_bare_node_id`, `test_resolve_ref_recovers_wrong_type_prefix_by_unique_name` (resolved False)

- [ ] **Step 3: 구현**

`simulation_context.py`의 `_resolve_ref`에서 `node:` 분기의 노드 payload 생성을 헬퍼로 추출하고, 마지막 `return {"ref": ref, "resolved": False, ...}` 직전에 bare fallback을 추가:

```python
def _node_payload(ref: str, node_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": ref,
        "resolved": True,
        "kind": "node",
        "node_id": node_id,
        "type": data.get("type"),
        "name": data.get("name"),
        "description": data.get("description", ""),
        "source_files": list(data.get("source_files") or []),
        "evidence": list(data.get("evidence") or []),
    }


def _resolve_bare_node_ref(ref: str, graph: nx.DiGraph) -> dict[str, Any] | None:
    """Resolve refs like "Skill:Python" (no "node:" prefix) — the format LLM
    debate turns actually emit. Tolerates a wrong type prefix when the name
    part matches exactly one node."""
    if ":" not in ref:
        return None
    if ref in graph:
        return _node_payload(ref, ref, graph.nodes[ref])
    _, _, name = ref.partition(":")
    name = name.strip()
    if not name:
        return None
    matches = [
        node_id
        for node_id, data in graph.nodes(data=True)
        if str(data.get("name", "")).strip() == name
    ]
    if len(matches) != 1:
        return None
    return _node_payload(ref, matches[0], graph.nodes[matches[0]])
```

`_resolve_ref` 내부 수정 — `node:` 분기를 헬퍼 사용으로 교체하고 말미에 fallback 호출:

```python
    elif ref.startswith("node:"):
        node_id = ref[len("node:"):]
        if node_id in graph:
            return _node_payload(ref, node_id, graph.nodes[node_id])
```

```python
    bare = _resolve_bare_node_ref(ref, graph)
    if bare is not None:
        return bare
    return {"ref": ref, "resolved": False, "kind": "unknown"}
```

- [ ] **Step 4: 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_services/test_simulation_context.py -q`
Expected: 전체 PASS (기존 테스트 포함)

- [ ] **Step 5: 커밋**

```bash
git add src/backend/app/services/simulation_context.py src/backend/tests/test_services/test_simulation_context.py
git commit -m "feat(sim): resolve bare Type:Name evidence refs with unique-name fallback"
```

---

### Task 2: Evidence ref 형식 프롬프트 계약 강화

**Files:**
- Modify: `src/backend/app/agents/simulation_agent.py:324-354` (debate turn 프롬프트), `:382-436` (synthesis 프롬프트)
- Test: `src/backend/tests/test_agents/test_simulation_agent.py`

**Interfaces:**
- Produces: 모듈 상수 `EVIDENCE_REF_RULE: str` (simulation_agent.py 상단, 다른 상수들 옆). 두 프롬프트 모두 이 상수를 포함.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_agents/test_simulation_agent.py`에 추가. 페르소나/환경 fake는 같은 파일의 `test_project_simulation_agent_runs_multi_turn_persona_debate`(약 233행)에 이미 있는 `FakePersonaAgent`/`FakeEnvironmentAgent`와 동일한 것을 그대로 복사해 사용하고, FakeLLM만 아래로 교체:

```python
@pytest.mark.asyncio
async def test_debate_and_synthesis_prompts_require_structured_evidence_refs():
    from app.agents.simulation_agent import EVIDENCE_REF_RULE, ProjectSimulationAgent

    captured_prompts = []

    class PromptCapturingLLM:
        model = "fake-model"

        async def chat_json(self, messages):
            prompt = messages[0]["content"]
            captured_prompts.append(prompt)
            if "debate의 다음 발언" in prompt:
                return {
                    "observation": "관찰", "proposal": "제안",
                    "evidence_refs": ["Skill:Python"],
                    "responds_to": "", "unresolved_questions": [],
                }
            return {
                "timeline": [], "graph_enhancements": {"nodes": [], "edges": []},
                "cv_improvements": {}, "report": {"title": "t", "answer": "a",
                "recommendations": [], "evidence": []},
            }

    # FakePersonaAgent / FakeEnvironmentAgent / graph / chunks 는
    # test_project_simulation_agent_runs_multi_turn_persona_debate 와 동일하게 구성
    agent = ProjectSimulationAgent(
        persona_agent=FakePersonaAgent(),
        environment_agent=FakeEnvironmentAgent(),
        llm=PromptCapturingLLM(),
    )
    await agent.run(graph, chunks, query="테스트 쿼리", apply_graph=False)

    debate_prompts = [p for p in captured_prompts if "debate의 다음 발언" in p]
    synthesis_prompts = [p for p in captured_prompts if "종합해" in p]
    assert debate_prompts and synthesis_prompts
    assert all(EVIDENCE_REF_RULE in p for p in debate_prompts)
    assert all(EVIDENCE_REF_RULE in p for p in synthesis_prompts)


def test_evidence_ref_rule_names_both_formats():
    from app.agents.simulation_agent import EVIDENCE_REF_RULE

    assert "타입:이름" in EVIDENCE_REF_RULE
    assert "chunk:" in EVIDENCE_REF_RULE
```

- [ ] **Step 2: 실패 확인**

Run: `cd src/backend && python3 -m pytest tests/test_agents/test_simulation_agent.py -q -k evidence_ref`
Expected: FAIL with `ImportError: cannot import name 'EVIDENCE_REF_RULE'`

- [ ] **Step 3: 구현**

`simulation_agent.py` 상단(기존 `_MAX_DEBATE_HISTORY_TURNS` 등 상수 옆)에 추가:

```python
EVIDENCE_REF_RULE = (
    "evidence_refs/evidence 규칙: 그래프/문서 컨텍스트에 실제로 존재하는 항목만 적으세요. "
    "노드 근거는 '타입:이름' 그대로(예: \"Skill:Python\", \"Institution:KAIST\"), "
    "문서 근거는 'chunk:파일명#청크ID' 형식으로 적으세요. "
    "자유 서술 문장이나 'agent_3의 제안' 같은 표현은 넣지 마세요."
)
```

debate turn 프롬프트(324행 f-string) 수정 — JSON 스키마 직전에 규칙 삽입, 스키마 예시 문구 교체:

```python
{EVIDENCE_REF_RULE}

JSON만 응답하세요:
{{
  "observation": "이전 발언과 근거를 고려한 관찰 또는 반론",
  "proposal": "다음 분석/그래프/CV 개선 제안",
  "evidence_refs": ["타입:이름 또는 chunk:파일명#청크ID"],
  "responds_to": "직접 응답한 이전 turn_id 또는 빈 문자열",
  "unresolved_questions": ["남은 쟁점"]
}}
```

synthesis 프롬프트(382행) 수정 — "중요:" 블록에 한 줄 추가:

```python
중요:
- timeline은 아래 실제 순차 debate 로그를 그대로 반영하세요.
- 서로 다른 persona의 합의/불일치/남은 쟁점을 report와 recommendations에 반영하세요.
- debate에 없는 새 사실은 만들지 말고 그래프/문서 컨텍스트 근거가 있는 제안만 graph_enhancements에 넣으세요.
- {EVIDENCE_REF_RULE}
```

그리고 synthesis JSON 스키마의 `"evidence": ["근거"]` (434행) 및 node/edge의 `"evidence": "근거"` (419, 422행)를 각각 `"evidence": ["타입:이름 또는 chunk:파일명#청크ID"]`, `"evidence": "타입:이름 또는 chunk:파일명#청크ID"`로 교체.

- [ ] **Step 4: 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_agents/test_simulation_agent.py -q`
Expected: 전체 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/backend/app/agents/simulation_agent.py src/backend/tests/test_agents/test_simulation_agent.py
git commit -m "feat(sim): enforce structured evidence ref format in debate and synthesis prompts"
```

---

### Task 3: Delta 초안 검증 — 중복 노드 감지 + relation 화이트리스트

**Files:**
- Create: `src/backend/app/utils/graph_delta_validation.py`
- Modify: `src/backend/app/agents/simulation_agent.py` — `run()`(222-231행), `_apply_graph_enhancements_with_status`(1000행), `_proposed_delta_statuses`(970행), `_build_graph_delta`(866행), synthesis 프롬프트 relation 제약
- Test: `src/backend/tests/test_utils/test_graph_delta_validation.py` (신규), `src/backend/tests/test_agents/test_simulation_agent.py`

**Interfaces:**
- Produces: `validate_graph_enhancements(graph: nx.DiGraph, enhancements: dict[str, Any]) -> dict[str, Any]` — 노드에 `duplicate_of: str` 주석, 엣지 endpoint를 기존 노드로 remap, 스키마 밖 relation을 `RELATED_TO`로 정규화(원본은 `relation_raw`에 보존). 모듈 상수 `ALLOWED_RELATIONS: set[str]`.
- Consumes: `app.utils.entity_normalization.are_acronym_variants(a, b) -> bool`, `config.FUZZY_MATCH_THRESHOLD` (0.85)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_utils/test_graph_delta_validation.py` 신규 작성:

```python
import networkx as nx

from app.utils.graph_delta_validation import ALLOWED_RELATIONS, validate_graph_enhancements


def _graph():
    g = nx.DiGraph()
    g.add_node("Skill:Cross-Impact Balance", type="Skill", name="Cross-Impact Balance")
    g.add_node("Person:양필성", type="Person", name="양필성")
    return g


def test_duplicate_node_gets_annotated_not_dropped():
    enhancements = {
        "nodes": [{"type": "Skill", "name": "Cross-Impact Balance (CIB)", "description": "d", "evidence": "e"}],
        "edges": [],
    }
    result = validate_graph_enhancements(_graph(), enhancements)
    assert result["nodes"][0]["duplicate_of"] == "Skill:Cross-Impact Balance"


def test_edge_endpoint_remapped_to_existing_duplicate():
    enhancements = {
        "nodes": [{"type": "Skill", "name": "Cross-Impact Balance (CIB)", "description": "d", "evidence": "e"}],
        "edges": [{
            "source_type": "Person", "source_name": "양필성",
            "target_type": "Skill", "target_name": "Cross-Impact Balance (CIB)",
            "relation": "USES_SKILL", "evidence": "e", "confidence": 0.7,
        }],
    }
    result = validate_graph_enhancements(_graph(), enhancements)
    assert result["edges"][0]["target_name"] == "Cross-Impact Balance"


def test_off_schema_relation_normalized_to_related_to():
    enhancements = {
        "nodes": [],
        "edges": [{
            "source_type": "Person", "source_name": "양필성",
            "target_type": "Skill", "target_name": "Cross-Impact Balance",
            "relation": "TARGET_COMPETENCE", "evidence": "e", "confidence": 0.7,
        }],
    }
    result = validate_graph_enhancements(_graph(), enhancements)
    assert result["edges"][0]["relation"] == "RELATED_TO"
    assert result["edges"][0]["relation_raw"] == "TARGET_COMPETENCE"


def test_new_node_and_valid_relation_pass_through():
    enhancements = {
        "nodes": [{"type": "Skill", "name": "Monte Carlo Simulation", "description": "d", "evidence": "e"}],
        "edges": [{
            "source_type": "Person", "source_name": "양필성",
            "target_type": "Skill", "target_name": "Monte Carlo Simulation",
            "relation": "USES_SKILL", "evidence": "e", "confidence": 0.7,
        }],
    }
    result = validate_graph_enhancements(_graph(), enhancements)
    assert "duplicate_of" not in result["nodes"][0]
    assert result["edges"][0]["relation"] == "USES_SKILL"
    assert "relation_raw" not in result["edges"][0]


def test_allowed_relations_contains_fixed_vocabulary():
    assert {"WORKED_AT", "DEVELOPED", "USES_SKILL", "AUTHORED", "COLLABORATED_WITH",
            "ACHIEVED", "PARTICIPATED_IN", "PUBLISHED_AT", "MENTORED_BY", "LED_BY"} <= ALLOWED_RELATIONS
```

- [ ] **Step 2: 실패 확인**

Run: `cd src/backend && python3 -m pytest tests/test_utils/test_graph_delta_validation.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.utils.graph_delta_validation'`

- [ ] **Step 3: `graph_delta_validation.py` 구현**

```python
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

import networkx as nx

from app.config import config
from app.utils.entity_normalization import are_acronym_variants
from app.utils.logger import get_logger

logger = get_logger(__name__)

# CLAUDE.md 고정 관계 10종 + 그래프 빌더가 실제 사용하는 구조 관계.
ALLOWED_RELATIONS = {
    "WORKED_AT", "DEVELOPED", "USES_SKILL", "AUTHORED", "COLLABORATED_WITH",
    "ACHIEVED", "PARTICIPATED_IN", "PUBLISHED_AT", "MENTORED_BY", "LED_BY",
    "HAS_ROLE", "INCLUDES", "HAS", "RELATED_TO",
}


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _find_existing_duplicate(graph: nx.DiGraph, ntype: str, name: str) -> str | None:
    threshold = config.FUZZY_MATCH_THRESHOLD
    exact_id = f"{ntype}:{name}"
    for node_id, data in graph.nodes(data=True):
        if node_id == exact_id or data.get("type") != ntype:
            continue
        existing = str(data.get("name", "")).strip()
        if not existing:
            continue
        if (
            existing.lower() == name.lower()
            or are_acronym_variants(existing, name)
            or _similarity(existing, name) >= threshold
        ):
            return node_id
    return None


def validate_graph_enhancements(
    graph: nx.DiGraph,
    enhancements: dict[str, Any],
) -> dict[str, Any]:
    """Annotate LLM-drafted graph enhancements against the real graph.

    Node drafts that fuzzy-match an existing same-type node get ``duplicate_of``
    so the review/apply path proposes a merge instead of a blind add; edge
    endpoints pointing at a duplicate draft are remapped to the existing node;
    relations outside ALLOWED_RELATIONS become RELATED_TO with the original kept
    in ``relation_raw``.
    """
    nodes = list(enhancements.get("nodes", []) or [])
    edges = list(enhancements.get("edges", []) or [])
    remap: dict[tuple[str, str], str] = {}

    for node in nodes:
        ntype = str(node.get("type") or "").strip()
        name = str(node.get("name") or "").strip()
        if not ntype or not name:
            continue
        existing = _find_existing_duplicate(graph, ntype, name)
        if existing:
            node["duplicate_of"] = existing
            remap[(ntype, name)] = existing
            logger.info(f"Delta validation: '{ntype}:{name}' duplicates '{existing}'")

    for edge in edges:
        for side in ("source", "target"):
            key = (
                str(edge.get(f"{side}_type") or "").strip(),
                str(edge.get(f"{side}_name") or "").strip(),
            )
            if key in remap:
                existing_type, _, existing_name = remap[key].partition(":")
                edge[f"{side}_type"] = existing_type
                edge[f"{side}_name"] = existing_name
        relation = str(edge.get("relation") or "").strip().upper()
        if relation not in ALLOWED_RELATIONS:
            edge["relation_raw"] = edge.get("relation")
            edge["relation"] = "RELATED_TO"

    return {"nodes": nodes, "edges": edges}
```

- [ ] **Step 4: 유틸 테스트 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_utils/test_graph_delta_validation.py -q`
Expected: 5 passed

- [ ] **Step 5: simulation_agent 배선 테스트 작성**

`tests/test_agents/test_simulation_agent.py`에 추가 (fixture는 Task 2와 동일한 방식으로 기존 debate 테스트에서 복사, FakeLLM synthesis 응답의 graph_enhancements만 아래로 교체):

```python
@pytest.mark.asyncio
async def test_run_marks_duplicate_delta_as_skipped_without_applying():
    # graph fixture에 다음 노드를 추가해 두고:
    #   graph.add_node("Skill:Cross-Impact Balance", type="Skill", name="Cross-Impact Balance")
    # FakeLLM synthesis 응답에 포함:
    #   "graph_enhancements": {
    #       "nodes": [{"type": "Skill", "name": "Cross-Impact Balance (CIB)",
    #                  "description": "d", "evidence": "Skill:Cross-Impact Balance"}],
    #       "edges": [],
    #   }
    result = await agent.run(graph, chunks, query="q", apply_graph=True)

    node_delta = result["graph_delta"]["nodes"][0]
    assert node_delta["status"] == "skipped"
    assert "Skill:Cross-Impact Balance" in node_delta["status_reason"]
    assert "Skill:Cross-Impact Balance (CIB)" not in graph
    assert result["applied_graph_changes"]["nodes_added"] == 0
```

- [ ] **Step 6: 실패 확인**

Run: `cd src/backend && python3 -m pytest tests/test_agents/test_simulation_agent.py -q -k duplicate_delta`
Expected: FAIL — status가 "applied"이고 중복 노드가 그래프에 추가됨

- [ ] **Step 7: simulation_agent 배선 구현**

(a) `run()` 222행 `legacy_result = self._normalize_legacy_result(...)` 다음에 삽입:

```python
        from app.utils.graph_delta_validation import validate_graph_enhancements

        legacy_result["graph_enhancements"] = validate_graph_enhancements(
            graph, legacy_result.get("graph_enhancements", {})
        )
```

(임포트는 파일 상단으로 올려도 됨 — simulation_agent는 API 라우터가 아니므로 순환 임포트 제약 없음.)

(b) `_apply_graph_enhancements_with_status`의 노드 루프에서 `if node_id in graph:` 분기 **앞에** 추가:

```python
        duplicate_of = str(node.get("duplicate_of") or "")
        if duplicate_of:
            node_statuses.append({
                "status": "skipped",
                "status_reason": f"Similar node already exists: {duplicate_of}",
                "node_id": node_id,
            })
            continue
```

(c) `_proposed_delta_statuses`를 중복 인지형으로 교체:

```python
def _proposed_delta_statuses(enhancements: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    node_statuses = []
    for node in enhancements.get("nodes", []) or []:
        duplicate_of = str(node.get("duplicate_of") or "")
        if duplicate_of:
            node_statuses.append({
                "status": "skipped",
                "status_reason": f"Similar node already exists: {duplicate_of}",
            })
        else:
            node_statuses.append({"status": "proposed", "status_reason": ""})
    return {
        "nodes": node_statuses,
        "edges": [
            {"status": "proposed", "status_reason": ""}
            for _ in enhancements.get("edges", []) or []
        ],
    }
```

(d) `_build_graph_delta` 노드 dict에 한 줄 추가 (`"status_reason"` 위):

```python
            "duplicate_of": str(node.get("duplicate_of") or ""),
```

엣지 dict에도 relation 원본 보존:

```python
            "relation_raw": str(edge.get("relation_raw") or ""),
```

(e) synthesis 프롬프트(Task 2에서 수정한 "중요:" 블록)에 relation 제약 한 줄 추가:

```
- graph_enhancements.edges의 relation은 다음 중에서만 선택: WORKED_AT, DEVELOPED, USES_SKILL, AUTHORED, COLLABORATED_WITH, ACHIEVED, PARTICIPATED_IN, PUBLISHED_AT, MENTORED_BY, LED_BY
```

- [ ] **Step 8: 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_agents/test_simulation_agent.py tests/test_utils/test_graph_delta_validation.py -q`
Expected: 전체 PASS

- [ ] **Step 9: 커밋**

```bash
git add src/backend/app/utils/graph_delta_validation.py src/backend/app/agents/simulation_agent.py src/backend/tests/test_utils/test_graph_delta_validation.py src/backend/tests/test_agents/test_simulation_agent.py
git commit -m "feat(sim): validate drafted graph deltas against existing nodes and relation vocabulary"
```

---

### Task 4: proposed delta 승인/거부 서비스

**Files:**
- Create: `src/backend/app/services/simulation_delta.py`
- Test: `src/backend/tests/test_services/test_simulation_delta.py`

**Interfaces:**
- Produces:
  - `apply_simulation_delta(project_id: str, delta_id: str) -> dict[str, Any]` — 반환 `{"delta": <갱신된 delta item>, "applied": {"nodes_added": int, "edges_added": int}, "summary": <graph_delta.summary>}`
  - `reject_simulation_delta(project_id: str, delta_id: str, reason: str = "") -> dict[str, Any]` — 반환 `{"delta": ..., "summary": ...}`
  - `class SimulationDeltaError(Exception)` — `status_code: int`, `detail: str` 속성 (404 미존재, 409 상태 충돌)
- Consumes: `simulation_agent._apply_graph_enhancements_with_status`, `graph_promotion.classify_node_layers`, 프로젝트 파일 레이아웃 (`projects/{id}/simulation.json`, `graph.json`, `chunks.json`, `simulations/{run_id}.json`)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_services/test_simulation_delta.py` 신규 작성:

```python
import json
from pathlib import Path

import networkx as nx
import pytest
from networkx.readwrite import json_graph

from app.config import config


def _write_project(tmp_path: Path) -> str:
    project_id = "testproj"
    proj_dir = tmp_path / project_id
    proj_dir.mkdir()
    (proj_dir / "simulations").mkdir()

    graph = nx.DiGraph()
    graph.add_node("Person:양필성", type="Person", name="양필성")
    out = json_graph.node_link_data(graph)
    (proj_dir / "graph.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    (proj_dir / "chunks.json").write_text("[]", encoding="utf-8")

    simulation = {
        "schema_version": "2.0",
        "run_id": "sim_test_run",
        "graph_delta": {
            "summary": {"proposed_nodes": 1, "proposed_edges": 1,
                        "applied_nodes": 0, "applied_edges": 0, "skipped": 0},
            "nodes": [{
                "delta_id": "delta_node_001", "operation": "add",
                "node_id": "Skill:Monte Carlo Simulation",
                "type": "Skill", "name": "Monte Carlo Simulation",
                "description": "표본 기반 수렴 분석", "confidence": 0.8,
                "evidence_refs": ["Person:양필성"], "duplicate_of": "",
                "status": "proposed", "status_reason": "",
            }],
            "edges": [{
                "delta_id": "delta_edge_001", "operation": "add",
                "source_type": "Person", "source_name": "양필성",
                "target_type": "Skill", "target_name": "Monte Carlo Simulation",
                "relation": "USES_SKILL", "confidence": 0.7,
                "evidence_refs": ["Person:양필성"],
                "status": "proposed", "status_reason": "",
            }],
        },
    }
    text = json.dumps(simulation, ensure_ascii=False)
    (proj_dir / "simulation.json").write_text(text, encoding="utf-8")
    (proj_dir / "simulations" / "sim_test_run.json").write_text(text, encoding="utf-8")
    return project_id


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    return _write_project(tmp_path), tmp_path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_apply_node_delta_adds_node_and_updates_statuses(project):
    from app.services.simulation_delta import apply_simulation_delta

    project_id, tmp_path = project
    result = apply_simulation_delta(project_id, "delta_node_001")

    assert result["delta"]["status"] == "applied"
    assert result["applied"]["nodes_added"] == 1

    graph_data = _load(tmp_path / project_id / "graph.json")
    node_ids = {n["id"] for n in graph_data["nodes"]}
    assert "Skill:Monte Carlo Simulation" in node_ids

    saved = _load(tmp_path / project_id / "simulation.json")
    assert saved["graph_delta"]["nodes"][0]["status"] == "applied"
    assert saved["graph_delta"]["summary"]["applied_nodes"] == 1
    archived = _load(tmp_path / project_id / "simulations" / "sim_test_run.json")
    assert archived["graph_delta"]["nodes"][0]["status"] == "applied"


def test_apply_edge_delta_after_node(project):
    from app.services.simulation_delta import apply_simulation_delta

    project_id, tmp_path = project
    apply_simulation_delta(project_id, "delta_node_001")
    result = apply_simulation_delta(project_id, "delta_edge_001")

    assert result["delta"]["status"] == "applied"
    graph_data = _load(tmp_path / project_id / "graph.json")
    edge_key = "links" if "links" in graph_data else "edges"
    pairs = {(e["source"], e["target"]) for e in graph_data[edge_key]}
    assert ("Person:양필성", "Skill:Monte Carlo Simulation") in pairs


def test_apply_twice_raises_conflict(project):
    from app.services.simulation_delta import SimulationDeltaError, apply_simulation_delta

    project_id, _ = project
    apply_simulation_delta(project_id, "delta_node_001")
    with pytest.raises(SimulationDeltaError) as exc:
        apply_simulation_delta(project_id, "delta_node_001")
    assert exc.value.status_code == 409


def test_reject_marks_delta_rejected_without_touching_graph(project):
    from app.services.simulation_delta import reject_simulation_delta

    project_id, tmp_path = project
    result = reject_simulation_delta(project_id, "delta_node_001", reason="근거 부족")

    assert result["delta"]["status"] == "rejected"
    assert result["delta"]["status_reason"] == "근거 부족"
    graph_data = _load(tmp_path / project_id / "graph.json")
    node_ids = {n["id"] for n in graph_data["nodes"]}
    assert "Skill:Monte Carlo Simulation" not in node_ids


def test_unknown_delta_raises_404(project):
    from app.services.simulation_delta import SimulationDeltaError, apply_simulation_delta

    project_id, _ = project
    with pytest.raises(SimulationDeltaError) as exc:
        apply_simulation_delta(project_id, "delta_node_999")
    assert exc.value.status_code == 404
```

- [ ] **Step 2: 실패 확인**

Run: `cd src/backend && python3 -m pytest tests/test_services/test_simulation_delta.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.simulation_delta'`

- [ ] **Step 3: `simulation_delta.py` 구현**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph

from app.config import config


class SimulationDeltaError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _project_dir(project_id: str) -> Path:
    return Path(config.PROJECTS_DIR) / project_id


def _load_json(path: Path, missing_detail: str) -> dict[str, Any]:
    if not path.exists():
        raise SimulationDeltaError(404, missing_detail)
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_graph(proj_dir: Path) -> nx.DiGraph:
    data = _load_json(proj_dir / "graph.json", "Graph not built yet")
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    return nx.node_link_graph(data)


def _save_graph(proj_dir: Path, graph: nx.DiGraph) -> None:
    out = json_graph.node_link_data(graph)
    if "edges" in out and "links" not in out:
        out["links"] = out.pop("edges")
    _save_json(proj_dir / "graph.json", out)


def _find_delta(simulation: dict[str, Any], delta_id: str) -> tuple[str, dict[str, Any]]:
    graph_delta = simulation.get("graph_delta") or {}
    for kind in ("nodes", "edges"):
        for item in graph_delta.get(kind, []) or []:
            if item.get("delta_id") == delta_id:
                return kind, item
    raise SimulationDeltaError(404, f"Delta {delta_id} not found")


def _refresh_summary(simulation: dict[str, Any]) -> None:
    graph_delta = simulation.get("graph_delta") or {}
    nodes = graph_delta.get("nodes", []) or []
    edges = graph_delta.get("edges", []) or []
    graph_delta["summary"] = {
        "proposed_nodes": len(nodes),
        "proposed_edges": len(edges),
        "applied_nodes": sum(1 for i in nodes if i.get("status") == "applied"),
        "applied_edges": sum(1 for i in edges if i.get("status") == "applied"),
        "skipped": sum(1 for i in [*nodes, *edges] if i.get("status") == "skipped"),
    }


def _persist_simulation(proj_dir: Path, simulation: dict[str, Any]) -> None:
    _save_json(proj_dir / "simulation.json", simulation)
    run_id = simulation.get("run_id")
    if run_id:
        archive = proj_dir / "simulations" / f"{run_id}.json"
        if archive.parent.exists():
            _save_json(archive, simulation)


def _delta_to_enhancements(kind: str, item: dict[str, Any]) -> dict[str, Any]:
    evidence = " / ".join(item.get("evidence_refs") or [])
    if kind == "nodes":
        return {
            "nodes": [{
                "type": item.get("type"),
                "name": item.get("name"),
                "description": item.get("description"),
                "confidence": item.get("confidence"),
                "evidence": evidence,
                "duplicate_of": item.get("duplicate_of") or "",
            }],
            "edges": [],
        }
    return {
        "nodes": [],
        "edges": [{
            "source_type": item.get("source_type"),
            "source_name": item.get("source_name"),
            "target_type": item.get("target_type"),
            "target_name": item.get("target_name"),
            "relation": item.get("relation"),
            "confidence": item.get("confidence"),
            "evidence": evidence,
        }],
    }


def apply_simulation_delta(project_id: str, delta_id: str) -> dict[str, Any]:
    # Reuses the same apply/status logic as the in-run apply path so a
    # reviewed delta behaves identically to apply_graph=True.
    from app.agents.simulation_agent import _apply_graph_enhancements_with_status
    from app.models.graph import TextChunk
    from app.utils.graph_promotion import classify_node_layers

    proj_dir = _project_dir(project_id)
    simulation = _load_json(proj_dir / "simulation.json", "Simulation not run yet")
    kind, item = _find_delta(simulation, delta_id)
    if item.get("status") != "proposed":
        raise SimulationDeltaError(409, f"Delta {delta_id} is already {item.get('status')}")

    graph = _load_graph(proj_dir)
    applied, statuses = _apply_graph_enhancements_with_status(
        graph, _delta_to_enhancements(kind, item)
    )
    status = (statuses["nodes"] or statuses["edges"])[0]
    item["status"] = status["status"]
    item["status_reason"] = status.get("status_reason", "")

    if applied["nodes_added"] or applied["edges_added"]:
        source_file_types: dict[str, str] = {}
        chunks_path = proj_dir / "chunks.json"
        if chunks_path.exists():
            chunks = [
                TextChunk(**c)
                for c in json.loads(chunks_path.read_text(encoding="utf-8"))
            ]
            source_file_types = {c.source_file: c.file_type for c in chunks}
        classify_node_layers(graph, source_file_types)
        _save_graph(proj_dir, graph)

    _refresh_summary(simulation)
    _persist_simulation(proj_dir, simulation)
    return {
        "delta": item,
        "applied": applied,
        "summary": simulation["graph_delta"]["summary"],
    }


def reject_simulation_delta(project_id: str, delta_id: str, reason: str = "") -> dict[str, Any]:
    proj_dir = _project_dir(project_id)
    simulation = _load_json(proj_dir / "simulation.json", "Simulation not run yet")
    _, item = _find_delta(simulation, delta_id)
    if item.get("status") not in ("proposed", "skipped"):
        raise SimulationDeltaError(409, f"Delta {delta_id} is already {item.get('status')}")

    item["status"] = "rejected"
    item["status_reason"] = reason or "Rejected by user review."
    _refresh_summary(simulation)
    _persist_simulation(proj_dir, simulation)
    return {"delta": item, "summary": simulation["graph_delta"]["summary"]}
```

- [ ] **Step 4: 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_services/test_simulation_delta.py -q`
Expected: 6 passed

- [ ] **Step 5: 커밋**

```bash
git add src/backend/app/services/simulation_delta.py src/backend/tests/test_services/test_simulation_delta.py
git commit -m "feat(sim): add apply/reject service for proposed simulation deltas"
```

---

### Task 5: delta 승인/거부 API 엔드포인트

**Files:**
- Modify: `src/backend/app/api/projects.py` (기존 `POST /projects/{id}/simulation/evidence` 근처)
- Test: `src/backend/tests/test_api/test_simulation_delta_api.py` (신규)

**Interfaces:**
- Produces: `POST /api/projects/{project_id}/simulation/delta/apply`, `POST /api/projects/{project_id}/simulation/delta/reject` — 요청 본문 `{"delta_id": str, "reason": str(옵션)}`, 응답은 Task 4 서비스 반환값 그대로
- Consumes: Task 4의 `apply_simulation_delta`, `reject_simulation_delta`, `SimulationDeltaError`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_api/test_simulation_delta_api.py` 신규 작성. TestClient/프로젝트 fixture 구성은 `tests/test_api/test_graph_merge_candidates.py`의 방식을 그대로 따르고, 프로젝트 데이터 준비는 Task 4의 `_write_project`와 동일한 내용을 사용:

```python
def test_apply_delta_endpoint_returns_applied_status(client, project):
    resp = client.post(
        f"/api/projects/{project}/simulation/delta/apply",
        json={"delta_id": "delta_node_001"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["delta"]["status"] == "applied"
    assert body["applied"]["nodes_added"] == 1


def test_apply_unknown_delta_returns_404(client, project):
    resp = client.post(
        f"/api/projects/{project}/simulation/delta/apply",
        json={"delta_id": "delta_node_999"},
    )
    assert resp.status_code == 404


def test_apply_twice_returns_409(client, project):
    client.post(f"/api/projects/{project}/simulation/delta/apply", json={"delta_id": "delta_node_001"})
    resp = client.post(f"/api/projects/{project}/simulation/delta/apply", json={"delta_id": "delta_node_001"})
    assert resp.status_code == 409


def test_reject_delta_endpoint_persists_reason(client, project):
    resp = client.post(
        f"/api/projects/{project}/simulation/delta/reject",
        json={"delta_id": "delta_edge_001", "reason": "근거 부족"},
    )
    assert resp.status_code == 200
    assert resp.json()["delta"]["status"] == "rejected"
```

- [ ] **Step 2: 실패 확인**

Run: `cd src/backend && python3 -m pytest tests/test_api/test_simulation_delta_api.py -q`
Expected: FAIL — 404 (라우트 없음)

- [ ] **Step 3: 엔드포인트 구현**

`app/api/projects.py`에 (BaseModel 요청 모델은 파일 내 기존 모델들 옆에):

```python
class SimulationDeltaAction(BaseModel):
    delta_id: str
    reason: str = ""


@router.post("/{project_id}/simulation/delta/apply")
async def apply_simulation_delta_endpoint(project_id: str, body: SimulationDeltaAction):
    from app.services.simulation_delta import SimulationDeltaError, apply_simulation_delta

    try:
        return apply_simulation_delta(project_id, body.delta_id)
    except SimulationDeltaError as exc:
        raise HTTPException(exc.status_code, exc.detail)


@router.post("/{project_id}/simulation/delta/reject")
async def reject_simulation_delta_endpoint(project_id: str, body: SimulationDeltaAction):
    from app.services.simulation_delta import SimulationDeltaError, reject_simulation_delta

    try:
        return reject_simulation_delta(project_id, body.delta_id, body.reason)
    except SimulationDeltaError as exc:
        raise HTTPException(exc.status_code, exc.detail)
```

(서비스 임포트는 API CLAUDE.md의 지연 임포트 규칙에 따라 함수 내부에서.)

- [ ] **Step 4: 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_api/test_simulation_delta_api.py tests/test_api/test_projects_api.py -q`
Expected: 전체 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/backend/app/api/projects.py src/backend/tests/test_api/test_simulation_delta_api.py
git commit -m "feat(sim): expose simulation delta apply/reject endpoints"
```

---

### Task 6: 프론트엔드 Delta 탭 승인/거부 UI

**Files:**
- Modify: `src/frontend/src/api/client.js:39-41` (projectsApi), `src/frontend/src/components/SimulationPanel.vue:176-198` (Graph Delta 탭)

**Interfaces:**
- Consumes: Task 5 엔드포인트, viewModel delta item의 `id` 필드(= `delta_id`, `simulationViewModel.js:382` 매핑 확인됨), 기존 `loadSimulation(showNotice)` / `emit('graph-updated', ...)` 패턴 (`SimulationPanel.vue:348, 374`)
- Produces: `projectsApi.applySimulationDelta(id, data)`, `projectsApi.rejectSimulationDelta(id, data)`

- [ ] **Step 1: client.js에 API 메서드 추가**

`resolveSimulationEvidence` 줄 아래:

```js
  applySimulationDelta: (id, data) => api.post(`/projects/${id}/simulation/delta/apply`, data),
  rejectSimulationDelta: (id, data) => api.post(`/projects/${id}/simulation/delta/reject`, data),
```

- [ ] **Step 2: SimulationPanel.vue delta 카드에 버튼 추가**

템플릿의 `.delta-item` 내부, `<EvidenceList ...>` 다음에:

```html
<div v-if="!readOnly && delta.status === 'proposed'" class="delta-actions">
  <el-button size="small" type="primary" :loading="deltaActionBusy === delta.id" @click="applyDelta(delta)">승인</el-button>
  <el-button size="small" :loading="deltaActionBusy === delta.id" @click="rejectDelta(delta)">거부</el-button>
</div>
```

script setup에 추가 (`props`의 프로젝트 ID prop 이름은 컴포넌트 상단 `defineProps` 선언을 확인해 그대로 사용 — 이하 `props.projectId`로 표기):

```js
const deltaActionBusy = ref(null)

async function applyDelta(delta) {
  deltaActionBusy.value = delta.id
  try {
    await projectsApi.applySimulationDelta(props.projectId, { delta_id: delta.id })
    ElMessage.success('그래프에 적용했습니다')
    await loadSimulation(false)
    const graphResponse = await projectsApi.getGraph(props.projectId)
    emit('graph-updated', graphResponse.data)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '적용에 실패했습니다')
  } finally {
    deltaActionBusy.value = null
  }
}

async function rejectDelta(delta) {
  deltaActionBusy.value = delta.id
  try {
    await projectsApi.rejectSimulationDelta(props.projectId, { delta_id: delta.id })
    await loadSimulation(false)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '거부에 실패했습니다')
  } finally {
    deltaActionBusy.value = null
  }
}
```

(`projectsApi.getGraph`가 client.js에 없으면 `onSimulationCompleted()`(369행)가 그래프를 다시 가져올 때 쓰는 기존 메서드명을 그대로 사용.) 스타일에 추가:

```css
.delta-actions { margin-top: 8px; display: flex; gap: 8px; }
```

status 태그(190행)는 3상태로 확장:

```html
<el-tag size="small" :type="delta.status === 'applied' ? 'success' : delta.status === 'rejected' ? 'danger' : 'warning'">{{ delta.status }}</el-tag>
```

- [ ] **Step 3: 검증**

Run: `cd src/frontend && npx vitest run && npm run build`
Expected: 기존 테스트 전체 PASS + 빌드 성공 (dgx02에는 GTK 미설치로 브라우저 확인 불가 — 빌드/테스트까지만)

- [ ] **Step 4: 커밋**

```bash
git add src/frontend/src/api/client.js src/frontend/src/components/SimulationPanel.vue
git commit -m "feat(sim): add delta approve/reject buttons to Graph Delta tab"
```

---

### Task 7: merge candidate 오탐 가드

**Files:**
- Modify: `src/backend/app/utils/merge_review.py`, `src/backend/app/config.py:58` 근처
- Test: `src/backend/tests/test_utils/test_merge_review.py`

**Interfaces:**
- Produces: `collect_merge_candidates(graph, threshold=None, denylist=None)` 시그니처 유지. 새 자격 규칙 — acronym variant, 정규화 containment(양쪽 정규화 이름이 4자 이상이고 한쪽이 다른 쪽의 부분 문자열), 또는 유사도 ≥ `config.MERGE_REVIEW_STRICT_THRESHOLD`. 원시 이름 중 짧은 쪽이 `config.MERGE_REVIEW_MIN_NAME_LEN` 미만이면 acronym variant만 허용. `threshold` 파라미터는 strict 임계값을 오버라이드.
- 새 config: `MERGE_REVIEW_STRICT_THRESHOLD: float = 0.93`, `MERGE_REVIEW_MIN_NAME_LEN: int = 4`. 기존 `MERGE_REVIEW_THRESHOLD`는 하위 호환을 위해 유지(더 이상 참조하지 않음을 주석으로 명시).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_utils/test_merge_review.py`에 추가 (기존 테스트의 그래프 구성 방식 재사용):

```python
def _pairs(candidates):
    return {frozenset({c["keep_id"], c["candidate_id"]}) for c in candidates}


def test_short_name_pairs_require_acronym_match():
    g = nx.DiGraph()
    g.add_node("Skill:AI", type="Skill", name="AI")
    g.add_node("Skill:AMI", type="Skill", name="AMI")
    assert collect_merge_candidates(g) == []


def test_single_char_variant_metrics_not_candidates():
    g = nx.DiGraph()
    g.add_node("Skill:cpWER", type="Skill", name="cpWER")
    g.add_node("Skill:cpCER", type="Skill", name="cpCER")
    assert collect_merge_candidates(g) == []


def test_similar_but_semantically_distinct_words_not_candidates():
    g = nx.DiGraph()
    g.add_node("Skill:simulation", type="Skill", name="simulation")
    g.add_node("Skill:estimation", type="Skill", name="estimation")
    assert collect_merge_candidates(g) == []


def test_containment_pairs_still_surface():
    g = nx.DiGraph()
    g.add_node("Skill:SOT fine-tuning", type="Skill", name="SOT fine-tuning")
    g.add_node("Skill:Fine-Tuning", type="Skill", name="Fine-Tuning")
    g.add_node(
        "Achievement:2024.08 Semester High Honors",
        type="Achievement", name="2024.08 Semester High Honors",
    )
    g.add_node(
        "Achievement:Semester High Honors",
        type="Achievement", name="Semester High Honors",
    )
    pairs = _pairs(collect_merge_candidates(g))
    assert frozenset({"Skill:SOT fine-tuning", "Skill:Fine-Tuning"}) in pairs
    assert frozenset({
        "Achievement:2024.08 Semester High Honors",
        "Achievement:Semester High Honors",
    }) in pairs


def test_different_urls_not_candidates():
    g = nx.DiGraph()
    g.add_node(
        "Publication:https://arxiv.org/html/2603.02128v1",
        type="Publication", name="https://arxiv.org/html/2603.02128v1",
    )
    g.add_node(
        "Publication:https://arxiv.org/html/2602.19623v1",
        type="Publication", name="https://arxiv.org/html/2602.19623v1",
    )
    assert collect_merge_candidates(g) == []
```

- [ ] **Step 2: 실패 확인**

Run: `cd src/backend && python3 -m pytest tests/test_utils/test_merge_review.py -q`
Expected: 신규 오탐 테스트 5개 중 `containment` 제외 4개 FAIL (현재는 후보로 수집됨)

- [ ] **Step 3: 구현**

`app/config.py`의 `MERGE_REVIEW_THRESHOLD` 아래에 추가:

```python
    # MERGE_REVIEW_THRESHOLD is kept for backward compat; candidate collection
    # now uses the strict threshold + containment/acronym rules below.
    MERGE_REVIEW_STRICT_THRESHOLD: float = 0.93
    MERGE_REVIEW_MIN_NAME_LEN: int = 4
```

`merge_review.py`에 헬퍼 추가:

```python
def _normalized(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _is_containment(a: str, b: str) -> bool:
    na, nb = _normalized(a), _normalized(b)
    if min(len(na), len(nb)) < 4:
        return False
    return na != nb and (na in nb or nb in na)
```

`collect_merge_candidates`의 자격 판정(기존 64-68행)을 교체:

```python
                if threshold is None:
                    strict = config.MERGE_REVIEW_STRICT_THRESHOLD
                else:
                    strict = threshold
                name_a = str(data_a.get("name", "")).strip()
                name_b = str(data_b.get("name", "")).strip()

                acronym = are_acronym_variants(name_a, name_b)
                if min(len(name_a), len(name_b)) < config.MERGE_REVIEW_MIN_NAME_LEN and not acronym:
                    continue
                containment = _is_containment(name_a, name_b)
                sim = _similarity(name_a, name_b)
                if not (acronym or containment or sim >= strict):
                    continue
                confidence = 1.0 if acronym else round(max(sim, 0.9) if containment else sim, 4)
```

(함수 서두의 `if threshold is None: threshold = config.MERGE_REVIEW_THRESHOLD` 두 줄은 삭제. `strict` 계산은 루프 밖 서두에 두는 것이 맞음 — 위 코드 블록에서 위치만 함수 서두로 이동.)

- [ ] **Step 4: 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_utils/test_merge_review.py tests/test_api/test_graph_merge_candidates.py -q`
Expected: 전체 PASS. 기존 테스트 중 느슨한 0.8 임계에 의존하는 것이 있으면 새 규칙(containment/strict)에 맞는 이름 쌍으로 수정하되, 수정 사유를 커밋 메시지 본문에 기록.

- [ ] **Step 5: 커밋**

```bash
git add src/backend/app/utils/merge_review.py src/backend/app/config.py src/backend/tests/test_utils/test_merge_review.py
git commit -m "fix(merge): require containment/acronym or strict similarity for merge candidates"
```

---

### Task 8: debate 합의/쟁점 집계

**Files:**
- Modify: `src/backend/app/agents/simulation_agent.py` — synthesis 프롬프트 JSON 스키마(412-436행), `_normalize_legacy_result`(441행), `_build_debate`(659행), `build_simulation_result_v2` 호출부(498행)
- Test: `src/backend/tests/test_agents/test_simulation_agent.py`

**Interfaces:**
- Produces: `_build_debate(timeline, personas, synthesis: dict | None = None) -> dict` — `agreements`/`disagreements`는 synthesis에서, `unresolved_questions`는 synthesis 목록 + 턴 레벨 중복 제거 롤업(최대 20개). legacy result에 `debate_synthesis` 키 추가.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_build_debate_aggregates_synthesis_and_turn_questions():
    from app.agents.simulation_agent import _build_debate

    timeline = [
        {"turn_id": "turn_001", "round": 1, "agent_id": "agent_1",
         "observation": "관찰1", "proposal": "제안1", "evidence_refs": [],
         "unresolved_questions": ["Q-턴1", "Q-공통"]},
        {"turn_id": "turn_002", "round": 1, "agent_id": "agent_2",
         "observation": "관찰2", "proposal": "제안2", "evidence_refs": [],
         "unresolved_questions": ["Q-공통", "Q-턴2"]},
    ]
    personas = [{"id": "agent_1"}, {"id": "agent_2"}]
    synthesis = {
        "agreements": ["뉴로-심볼릭 분리 채택"],
        "disagreements": ["프레이밍 레이어 허용 여부"],
        "unresolved_questions": ["Q-합성"],
    }

    debate = _build_debate(timeline, personas, synthesis)

    assert debate["agreements"] == ["뉴로-심볼릭 분리 채택"]
    assert debate["disagreements"] == ["프레이밍 레이어 허용 여부"]
    assert debate["unresolved_questions"] == ["Q-합성", "Q-턴1", "Q-공통", "Q-턴2"]


def test_build_debate_without_synthesis_rolls_up_turn_questions():
    from app.agents.simulation_agent import _build_debate

    timeline = [
        {"turn_id": "turn_001", "round": 1, "agent_id": "agent_1",
         "observation": "관찰", "proposal": "제안", "evidence_refs": [],
         "unresolved_questions": ["Q1"]},
    ]
    debate = _build_debate(timeline, [{"id": "agent_1"}])
    assert debate["unresolved_questions"] == ["Q1"]
    assert debate["agreements"] == []
```

- [ ] **Step 2: 실패 확인**

Run: `cd src/backend && python3 -m pytest tests/test_agents/test_simulation_agent.py -q -k build_debate`
Expected: FAIL — `unresolved_questions`가 빈 배열

- [ ] **Step 3: 구현**

(a) `_build_debate` 교체:

```python
def _build_debate(
    timeline: list[dict[str, Any]],
    personas: list[dict[str, Any]],
    synthesis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    persona_ids = {persona["id"] for persona in personas}
    turns = []
    for idx, item in enumerate(timeline or []):
        speaker_id = str(item.get("agent_id") or item.get("speaker_id") or "")
        turns.append({
            "turn_id": str(item.get("turn_id") or f"turn_{idx + 1:03d}"),
            "round": int(item.get("round") or idx + 1),
            "speaker_id": speaker_id,
            "stance": "review" if speaker_id in persona_ids else "",
            "claim": str(item.get("observation") or item.get("claim") or ""),
            "evidence_refs": _evidence_refs(item.get("evidence_refs") or item.get("evidence")),
            "proposal": str(item.get("proposal") or item.get("recommendation") or ""),
            "responds_to": str(item.get("responds_to") or ""),
            "had_previous_context": bool(item.get("had_previous_context")),
            "is_fallback": bool(item.get("is_fallback")),
            "unresolved_questions": [
                str(value)
                for value in item.get("unresolved_questions", [])
                if value
            ],
        })

    synthesis = synthesis or {}
    unresolved: list[str] = [
        str(q).strip() for q in synthesis.get("unresolved_questions", []) if str(q).strip()
    ]
    for turn in turns:
        for question in turn["unresolved_questions"]:
            if question not in unresolved:
                unresolved.append(question)

    return {
        "turns": turns,
        "agreements": [str(a).strip() for a in synthesis.get("agreements", []) if str(a).strip()],
        "disagreements": [str(d).strip() for d in synthesis.get("disagreements", []) if str(d).strip()],
        "unresolved_questions": unresolved[:20],
    }
```

(b) `_normalize_legacy_result` 반환 dict에 추가:

```python
            "debate_synthesis": result.get("debate_synthesis", {}),
```

(c) `build_simulation_result_v2` 498행 교체:

```python
    debate = _build_debate(
        legacy_result.get("timeline", []),
        v2_personas,
        legacy_result.get("debate_synthesis"),
    )
```

(d) synthesis 프롬프트 JSON 스키마에서 `"cv_improvements"` 블록 앞에 추가:

```
  "debate_synthesis": {
    "agreements": ["persona들이 합의한 사항"],
    "disagreements": ["끝까지 갈린 쟁점"],
    "unresolved_questions": ["추가 검증이 필요한 질문"]
  },
```

- [ ] **Step 4: 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_agents/test_simulation_agent.py -q`
Expected: 전체 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/backend/app/agents/simulation_agent.py src/backend/tests/test_agents/test_simulation_agent.py
git commit -m "feat(sim): aggregate debate agreements, disagreements, unresolved questions"
```

---

### Task 9: career layer 전파 제한 (USES_SKILL)

**Files:**
- Modify: `src/backend/app/utils/graph_promotion.py:20-30` (`_OWNERSHIP_RELATIONS`), `:73-86` (전파 루프)
- Test: `src/backend/tests/test_utils/test_graph_promotion.py`

**Interfaces:**
- Produces: `classify_node_layers` 시그니처 불변. 동작 변경 — `USES_SKILL` 엣지는 상대가 user Person 노드일 때만 career 전파. 새 상수 `_USER_ONLY_RELATIONS = {"USES_SKILL"}`.
- Consumes: `_load_user_person_ids(graph)` (기존, graph_restructure)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_utils/test_graph_promotion.py`에 추가 (user Person 인식 방식은 같은 파일의 기존 테스트가 쓰는 fixture 구성을 그대로 따를 것 — `_load_user_person_ids`가 user를 인식하게 만드는 노드 속성 포함):

```python
def test_uses_skill_from_user_person_promotes_to_career():
    graph = _graph_with_user_person()  # 기존 테스트와 동일한 user Person fixture
    graph.add_node("Skill:Python", type="Skill", name="Python")
    graph.add_edge(USER_PERSON_ID, "Skill:Python", relation="USES_SKILL")

    classify_node_layers(graph, {})

    assert graph.nodes["Skill:Python"]["layer"] == "career"


def test_uses_skill_from_career_project_stays_knowledge():
    graph = _graph_with_user_person()
    # user가 DEVELOPED로 소유한 career Project
    graph.add_node("Project:MyProj", type="Project", name="MyProj")
    graph.add_edge(USER_PERSON_ID, "Project:MyProj", relation="DEVELOPED")
    # 그 Project가 USES_SKILL로 참조하는, 논문에서만 언급된 스킬
    graph.add_node("Skill:CIB", type="Skill", name="CIB")
    graph.add_edge("Project:MyProj", "Skill:CIB", relation="USES_SKILL")

    classify_node_layers(graph, {})

    assert graph.nodes["Project:MyProj"]["layer"] == "career"
    assert graph.nodes["Skill:CIB"]["layer"] == "knowledge"
```

- [ ] **Step 2: 실패 확인**

Run: `cd src/backend && python3 -m pytest tests/test_utils/test_graph_promotion.py -q`
Expected: `test_uses_skill_from_career_project_stays_knowledge` FAIL (현재는 career로 전파)

- [ ] **Step 3: 구현**

`graph_promotion.py` 상수 교체:

```python
_OWNERSHIP_RELATIONS = {
    "DEVELOPED",
    "LED_BY",
    "WORKED_AT",
    "HAS_ROLE",
    "ACHIEVED",
    "PARTICIPATED_IN",
    "COLLABORATED_WITH",
    "MENTORED_BY",
}

# USES_SKILL is deliberately separate: propagating it through career Projects
# flooded the career layer (108/168 Skills in the 2026-06-28 build), so skill
# usage only counts as career evidence when the user Person node is on the edge.
_USER_ONLY_RELATIONS = {"USES_SKILL"}
```

전파 루프(80-86행) 교체:

```python
            for neighbor in neighbors:
                if layers.get(neighbor) != CAREER_LAYER:
                    continue
                relation = _edge_relation(graph, neighbor, node_id)
                if relation in _OWNERSHIP_RELATIONS or (
                    relation in _USER_ONLY_RELATIONS and neighbor in user_ids
                ):
                    layers[node_id] = CAREER_LAYER
                    changed = True
                    break
```

- [ ] **Step 4: 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_utils/test_graph_promotion.py -q`
Expected: 전체 PASS. 기존 테스트가 career Project 경유 USES_SKILL 전파를 기대하고 있었다면 새 정책에 맞게 기대값을 수정하고 커밋 본문에 사유 기록.

- [ ] **Step 5: 커밋**

```bash
git add src/backend/app/utils/graph_promotion.py src/backend/tests/test_utils/test_graph_promotion.py
git commit -m "fix(graph): restrict USES_SKILL career propagation to user person edges"
```

---

### Task 10: 전체 검증 + 핸드오프 문서 갱신

**Files:**
- Modify: `docs/claude-code-handoff.md`

- [ ] **Step 1: 백엔드 전체 스위트**

Run: `cd src/backend && python3 -m pytest tests/ -q`
Expected: 전체 PASS (기준선 526 passed + 신규 테스트). 실패 시 해당 Task로 돌아가 수정.

- [ ] **Step 2: 프론트엔드 검증**

Run: `cd src/frontend && npx vitest run && npm run build`
Expected: 11 passed + 빌드 성공

- [ ] **Step 3: 실데이터 스모크 테스트 (선택, project 21fc2ce5)**

백엔드를 8001 포트로 띄우고:

```bash
curl -s -X POST localhost:8001/api/projects/21fc2ce5/simulation/delta/reject \
  -H 'Content-Type: application/json' \
  -d '{"delta_id": "delta_node_002", "reason": "기존 Skill:Cross-Impact Balance와 중복"}' | python3 -m json.tool
```

Expected: `delta.status == "rejected"`, `simulation.json`과 `simulations/sim_20260628_152220_230888.json` 모두 갱신됨.

- [ ] **Step 4: 핸드오프 문서 갱신**

`docs/claude-code-handoff.md`의 "Implemented Recently"에 이번 작업 요약(6개 개선 + 검증 결과)을 추가하고, "Known Gaps"에서 해결된 항목(merge 후보 오탐, career layer 선호 미구현 관련 서술)을 갱신. "Recommended Next Work"에 다음 후보 기록:
- 다음 시뮬레이션 실행에서 evidence ref 해석률 실측 (기대: bare 노드 ref 전부 해석)
- `ISOLATED_REEXTRACT_ENABLED=true` 재실행 품질 점검 (기존 항목 유지)
- delta 일괄 승인 UI 및 rejected delta 되돌리기 검토

- [ ] **Step 5: 커밋**

```bash
git add docs/claude-code-handoff.md
git commit -m "docs(handoff): simulation delta review flow and graph quality guards shipped"
```
