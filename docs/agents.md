# ProjectOS — Agent Documentation

## Agent Pipeline

파일 업로드 → ParserAgent → OntologyAgent → GraphBuilderAgent → ProfileAgent → ObsidianWriterAgent

QueryAgent는 독립적으로 채팅 질의 처리.

## Agents

- **ParserAgent**: PDF/DOCX/TXT → TextChunk 리스트
- **OntologyAgent**: 청크 샘플 → LLM → 엔티티/관계 타입 정의
- **GraphBuilderAgent**: 청크 + 온톨로지 → NetworkX DiGraph (fuzzy dedup + incremental)
- **ProfileAgent**: Person 노드 BFS → LLM → CareerProfile
- **ObsidianWriterAgent**: 그래프 → Obsidian vault (.md + wikilinks + canvas)
- **QueryAgent**: 질문 → BFS 그래프 검색 → LLM → SSE 스트리밍 답변

See design spec: docs/superpowers/specs/2026-05-24-projectos-design.md
