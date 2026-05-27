# Claude Code Handoff

Last updated: 2026-05-27

## Current Objective

Category 허브 노드 구조 완료. 다음 작업 후보:
1. Skill/Project cross-연결 강화 — LLM 추출 프롬프트에 "어떤 프로젝트에서 어떤 스킬 사용" 관계 명시
2. Skill/Technology 타입 교차 중복 병합 (NLP ↔ NLP, AI ↔ Artificial Intelligence)
3. 추출 프롬프트에 사용자 이름 컨텍스트 주입 (동일 인물 중복 추출 방지)

## Completed In This Session (2026-05-27 Category Hub Restructure)

### 변경 내역

- `app/utils/graph_restructure.py` (신규): `add_category_hubs()` 함수
  - LLM 추출 후 후처리로 Category 허브 노드 삽입
  - 허브 타입: Achievements, Skills, Technologies, Projects, Roles, Organizations, Institutions, Events, Publications, People
  - user.json 기반으로 사용자 본인 Person 식별 → 다른 Person은 `Category:People`로 묶음
  - Person → Category(HAS) → Individual(원래 relation 유지)
  - Person → Person 직접 연결 → Category:People 경유로 전환
  - Skill → Project 등 cross-type 연결은 그대로 보존
- `app/api/graph.py`: `semantic_dedup()` 후 `add_category_hubs()` 호출
- `src/frontend/src/components/GraphView.vue`:
  - `Category` 타입 색상 추가 (`#34495E`, 다크 그레이)
  - Category 노드 반지름 12 (Person 14, 일반 10)
  - Category 노드 텍스트 길이 10자로 확장
- `tests/test_utils/test_graph_restructure.py` (신규): 9개 테스트

### 검증

- `python3 -m pytest tests/ -v` → **105 passed**
- 그래프 재빌드 결과: 노드 173개, 엣지 100개
  - 양필성 직접 연결: 7개 (Category 허브만) — 이전 ~40개 대비 대폭 감소
  - Category 허브: Skills(7), Projects(5), Roles(5), Achievements(3), Organizations(3), Technologies(3), Events(1)

### 알려진 한계

- Skill → Project cross-연결이 거의 없음 (LLM이 현재 Person 중심 관계만 추출)
  → 다음 작업: GraphBuilderAgent 프롬프트에 Skill/Technology ↔ Project 관계 추출 명시 필요

## Completed In This Session (2026-05-27 User Person Merge)

### 변경 내역

- `app/utils/semantic_dedup.py`: `merge_user_persons()` 함수 추가
  - `USER_CONFIG_PATH`(user.json)에서 `name` + `display_name` 두 변형 로드
  - 그래프의 Person 노드 중 이름이 변형에 매칭되는 노드를 모두 단일 canonical 노드로 병합
  - canonical 선택 기준: degree 높은 쪽, 동점 시 display_name 매칭 우선
  - user.json 없거나 변형이 1개뿐이면 무조건 스킵
- `app/api/graph.py` `_run_graph()`: `semantic_dedup()` 호출 직전에 `merge_user_persons()` 추가 (progress 71%)
- `tests/test_utils/test_semantic_dedup.py`: 4개 테스트 추가
  - `test_merge_user_persons_merges_name_and_display_name` — 병합 + 엣지 리다이렉트
  - `test_merge_user_persons_skips_when_no_user_json` — user.json 없으면 스킵
  - `test_merge_user_persons_skips_when_only_one_variant` — 변형 1개면 스킵
  - `test_merge_user_persons_does_not_touch_other_persons` — 다른 Person 노드 영향 없음
- `CLAUDE.md` Key Rules: 작업 완료 후 handoff 문서 업데이트 규칙 추가

### 임베딩 URL 버그 수정

- `.env` 및 `.env.example`: `EMBEDDING_BASE_URL=http://localhost:14004` → `http://localhost:14004/v1`
  - OpenAI SDK가 `{base_url}/embeddings`를 호출하는데 Infinity 서버 경로가 `/v1/embeddings`여서 404 발생하던 문제
  - 수정 후 semantic dedup 정상 동작 확인 (5개 노드 병합: LLM 개발, Project 2개, Role 1개)

