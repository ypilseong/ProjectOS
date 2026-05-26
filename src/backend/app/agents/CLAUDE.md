# Agents — ProjectOS

6개 독립 에이전트. 공통 기반 클래스 없음. 각각 `run()` 또는 `stream()` 메서드.

## 에이전트 목록

| 파일 | 클래스 | 주요 메서드 |
|------|--------|-------------|
| parser_agent.py | ParserAgent | `run(file_paths, file_type) → list[TextChunk]` |
| ontology_agent.py | OntologyAgent | `run(chunks) → Ontology` |
| graph_builder_agent.py | GraphBuilderAgent | `run(chunks, ontology, incremental, graph_path) → nx.DiGraph` |
| profile_agent.py | ProfileAgent | `run(graph) → list[CareerProfile]` |
| obsidian_writer_agent.py | ObsidianWriterAgent | `run(graph, profiles, vault_path, delta)` |
| query_agent.py | QueryAgent | `stream(question, graph, chunks)` async generator |

## LLM 호출 패턴

```python
from app.utils.llm_client import llm_client

# JSON 응답
result: dict = await llm_client.chat_json(prompt)

# 스트리밍
async for token in llm_client.stream(prompt):
    yield token
```

## 고정 타입 목록

엔티티 10개: Person, Project, Skill, Organization, Publication, Technology, Role, Achievement, Event, Institution

관계 10개: WORKED_AT, DEVELOPED, USES_SKILL, AUTHORED, COLLABORATED_WITH, ACHIEVED, PARTICIPATED_IN, PUBLISHED_AT, MENTORED_BY, LED_BY

## Fuzzy Matching

`difflib.SequenceMatcher` — threshold `config.FUZZY_MATCH_THRESHOLD` (기본 0.85).
타입 범위 내 매칭만 수행 (Person ↔ Person 등).

## 한국어 주의사항

`QueryAgent._find_relevant_chunks()` 는 단어 집합 교차가 아닌 substring 매칭 사용.
이유: 한국어 조사 ("Python을", "Python이") 때문에 단어 분리 시 매칭 실패.
