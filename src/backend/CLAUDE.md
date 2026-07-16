# Backend — ProjectOS

FastAPI 백엔드. 9개 에이전트 + 10개 API 라우터.

## 명령어

```bash
# 설치
pip install -e ".[dev]"

# 실행 (src/backend/ 에서)
python3 run.py
# 또는
uvicorn app.main:app --reload

# 테스트
python3 -m pytest tests/ -v

# 특정 테스트
python3 -m pytest tests/test_agents/test_parser_agent.py -v
```

## 패키지 구조

```
app/
  agents/     — 9개 (parser, ontology, graph_builder, claude_task_graph_builder, profile, obsidian_writer, query, analysis, simulation)
  api/        — 10개 라우터 (api/CLAUDE.md 참고)
  models/     — 데이터 모델 (graph.py, project.py, vault.py)
  services/   — 16개 (project_store, task_manager, retrieval_index, graph_context, capture_context, digest, watcher 등)
  utils/      — 25개 (llm_client, file_parser, embedding_client, hybrid_retrieval, entity_*, graph_* 등)
  config.py   — pydantic_settings BaseSettings 싱글톤
  main.py     — FastAPI 앱, CORS, 라우터 등록
```

## 에이전트 파이프라인 순서

ParserAgent → OntologyAgent → GraphBuilderAgent → ProfileAgent → ObsidianWriterAgent

QueryAgent는 독립 실행 (채팅 엔드포인트에서 호출).

## 환경 변수

`src/backend/` 에 `.env` 파일 생성 (`.env.example` 참고):
- `LLM_API_KEY` — OpenAI 호환 API 키 (필수)
- `LLM_BASE_URL` — 기본값 `https://api.openai.com/v1`
- `LLM_MODEL` — 기본값 `gpt-4o`
- `VAULT_DIR` — 기본값 `./vault` (Syncthing 절대경로 사용 권장)
- `PROJECTS_DIR` — 기본값 `./projects`