### 검증

- `python3 -m pytest tests/ -v` → **96 passed**
- 그래프 재빌드 결과: 노드 187개, 엣지 98개
  - Person: `Pilseong Yang` → `양필성` 병합 확인
  - Semantic dedup: `LLM development`←`LLM 개발`, `Team Leader`←`팀 리더` 등 5개 병합

### Claude API 대체 가능성 확인

현재 `LLMClient`는 `openai.AsyncOpenAI`에 `base_url`만 바꿔서 사용하므로, Anthropic OpenAI 호환 엔드포인트로 env 3개만 교체하면 Claude로 전환 가능:
```
LLM_BASE_URL=https://api.anthropic.com/v1
LLM_API_KEY=<anthropic_api_key>
LLM_MODEL=claude-sonnet-4-6
```
단, `response_format={"type": "json_object"}` (chat_json에서 사용) 호환 여부 실사용 테스트 필요.

## Completed In This Session (2026-05-26 Semantic Dedup + Embedding Serving)

### Embedding Model Serving (`../embedding-model-serving/`)

- 신규 프로젝트 `/raid/home/a202121010/workspace/projects/embedding-model-serving/` 생성
- `docker-compose.yml`: Infinity 서버 (`michaelf34/infinity:latest`), BGE-M3 로컬 경로 마운트
  - GPU 4 (`CUDA_DEVICE=4`), 포트 14004 (`HOST_PORT=14004`)
  - 볼륨: `${MODELS_DIR}:/models`
  - 커맨드: `v2 --model-id /models/BAAI/bge-m3 --dtype float16 --batch-size 32 --port 7997 --engine torch --url-prefix /v1`
- BGE-M3 모델 다운로드: `/raid/home/a202121010/workspace/models/BAAI/bge-m3/`
- 컨테이너 `embedding-bge-m3` 실행 중. 확인:
  - `curl http://localhost:14004/v1/models` → `BAAI/bge-m3` 반환
  - `curl http://localhost:14004/v1/embeddings` → 한국어/영어 임베딩 정상
- `.env`: `MODELS_DIR=/raid/home/a202121010/workspace/models`

### Semantic Deduplication (ProjectOS Backend)

- `app/config.py`: `EMBEDDING_BASE_URL=""`, `EMBEDDING_MODEL="BAAI/bge-m3"`, `SEMANTIC_DEDUP_THRESHOLD=0.88` 추가
- `.env`: `EMBEDDING_BASE_URL=http://localhost:14004`, `EMBEDDING_MODEL=BAAI/bge-m3`, `SEMANTIC_DEDUP_THRESHOLD=0.88` 추가
- `.env.example`: 임베딩 설정 섹션 추가
- `app/utils/embedding_client.py` (신규): OpenAI SDK 기반 `/v1/embeddings` 클라이언트
- `app/utils/semantic_dedup.py` (신규):
  - 같은 타입 노드 이름을 BGE-M3로 임베딩 → 코사인 유사도 ≥ threshold 쌍을 Union-Find로 그룹화
  - Person 타입 제외 (사람은 자동 병합 안 함)
  - Canonical 선택 기준: 연결도 높은 노드, 동점 시 이름 짧은 쪽
  - `EMBEDDING_BASE_URL` 미설정 시 완전 스킵
  - `_merge_node()`: 엣지 리다이렉트 + source_files 합집합 + 중복 노드 제거
- `app/api/graph.py` `_run_graph()`: 그래프 저장 전 `semantic_dedup()` 호출 (progress 71%)
- `pyproject.toml`: `numpy>=1.26` 의존성 추가 (numpy 2.4.6 설치됨)
- `tests/test_utils/test_semantic_dedup.py` (신규): 7개 테스트
  - `test_merge_node_redirects_edges` — 엣지 리다이렉트 확인
  - `test_merge_node_does_not_duplicate_existing_edge` — 중복 엣지 방지
  - `test_dedup_merges_similar_same_type_nodes` — NLP/자연어처리 병합
  - `test_dedup_skips_person_nodes` — Person 타입 스킵
  - `test_dedup_skips_when_no_embedding_url` — URL 미설정 시 스킵
  - `test_dedup_does_not_merge_different_types` — 타입 다르면 병합 안 함
  - `test_dedup_transitive_merge` — A≈B, B≈C → 3개 → 1개

