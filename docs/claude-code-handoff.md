# Claude Code Handoff

Last updated: 2026-05-26

## Current Objective

모든 계획된 리팩토링 완료. 다음 세션에서는 새 기능 개발 또는 버그 수정 진행.

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