### 검증

- `python3 -m pytest tests/ -v` → **92 passed**
- 백엔드 포트 8001 재시작 완료

## Completed In This Session (2026-05-26 Graph Visualization Fix)

- `src/views/ProjectDetail.vue` `onMounted()`: 페이지 새로고침/직접 접속 시 그래프가 표시 안 되는 버그 수정
  - 기존: status만 읽고 graphData 미로드, activeStep = 0 유지
  - 수정: status 별 분기
    - `ready` → `getGraph()` + `getOntology()` 병렬 로드 → `activeStep = 3`
    - `building` → `activeStep = 2` + SSE 재연결
    - `parsed` / `ontology` → `activeStep = 1`

## Completed In This Session (2026-05-26 User Config + Profile Refactor)

커밋 범위: `050bf23` → `0bcaa63` (10개 커밋)

### 변경 내역

**Backend**

- `app/config.py`: `USER_CONFIG_PATH: str = "./user.json"` 추가
- `app/api/user.py` (신규): `GET /api/user` (없으면 404, 손상 시 500), `POST /api/user` (이름 저장)
- `app/main.py`: `user_router` 등록 (`/api/user`)
- `app/agents/obsidian_writer_agent.py`: `profiles: list[CareerProfile] | None = None` (optional)
- `app/api/graph.py` `_run_graph()`: ProfileAgent 호출 제거 → graph.json + vault만 생성. 진행률 30→70 (추출), 72→97 (vault)
- `app/agents/profile_agent.py`: `person_ids: list[str] | None = None` 파라미터 추가 — 지정된 노드만 프로파일링
- `app/api/projects.py`: `GET/POST /{id}/profiles` 추가. `_run_profiles()` — user.json 로드 → fuzzy match (threshold 0.7) → ProfileAgent → profiles.json → vault delta 업데이트. `project.status = FAILED` on error
- `app/agents/graph_builder_agent.py`: Role 추출 규칙을 공식 직함/직위로 제한 (발표자, 사회자, 데이터 검수 등 제외)
- `app/api/graph.py`: `GET /{id}/profiles` 제거 (projects.py로 이동)
- `tests/conftest.py`: `USER_CONFIG_PATH` 테스트 격리 추가
- `tests/test_api/test_user_api.py` (신규): 5개 테스트 (GET 404, GET 500 손상, POST 저장, GET 반환, display_name 기본값)
- `tests/test_agents/test_profile_agent.py`: 2개 테스트 추가 (person_ids 필터, None 시 전체)
- `tests/test_api/test_projects_api.py`: 3개 테스트 추가 (GET 404, POST 400 그래프 없음, POST 200 task_id)

**Frontend**

- `src/api/client.js`: `userApi` (`get`, `set`), `projectsApi.getProfiles`, `projectsApi.runProfiles` 추가
- `src/components/UserSetupModal.vue` (신규): 최초 방문 이름 입력 모달 (el-dialog, 이름/영문 이름, 저장)
- `src/views/HomeView.vue`: `onMounted`에서 `userApi.get()` → 404이면 UserSetupModal 표시
- `src/views/ProjectDetail.vue`: 커리어 프로필 섹션 추가 — 미생성 시 "프로필 생성" 버튼 (status=ready 필요), 생성 중 ProgressPanel, 완료 후 "프로필 보기"/"재생성"

### 검증

- `cd src/backend && python3 -m pytest tests/ -v` → **85 passed**
- `cd src/frontend && npm run build` → 성공 (large chunk 경고만)

## Previously Completed

- Added Analysis API tests to `src/backend/tests/test_api/test_projects_api.py`.
- Added Analysis API endpoints to `src/backend/app/api/projects.py`:
  - `POST /api/projects/{project_id}/analysis`
  - `GET /api/projects/{project_id}/analysis`
- Added background `_run_analysis()` execution:
  - loads `chunks.json`
  - optionally loads `graph.json`
  - runs `AnalysisAgent`
  - writes `analysis.json`
  - updates task progress via `task_manager`
- Verified targeted backend tests:
  - `cd src/backend && python3 -m pytest tests/test_api/test_projects_api.py::test_get_analysis_returns_404_when_not_run tests/test_api/test_projects_api.py::test_run_analysis_returns_400_when_no_chunks tests/test_api/test_projects_api.py::test_run_analysis_returns_task_id_when_chunks_exist -v`
  - Result: `3 passed`
- Updated frontend API client in `src/frontend/src/api/client.js`:
  - `projectsApi.runAnalysis(id)`
  - `projectsApi.getAnalysis(id)`
  - `globalApi.getGraph()`
- Extended `src/frontend/src/components/GraphView.vue`:
  - project-level color support via `projectColors`
  - project-name legend support via `projectNames`
  - global graph click callback via `onProjectNodeClick`
- Updated `src/frontend/src/views/HomeView.vue`:
  - added `프로젝트 목록` / `전체 그래프` tabs
  - loads `/api/graph/global` lazily when the global graph tab is opened
  - passes project colors/names into `GraphView`
- Added `src/frontend/src/components/AnalysisDrawer.vue`:
  - shows analysis summary
  - lists issues by severity
  - shows improved markdown draft
- Updated `src/frontend/src/views/ProjectDetail.vue`:
  - added document analysis sidebar section
  - supports analysis task progress via `ProgressPanel`
  - opens `AnalysisDrawer` after completion
  - exposes `증분 업데이트 시작` when an existing graph is present
- Updated `src/backend/app/services/task_manager.py`:
  - persists tasks to `PROJECTS_DIR/.tasks.json`
  - reloads persisted tasks on process start
- Refined graph extraction prompt behavior after MiroFish review:
  - removed the previously added `Keyword` and `Concept` entity types
  - removed `HAS_KEYWORD` and `RELATED_TO`
  - kept chunks as internal input only; chunks are not graph nodes
  - important keyword-like items are now classified into the most specific existing type such as `Skill`, `Technology`, `Project`, `Publication`, or `Achievement`
  - ontology and graph extraction prompts are written in English, while extracted entity names may preserve Korean, English, or mixed Korean/English source text
- Updated docs visible in-app/about-agent notes back to 10 fixed entity types and 10 relation types.
- Restarted local serving after updates:
  - Backend: `uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload`
  - Frontend: `npm run dev -- --host 0.0.0.0 --port 5174`
  - Backend health: `http://localhost:8001/health` returned `{"status":"ok"}`
  - Frontend root: `http://localhost:5174/` returned `HTTP 200`
- Temporary serving-only change:
  - `src/frontend/vite.config.js` proxy now points to `http://localhost:8001`
  - This matches dgx02 runtime notes. Decide whether to keep or revert before commit.
- Runtime log/status follow-up:
  - Added file logging via `app.utils.logger.configure_logging()`.
  - Runtime logs now write to project-root `logs/projectos.log`.
  - `LOG_DIR` default is `../../logs` relative to `src/backend`, so uvicorn `--reload` does not watch the log file.
  - Uvicorn access/error logs are attached to the file log.
  - Removed 115 test-created project directories from `src/backend/projects`.
  - Remaining project list contains only `b6461d62` (`cv`, description `KAIST CV`).
  - Marked stale ontology task as `failed` because the backend was started without `LLM_API_KEY`.
  - Added pytest filesystem isolation in `src/backend/tests/conftest.py` so future tests do not create real projects.
- LLM API key behavior:
  - `LLMClient` now passes a dummy `"not-needed"` key when `LLM_API_KEY` is empty.
  - This supports OpenAI-compatible local LLM servers that do not require credentials.
  - If `LLM_BASE_URL` remains `https://api.openai.com/v1`, a real key is still required by the remote service.
  - `.env.example` now documents local server configuration.
  - Created ignored runtime file `src/backend/.env` from MiroFish-compatible local settings:
    - `LLM_BASE_URL=http://localhost:14003/v1`
    - `LLM_MODEL=Qwen3.6-35B-A3B`
    - `LLM_API_KEY=` empty
  - Restarted backend after adding this env file; `/health` is OK.
- Resolved several previously noted caveats:
  - project status is now updated during parse/ontology/graph phases
  - graph completion writes `project.stats` into project metadata
  - CORS allows both `http://localhost:5173` and `http://localhost:5174`
  - project delete also deletes its vault directory
  - project vault APIs now read/write under `VAULT_DIR/{project_id}`
  - vault file preview now rejects paths outside the project vault
  - incremental graph API is now reachable from the graph-build step UI
  - task state is no longer purely in-memory

## Verification

- Backend full test suite:
  - `cd src/backend && python3 -m pytest tests/ -v`
  - Result: `74 passed, 19 warnings`
- Frontend production build:
  - `cd src/frontend && npm run build`
  - Result: built successfully
  - Warning remains: large Vite chunk over 500 kB

## In Progress

- 2026-05-26 18:40 KST update:
  - User asked to stop the backend before continuing; ProjectOS backend on port `8001` was stopped.
  - The repeated vault write failure was caused by entity names containing path separators such as `/`.
  - `ObsidianWriterAgent` now writes notes with sanitized filenames, so `프로젝트 리더/책임자` becomes a safe single markdown filename.
  - Old failed generated vault output was removed from `src/backend/vault/b6461d62` and `vault/b6461d62`.
  - Added `app.utils.entity_validation` and wired it into graph/profile generation.
  - Person extraction is now stricter:
    - prompts say Person is only for real identifiable human names
    - pronouns, author/user references, anonymous people, role titles, departments, fields, and generic descriptions are rejected
    - code also filters invalid Person entities before graph merge and before profile generation
  - Task progress messages now include quantitative counts:
    - parse: `파일 파싱 중... (current/total)`
    - ontology: `(1/1)`
    - graph extraction: `엔티티/관계 추출 중... (current/total)`
    - profile generation: `프로필 생성 중... (current/total)`
    - vault writing: `Obsidian vault 작성 중... (current/total)`
    - analysis: staged `(1/3)`, `(2/3)`, `(3/3)`
  - `ProgressPanel.vue` now deduplicates identical consecutive SSE log lines, so the web log area is cleaner.
  - Backend file logging now suppresses noisy `httpx` and `watchfiles` info logs.
  - `.gitignore` now excludes root `vault/` and `logs/`, matching the moved runtime paths.
  - Old failed `graph.json` and `profiles.json` were removed for project `b6461d62` so the next graph build uses the stricter Person extraction.
  - Project `b6461d62` status was reset from `failed` to `created`; `chunks.json` and `ontology.json` remain.
  - Rotated the noisy previous log to `logs/archive/projectos-before-progress-update-20260526-1841.log`.
  - Fresh runtime log is now `logs/projectos.log`.
  - Backend is currently served without `--reload` to keep runtime logs cleaner:
    - `uvicorn app.main:app --host 0.0.0.0 --port 8001`
  - Verification after this update:
    - `cd src/backend && python3 -m pytest tests/ -v` -> `75 passed, 19 warnings`
    - `cd src/frontend && npm run build` -> success; Vite large chunk warning remains
    - `git diff --check` -> clean
    - backend restarted on `http://localhost:8001`; `/health` returned OK
    - frontend still serves `http://localhost:5174/` with HTTP 200

## Existing Dirty Worktree Notes

- `CLAUDE.md` was already modified before this session.
- That change documents dgx02 runtime notes:
  - backend on port `8001`
  - frontend on port `5174`
  - temporary Vite proxy change to `8001` should not be committed unless intentionally desired
  - Playwright/Puppeteer cannot run directly because GTK libs are missing

## Known Issues To Resolve

- Existing global vault contents written before this change may remain under the old `VAULT_DIR` root. New writes go to `VAULT_DIR/{project_id}`.
- Vite build warns about a large JS chunk; no functional failure.
- Incremental graph build currently loads the existing graph but still iterates all chunks; this can revisit older chunks. Fuzzy dedup reduces duplicate nodes, but relation extraction can still add repeated edges if relation identity differs.
- Current runtime cannot proceed past ontology generation until `LLM_BASE_URL` points to a reachable OpenAI-compatible server. If that server is OpenAI, a real `LLM_API_KEY` is required; if it is a local server, the key may remain empty.
