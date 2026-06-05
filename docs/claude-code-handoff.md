# Claude Code Handoff

Last updated: 2026-06-05

## 2026-06-05 claude-obsidian 비교 개선 (진행 중)

**배경:** claude-obsidian(github.com/AgriciDaniel/claude-obsidian)과 ProjectOS를 비교해 개선점 5종 도출.
사용자 지시: #1부터 순차 진행, #6(transport 자동감지)은 제외, 작업은 subagent로, 진행 내역은 본 문서에 기록.

**개선점 우선순위:**
1. **(진행 중) 하이브리드 검색** — QueryAgent가 substring 매칭만 사용. BGE-M3 임베딩 인프라가 쿼리 경로에서 미사용. → 키워드(sparse)+dense RRF 융합, 빌드 시 임베딩 캐시. spec: `docs/superpowers/specs/2026-06-05-hybrid-retrieval-design.md`.
2. Vault 수동 편집 → 그래프 역반영(reconcile) 경로 부재.
3. "Hot cache"(claude-obsidian `hot.md`) 부재 — MCP 세션 진입용 압축 컨텍스트.
4. 출처 인용 강제화(현재 프롬프트 권유만).
5. 능동적 지식 보강(autoresearch) — 고립 노드/약점 자동 채움.
- (#6 제외) transport 자동감지: 도메인 파이프라인상 백엔드 상주 불가피, 사용자 제외.

**#1 상태:** 설계 승인 완료(빌드 시 캐시 + 청크·노드 적용). 다음: 구현 plan 작성 → subagent TDD 실행.

## 2026-06-03 Phase 2b — Scheduled Digest Agent

**What:** Deterministic daily digest per built project → `vault/<id>/Digests/YYYY-MM-DD.md`.
No LLM calls; composed from `run_health_check` + new-node diff (`digest_state.json`) +
reused `analysis.json`.

**New files:** `app/services/digest.py` (compose/generate/should_run/DigestService),
`app/api/digest.py` (POST `/api/projects/{id}/digest`, GET `/digests`, GET `/digests/{date}`).

**Config:** `DIGEST_ENABLED=False` (opt-in), `DIGEST_HOUR=7`, `DIGEST_POLL_SECONDS=300`.

**Wiring:** `DigestService` started/stopped in `app/main.py` lifespan alongside `WatcherService`.

**Verification:** `python3 -m pytest tests/ -q` → 302 passed.

**Next candidates:** local-LLM prose synthesis (optional layer), Obsidian plugin "new digest"
badge (polls the list endpoint), weekly cadence, deleted-node tracking.

## 2026-06-03 Phase 2b 후속 — Digest 보강 (코드 리뷰 도출, 완료·미커밋)

코드 리뷰의 non-blocking 제안 4건 모두 구현. 검증: `python3 -m pytest src/backend/tests -q` → **307 passed**.
- **스케줄 dedup 영속화**: scheduled poll이 `digest_state.json.last_digest_date`를 읽어 재시작 후에도 오늘 이미 생성된 프로젝트를 건너뜀(`_read_last_digest_date`, `_seed_last_run_date`). 모든 eligible 프로젝트가 오늘 완료 상태면 `_last_run_date`도 seed.
- **블로킹 IO 해소**: `poll_once`의 scheduled 생성 루프를 `asyncio.to_thread(_run_scheduled_digest_cycle, ...)`로 이동해 async loop 블로킹 감소.
- **best-effort 정책 주석**: 한 cycle에서 일부 프로젝트가 실패해도 다음 날까지 재시도하지 않음(의도된 동작)임을 주석화.
- **테스트 5종 추가**: 2차 실행 diff(`test_generate_second_run_diffs_against_written_state`), analysis issue 5개 cap(`test_render_markdown_caps_analysis_issues_at_five`), 재시작 dedup(`test_poll_once_skips_project_with_state_for_today_after_restart`), all-today seed(`test_poll_once_seeds_last_run_when_all_projects_have_today_state`), start/stop lifecycle(`test_start_stop_lifecycle_when_enabled`).

> ⚠️ **push 차단 상태**: 위 변경은 로컬 `main`에 `0fcc848 fix(digest): persist scheduled dedup state`로 커밋됨. `git push origin main`은 `/usr/bin/gh: not found` 및 HTTPS credential 부재로 실패. 인증 가능한 환경에서 push 필요.

## 2026-06-03 Phase 3 시작 — 최소 MCP Tool 노출 (구현 완료, push 전)

외부 에이전트가 ProjectOS를 career-memory backend로 호출할 수 있도록 의존성 추가 없이 MCP JSON-RPC 최소 엔드포인트를 추가.
- `POST /mcp`: MCP JSON-RPC `initialize`, `tools/list`, `tools/call` 지원. protocolVersion `2025-11-25`, tools capability 제공.
- `GET /mcp/tools`: HTTP 디버깅/호환용 tool schema listing.
- Tool adapter: `projectos_create_project`, `projectos_upload_file`, `projectos_get_task`, `projectos_build_ontology`, `projectos_build_graph`, `projectos_list_projects`, `projectos_get_graph_health`, `projectos_query_career_graph`, `projectos_generate_digest`, `projectos_list_digests`, `projectos_get_digest`, `projectos_get_vault_note`, `projectos_read_traces`.
- 안전장치: vault note path traversal 차단, tool 실행 실패는 MCP `CallToolResult.isError=true`로 반환.
- 검증: `python3 -m pytest src/backend/tests -q` → **313 passed**.
- 참고: MCP 공식 스키마는 JSON-RPC 2.0, `tools/list`, `tools/call`, `CallToolResult.content/structuredContent/isError` 형태를 사용.

## 2026-06-03 Claude Desktop MCP stdio bridge (구현 완료, push 전)

Claude Desktop local MCP 설정에서 ProjectOS를 바로 호출할 수 있도록 HTTP MCP endpoint 앞단에 stdio bridge 추가.
- `src/backend/projectos_mcp_stdio.py`: newline-delimited JSON-RPC stdin/stdout 메시지를 `PROJECTOS_MCP_URL`(기본 `http://127.0.0.1:8002/mcp`)로 프록시.
- stdout에는 MCP JSON-RPC 응답만 기록하고, 로그는 stderr로 분리.
- `/mcp` 라우터에 `ping` 지원 추가.
- 연결 문서: `docs/claude-desktop-mcp.md`에 backend 실행 명령과 `claude_desktop_config.json` 예시 추가.
- 테스트 추가: bridge forwarding/parse error/unreachable backend, `/mcp` ping.
- 검증: `python3 -m pytest src/backend/tests -q` → **317 passed**.

## 2026-06-03 MCP Project 생성 Tool 추가 (구현 완료, push 전)

Claude Desktop에서 ProjectOS project를 직접 만들 수 있도록 MCP tool 추가.
- `projectos_create_project`: 입력 `name`(required), `description`(optional). 반환 `project`, `project_id`.
- `project_store.create(...)`를 재사용해 기존 REST `POST /api/projects`와 동일한 project metadata/files 디렉터리 생성 흐름 유지.
- 빈 이름은 `CallToolResult.isError=true`와 `name is required`로 반환.
- stdio bridge 경로에서 `tools/list` 및 실제 `tools/call` 생성 smoke test 완료. 검증용 project는 삭제함.
- 검증: `python3 -m pytest src/backend/tests -q` → **319 passed**.

## 2026-06-04 MCP/API File Upload 추가 (구현 완료, push 전)

Claude Desktop에서 첨부 파일을 ProjectOS project로 전달해 초기 graph build 전 parse 단계까지 진행할 수 있도록 업로드 경로 추가.
- REST raw binary API: `POST /api/projects/{project_id}/files/raw?filename=<name>&file_type=<type>` body bytes를 그대로 저장 후 parse task 시작.
- REST base64 API: `POST /api/projects/{project_id}/files/base64` JSON `{filename, content_base64, file_type}` 저장 후 parse task 시작.
- 공통 helper `save_file_and_start_parse(...)`: 기존 multipart 업로드와 동일하게 `projects/<id>/files/`에 저장, `project.files` 갱신, `ProjectStatus.PARSING`, parse task 생성.
- MCP tool `projectos_upload_file`: 입력 `project_id`, `filename`, `content_base64`(binary PDF/DOCX 등) 또는 `content_text`, `file_type`; 반환 `task_id`, `files`.
- 파일명은 basename으로 정리하고 빈 이름/빈 내용/잘못된 base64는 error로 반환.
- 검증: targeted API/MCP tests `33 passed`; 전체 `python3 -m pytest src/backend/tests -q` → **325 passed**.

## 2026-06-04 MCP Graph Build Tool 추가 (구현 완료, push 전)

Claude Desktop이 업로드 후 그래프를 수동 합성하려는 문제를 막기 위해 빌드 단계 MCP tool 추가.
- `projectos_get_task`: `task_id`로 parse/ontology/graph background task 상태 조회.
- `projectos_build_ontology`: parse 완료 후 `chunks.json`을 전제로 ontology task 시작.
- `projectos_build_graph`: ontology 완료 후 `ontology.json`을 전제로 initial/incremental graph task 시작.
- 권장 순서 문서화: create project → upload file → poll parse task → build ontology → poll ontology task → build graph → poll graph task → graph health.
- `docs/claude-desktop-mcp.md`에 “그래프를 첨부 텍스트에서 수동 합성하지 말고 ProjectOS build task를 사용”하라는 지침 추가.
- 검증: `python3 -m pytest src/backend/tests/test_api/test_mcp_api.py -q` → 17 passed; 전체 `python3 -m pytest src/backend/tests -q` → **330 passed**.

## 앞으로 진행할 내용 (Next Up)

작성 시점 2026-06-03. Phase 1/2a/2b 백엔드 구현 본체는 `main`에 머지됨. 다음 작업 우선순위:

### A. Digest 후속 보강 커밋 (즉시)
- **커밋 완료, push 미완료**: digest 보강 변경(`app/services/digest.py`, `tests/test_services/test_digest.py`) + 본 문서는 `0fcc848`로 로컬 `main`에 커밋됨. `git push origin main`은 GitHub HTTPS 인증 문제로 실패했으므로 인증 가능한 셸에서 push 필요.

### B. 수동 검증 (선택)
- `.env`에 `DIGEST_ENABLED=true`, `DIGEST_HOUR=<현재 시각>` 설정 후 서버 실행 → 빌드 완료 프로젝트에 대해 `vault/<id>/Digests/<오늘>.md` 생성 및 `traces.jsonl`에 `"action":"digest"` 기록 확인.

### C. Phase 3 — MCP 노출 + trace 기반 자동 튜닝 (다음 주요 단계)
- **진행 중** OpenJarvis 방향성 로드맵의 마지막 단계. `docs/superpowers/specs/2026-06-02-projectos-openjarvis-direction.md` §4.2~ 참고.
- **진행 중** ProjectOS 그래프/쿼리/digest 기능을 MCP 서버로 노출 → 외부 에이전트가 ProjectOS를 memory backend로 사용.
- `traces.jsonl`(graph_build/watcher/digest 결정 로그) 기반 learning loop: 라우팅/budget 정책 자동 튜닝.
- 다음: Claude Desktop에서 실제 연결 검증 후, trace 기반 tuning spec/plan 작성.

### D. 선택적 Digest 확장 (우선순위 낮음)
- local-LLM prose synthesis 레이어, Obsidian plugin "new digest" 배지(list 엔드포인트 폴링), 주간 cadence, 삭제 노드 추적.

## Completed In This Session (2026-06-03 Phase 1 Foundation + Phase 2a File Watcher)

OpenJarvis 방향성 로드맵의 Phase 1과 Phase 2a를 TDD subagent-driven 방식으로 구현 완료.

### Phase 1 — Constraint-aware routing foundation (branch `phase1-foundation`, 머지 대기)
- `Role` 클래스 + `route()` 라우팅 정책 + budget guard (누적 비용 ≥ `LLM_BUDGET_USD` 초과 시 `claude_code`→`local` 강등; 0=무제한).
- `LLMClient.for_role` 팩토리로 역할별 백엔드 선택. 에이전트들을 역할 기반 라우팅으로 마이그레이션.
- Decision-trace sink: `app/utils/trace.py` `record_trace()` → `PROJECTS_DIR/<id>/traces.jsonl`(JSONL). `GET` traces 엔드포인트.
- Skills 카탈로그: `app/skills.py` `SkillDescriptor` 6종 + `GET /api/skills`.
- 정책: `CHUNK_EXTRACTION→GRAPH_EXTRACTION_BACKEND`, `SIMULATION→local`, 나머지→`LLM_BACKEND`. 253 tests passed, READY TO MERGE.

### Phase 2a — Continuous File Watcher (branch `phase2-watcher`, `phase1-foundation` 기반)
- 스펙: `docs/superpowers/specs/2026-06-02-phase2-file-watcher-design.md`. 계획: `docs/superpowers/plans/2026-06-02-phase2-file-watcher.md`.
- 해시 폴링 백그라운드 태스크가 빌드 완료 프로젝트의 `files/` 변경을 감지 → 재파싱 → incremental 빌드 자동 트리거. opt-in `WATCHER_ENABLED=False` 기본.
- 핵심 설계 근거: incremental 빌드는 재파싱을 안 하므로 Watcher가 **빌드 전에 chunks.json을 재파싱·교체**(`reparse_and_replace_chunks`)해야 신규/수정 파일이 반영됨.
- 구현 (6 commits, `phase1-foundation..phase2-watcher`):
  - `TaskManager.has_active_build` — 프로젝트별 빌드 중복 방지.
  - `compute_stable_changes` — 순수 디바운스 함수(변경 AND 직전 폴링 대비 안정).
  - `reparse_and_replace_chunks` — 변경 파일 재파싱, file_type 보존, 중복 청크 방지.
  - `_run_graph(trigger="manual")` 파라미터 + graph_build trace에 `trigger` 기록.
  - `WatcherService` — 감지 IO + 오케스트레이션 + 폴링 루프(`app/services/watcher.py`), config `WATCHER_ENABLED`/`WATCHER_POLL_SECONDS`.
  - `main.py` lifespan으로 watcher 시작/정지.

### 검증
- `python3 -m pytest tests/ -q` → **269 passed**.
- 최종 코드 리뷰: APPROVED_WITH_NITS, 실버그 없음. 디바운스/dedup/예외 격리/청크 교체 모두 정확. nit은 모두 스펙 범위 밖(삭제 처리 미지원=의도된 비목표).

### 다음 판단
- 브랜치 정리: `phase1-foundation` 머지 → `phase2-watcher` 머지 순서 결정 필요. `phase1-foundation`은 사전 미커밋 작업(GRAPH_BUILD_WORKERS 등)을 함께 담고 있음.
- 수동 검증(선택): `.env`에 `WATCHER_ENABLED=true` 설정 후 서버 실행, 빌드 완료 프로젝트의 `files/`에 파일 추가/수정 → ~30초 후 `graph_watcher` task + `traces.jsonl`에 `"trigger":"watcher"` 확인.
- 후속: Phase 2b(Scheduled Digest Agent) 별도 스펙/플랜. Phase 3(MCP 노출 + trace 기반 자동 튜닝).

## Current Objective

LLM Wiki-inspired 개선 Task 1-5 완료. Obsidian vault sync 방식 1번 구현이 백엔드/export/plugin scaffold까지 진행됨. ProjectOS는 UI에서 local/Claude/Claude task graph build 설정을 전환할 수 있음. vault wiki/index/log/provenance를 QueryAgent와 Health에 활용함.

## Completed In This Session (2026-06-02 OpenJarvis 방향성 분석)

- OpenJarvis(Stanford Hazy Research)와 ProjectOS 비교 분석 후 전략 방향 문서 작성.
- 결론: ProjectOS=기억(memory), OpenJarvis=행동(action)으로 상보적. 전면 채택(A) 기각, **패턴 차용(B) + 스킬/MCP 노출(C)** 채택.
- 차용 패턴 5종: Scheduled Digest, Continuous Watcher, skills 카탈로그 표준, trace 기반 learning loop, constraint-aware routing.
- 로드맵 Phase 1(라우팅 policy+budget, trace 로깅, skills descriptor) → Phase 2(Digest/Watcher 자동화) → Phase 3(MCP 노출+자동 튜닝).
- 문서: `docs/superpowers/specs/2026-06-02-projectos-openjarvis-direction.md`
- 코드 변경 없음. 권장 첫 구현: Phase 1 constraint-aware routing policy table + budget guard.

## Completed In This Session (2026-06-01 Workflow Progress UI)

사용자 추가 요청 1번 반영: 진행률 bar만으로는 현재 작업 단계 파악이 부족하므로 Obsidian 패널에 워크플로우 단계 표시를 추가함. 사용자 추가 요청 2번은 Claude task graph 단일 경로 E2E 이후 dependency 없는 chunk extraction을 worker 2개로 병렬화하는 방식으로 구현함.

- **워크플로우 단계 UI** (`src/obsidian-plugin/src/ui/WorkflowStrip.svelte`, `src/obsidian-plugin/src/App.svelte`, `styles.css`)
  - 헤더 아래에 `Project → Runtime → Sync → Collect → Ontology → Graph → Analysis → Query → Sim` 단계 스트립 추가
  - 단계 상태: `idle / running / success / failed / skipped`
  - running 단계 pulse, success/failed 색상 표시
  - 좁은 Obsidian side panel에서 가로 스크롤로 깨짐 방지
- **단계 상태 연결** (`src/obsidian-plugin/src/store/appStore.svelte.ts`, sections)
  - project create/select/delete, runtime load/save, sync, collect parse, ontology, graph, analysis, query, simulation 액션에 workflow 상태 갱신 연결
  - 기존 task SSE watch에 optional `workflowStepId`를 추가해 task progress와 단계 상태를 같이 갱신
- **Claude task graph API E2E**
  - backend `http://localhost:8002`에서 작은 임시 프로젝트로 parse → ontology → graph 수행
  - runtime settings: `graph_build_mode=claude_task`, `graph_extraction_backend=claude_code`, `claude_code_model=claude-haiku-4-5`, `chunk_size=1800`, `chunk_overlap=150`
  - 결과: graph task 완료, node-link graph 기준 `nodes=9`, `links=13`
  - health: isolated 0, duplicate pairs 0, `wiki_graph_lint` mismatch 없음
  - 임시 프로젝트 삭제 및 기존 runtime settings 복원 완료
- **Graph build 병렬화** (`src/backend/app/agents/graph_builder_agent.py`, `src/backend/app/config.py`)
  - `GRAPH_BUILD_WORKERS=2` 기본값 추가
  - dependency 없는 chunk별 `_extract_from_chunk`를 semaphore 기반 worker 2개로 병렬 실행
  - 공유 graph merge는 race를 피하기 위해 결과 수집 후 기존 chunk 순서로 순차 처리
  - `claude_task` mode는 현재 전체 source file task 1개 구조라 변경하지 않음

### 검증

- `cd src/obsidian-plugin && npm run build` → success
- `cd src/obsidian-plugin && npm test` → `11 passed`
- 번들을 `src/backend/vault/.obsidian/plugins/projectos-vault-sync/`에 동기화
- `pytest src/backend/tests/test_api/test_settings_api.py src/backend/tests/test_agents/test_graph_builder_agent.py src/backend/tests/test_agents/test_claude_task_graph_builder_agent.py` → `28 passed`

### 다음 판단

- Obsidian plugin runtime validation을 먼저 수행해 새 workflow UI와 sync/collect/query 수동 흐름을 확인
- 실행 중인 backend 서버가 reload되지 않았다면 재시작해 `GRAPH_BUILD_WORKERS=2` 코드 반영
- 이후 큰 프로젝트에서 worker=2 기준 graph build 시간/실패율 비교

## Completed In This Session (2026-06-01 Panel Nav Redesign + Simulation Timeline)

사용자 피드백: 기존 redesign이 (1) 동적 요소가 없어 재미없고 (2) 7개 섹션이 한 화면에 모두 쌓여 복잡함. 시뮬레이션 타임라인의 라운드 구분이 불명확하고 `agent + 숫자` 조합이 이해하기 어려움.

- **패널 네비게이션** (`src/obsidian-plugin/src/App.svelte`, `styles.css`)
  - 7개 섹션 세로 stack → 상단 아이콘 탭 네비게이션으로 변경 (사용자 선택)
  - 한 번에 한 섹션만 렌더링, 탭 전환 시 fade transition
  - 각 탭에 인라인 SVG 아이콘 + 짧은 라벨, active 상태 accent 강조
  - 동적 요소: 카드 hover lift(border accent + shadow), nav hover/active 트랜지션
- **시뮬레이션 타임라인** (`src/obsidian-plugin/src/sections/SimulationSection.svelte`, `styles.css`)
  - 라운드별 색상 구분: 8색 팔레트, 라운드 헤더 pill + 좌측 컬러 바 + 카드 배경 틴트
  - 타임라인을 `round` 기준으로 그룹화(`roundGroups`)
  - `Round N · agent_id` 조합 제거 → agent의 **실제 이름**(persona.name) 버튼 표시
  - agent 이름 클릭 시 해당 persona의 role + goals/knowledge가 인라인 slide로 펼쳐짐 (`openItems` Set 토글)
  - persona 매칭 안 되면 버튼 disabled

### 검증

- `cd src/obsidian-plugin && npm run build` → success
- `npm test` → `8 passed`
- 번들을 `src/backend/vault/.obsidian/plugins/projectos-vault-sync/`에 동기화
- **시각 확인 불가**: 이 서버(dgx02)는 GTK/브라우저 미설치로 Obsidian 실행 불가. 최종 확인은 macOS Obsidian에서 플러그인 reload 후 사용자가 직접 수행 필요.

### User Action

- Obsidian에서 ProjectOS 플러그인 disable/enable 또는 Obsidian reload로 갱신된 `main.js`/`styles.css` 로드

## Completed In This Session (2026-06-01 Obsidian Plugin Blank Panel Fix)

- Diagnosed Obsidian ProjectOS plugin blank panel using the in-app fallback error display.
- Root cause: `src/obsidian-plugin/src/store/appStore.svelte.ts` used Svelte 5 runes (`$state`) in a plain TypeScript module that was bundled without rune transformation. Obsidian therefore raised `ReferenceError: $state is not defined`.
- Fixed `AppStore` by replacing rune fields with a `createSubscriber`-based reactive class:
  - `status`, `task`, `projects`, `backendSettings`, `runtimeDirty`, `analysis`, `simulation`, `simulationLive`, and `answer` now use explicit getters/setters.
  - Svelte components still update reactively without relying on global `$state`.
- Added a view-level fallback in `src/obsidian-plugin/src/main.ts`:
  - render failures now show an error panel and Retry button instead of a blank Obsidian view.
- Hardened plugin layout CSS in `src/obsidian-plugin/styles.css`:
  - long project names, IDs, status text, pills, buttons, and error stacks wrap inside their containers.
- Cleaned Svelte build warnings:
  - `verbatimModuleSyntax=true` in `src/obsidian-plugin/tsconfig.json`
  - Runtime section labels connected to controls
  - local state initialization warnings removed in ProjectSection, Disclosure, and Tabs.
- Rebuilt and installed the updated plugin bundle into `src/backend/vault/.obsidian/plugins/projectos-vault-sync/`.
- Verified the installed plugin bundle no longer contains unresolved `$state`, `$derived`, `$effect`, or `$props` tokens.

### Verification

- `cd src/obsidian-plugin && npm run build` -> success
- `cd src/obsidian-plugin && npm test` -> `8 passed`
- `http://172.16.229.33:8002/health` -> OK
- Backend OpenAPI includes `/api/projects/{project_id}/simulation`

### User Action

- In Obsidian, disable/enable the ProjectOS plugin or reload Obsidian so it loads the updated `main.js`.

## 다음 작업 후보

1. **Obsidian plugin runtime validation** — `src/obsidian-plugin/main.js`, `manifest.json`을 로컬 Obsidian vault plugin 폴더에 배치해 sync/collect/query 수동 검증
2. **Claude task graph API E2E** — UI에서 `GRAPH_BUILD_MODE=claude_task`, `CLAUDE_CODE_MODEL=claude-haiku-4-5`, 큰 `CHUNK_SIZE` 저장 후 실제 `/api/projects/{id}/graph` task path를 작은 프로젝트로 검증
3. **Graph health UI** — `/api/projects/{id}/graph/health`의 `wiki_graph_lint` 결과를 프론트엔드에 표시하는 진단 패널
4. **고립 노드 개선** — 현재 `a0dfcffa` health 기준 isolated 20개. 필터보다 relation re-extraction/context grouping 우선 검토
5. **Wiki synthesis/lint Claude task** — 로컬 graph build 후 Claude로 vault 품질 리뷰/요약 생성
6. **WritingAgent** — 그래프/위키 품질이 충분히 올라간 후 이력서/자기소개서 초안 생성 에이전트

## Completed In This Session (2026-05-31 Obsidian Plugin Svelte Redesign)

- Obsidian side-panel view를 Svelte 5 (runes) 기반으로 전면 재작성
  - Theme-adaptive, 동적 UI — Obsidian CSS 변수 활용
  - Settings tab은 기존 Obsidian native `Setting` API 유지 (non-Svelte)
- 새 모듈 구조: `src/obsidian-plugin/src/`
  - `api/` — types + HTTP client
  - `lib/` — vaultSync (이전), runtime, graphColors + graphColorGroups 분리
  - `store/appStore.svelte.ts` — Svelte 5 runes 기반 앱 상태
  - `ui/` — 6개 primitive 컴포넌트
  - `sections/` — 7개 섹션 컴포넌트
  - `App.svelte`, `main.ts` (새 plugin entry)
- 구 root-level `main.ts` monolith (~1180 lines) 삭제
- Build: esbuild-svelte → single `main.js` 번들

검증:

- `npm run build`: success (verbatimModuleSyntax warning only, no errors)
- `npm test`: `8 passed` (runtime, vaultSync, graphColors)
- **주의**: 이 서버(dgx02)에서는 GTK/브라우저 미설치로 Obsidian 실제 실행 불가.
  최종 시각적 확인은 macOS Obsidian에서 사용자가 직접 수행 필요.

미완료 (별도 작업, 사용자 판단에 의해 연기):

- Backend simulation 결함: edge type-match fallback, relation normalization (고정 10 relation type으로), Category 노드의 enhancement-edge 타깃 제외

## Completed In This Session (2026-05-31 Runtime Settings UI)

- Backend settings API 확장
  - `llm_backend`
  - `graph_build_mode=chunk|claude_task`
  - `graph_extraction_backend=local|claude_code`
  - `claude_code_model`
  - `chunk_size`
  - `chunk_overlap`
  - 저장 즉시 runtime `config`에 반영
- Web UI `HomeView` 설정 다이얼로그 확장
  - local/Claude LLM backend 선택
  - chunk extraction vs Claude task graph build 선택
  - chunk extraction backend 선택
  - Claude 모델명 및 chunk size/overlap 설정 가능
- Obsidian plugin side panel에 `Runtime` 섹션 추가
  - `/api/settings` GET/POST로 backend runtime 설정 로드/저장
  - Project 생성/선택 없이도 graph build 동작 방식을 먼저 지정 가능
  - `Local`, `Hybrid`, `Claude Task` 프리셋 버튼 추가
- Obsidian plugin `Project` 섹션에 backend project list 추가
  - `/api/projects` 결과를 카드 리스트로 렌더링
  - 프로젝트 이름/설명/status/id 확인 후 바로 선택 가능
  - 기존 dropdown 선택도 유지
- Obsidian plugin settings tab에도 backend runtime 설정 추가
  - base URL/target folder와 같은 설정 화면에서 runtime reload/save 가능
- Obsidian plugin README에 runtime mode 설정 설명 추가
- Claude graph build subprocess에서 user Claude Code plugins/skills 제외
  - `CLAUDE_GRAPH_DISABLE_PLUGINS=true` 기본값 추가
  - `ClaudeTaskRunner`와 graph extraction용 `LLMClient(..., disable_plugins=True)`에 `--setting-sources project,local`, `--disable-slash-commands` 적용
  - 일반 개발용 Claude Code 호출은 기존 plugin 사용 가능

검증:

- Backend settings tests: `5 passed`
- Backend full tests: `212 passed`
- Frontend production build: success
- Obsidian plugin tests/build: `2 passed`, production build success
- Claude graph plugin-disable targeted tests: `32 passed`

## Completed In This Session (2026-05-31 Isolated Claude Task Runner)

- Local LLM이 없는 환경 대비용 Claude Code only task 기반 구조 추가
- 기존 repo `CLAUDE.md`와 섞이지 않도록 task workspace를 repo 밖에 생성
  - default: `/tmp/projectos-claude-tasks/<task_id>`
  - task-local files: `CLAUDE.md`, `input.json`, `schema.json`, `output.json`
  - process cwd는 task workspace
  - task `CLAUDE.md`는 `--system-prompt`로 명시 전달
- 이 환경에서는 `--bare`가 OAuth/keychain auth를 못 써서 `Not logged in`으로 실패함을 확인
  - default `CLAUDE_TASK_BARE=false`
  - API-key 기반 환경에서만 `CLAUDE_TASK_BARE=true` 사용 가능
- `ClaudeTaskRunner` 추가
  - isolated workspace 생성
  - allowed paths를 `--add-dir`로 제한
  - JSON wrapper/result 파싱
  - required key 검증
  - Claude usage 집계
- `ClaudeTaskGraphBuilderAgent` 추가
  - `GRAPH_BUILD_MODE=claude_task`일 때 graph API에서 사용 가능
  - source file paths를 input allowlist로 전달
  - task-specific graph extraction `CLAUDE.md` 지시사항 사용
- Config/env 추가
  - `GRAPH_BUILD_MODE=chunk|claude_task`
  - `CLAUDE_TASKS_DIR`
  - `CLAUDE_TASK_BARE`
  - `CLAUDE_TASK_TIMEOUT`

검증:

- `--bare` smoke: fails with `Not logged in`, so disabled by default
- isolated Claude task smoke with `claude-haiku-4-5`:
  - result: `{"ok": true, "value": "ProjectOS"}`
  - usage: 1 call, cost `$0.0447438`
- real file graph extraction smoke with `ClaudeTaskGraphBuilderAgent`:
  - allowed source path: `/tmp/projectos-claude-task-profile.txt`
  - result: 4 nodes / 3 edges
  - usage: 1 call, cost `$0.0263992`
- Targeted tests:
  - `test_claude_task_runner.py`
  - `test_claude_task_graph_builder_agent.py`
  - `test_graph_builder_agent.py`
  - `test_llm_client.py`
  - Result: `31 passed`

## Completed In This Session (2026-05-30 Obsidian User Graph + Claude Haiku E2E)

- Obsidian native Graph View에서 user node가 작아지는 문제 완화
  - category hub 구조는 유지
  - Person note 렌더링 시 `Person -> Category -> Entity`를 직접 wikilink로 확장
  - `a0dfcffa`의 `vault/a0dfcffa/Career/양필성.md` 재생성 결과 wikilink 111개
  - `_index.canvas`에서 Person node 크기 `320x120`으로 확대
- Claude Code model 설정 추가
  - `CLAUDE_CODE_MODEL` config/env 추가
  - `_ClaudeCodeBackend`가 `claude -p --model <model>`로 호출
  - `claude-haiku-4-5` 실제 CLI 호출 확인
- Graph extraction backend override 추가
  - 기본은 계속 `GRAPH_EXTRACTION_BACKEND=local`
  - 품질/속도 실험 시 `GRAPH_EXTRACTION_BACKEND=claude_code`로 전체 graph extraction도 Claude Code 사용 가능
- 큰 chunk 테스트
  - `CHUNK_SIZE=1800`, `CHUNK_OVERLAP=150`
  - `claude-haiku-e2e` 테스트 프로젝트로 parse → ontology → graph extraction → dedup/canonicalization/refinement → vault → analysis → query 실행

검증:

- Claude Code haiku smoke test:
  - `claude -p --model claude-haiku-4-5 --output-format json ...` success
- Claude haiku E2E:
  - chunks: `1`, max chunk length: `685`
  - graph: `20 nodes / 19 edges`
  - health: isolated `0`, components `1`, duplicate pairs `0`, graph/vault mismatch `0`
  - QueryAgent answer returned ProjectOS + skills with source reference
  - usage: `7 calls`, `19,836 output tokens`, `92,417 cache creation tokens`, `178,794 cache read tokens`, cost `$0.23264365`
- Backend full tests: `207 passed`
- Obsidian plugin tests/build: `2 passed`, production build success
- `git diff --check`: clean
- Backend restarted on `http://localhost:8002`

## Completed In This Session (2026-05-30 Obsidian Vault Sync Mode 1)

Plan:

- `docs/superpowers/plans/2026-05-30-obsidian-vault-sync-implementation.md`

Spec:

- `docs/superpowers/specs/2026-05-30-obsidian-plugin-vault-sync-design.md`

변경 내역:

- `app.models.vault` 추가
  - `VaultNote`, `VaultFile`, `VaultPayload`
- `ObsidianWriterAgent` 2계층 리팩터
  - `build_payload(...) -> VaultPayload`
  - `write_payload(payload, ...)`
  - 기존 `run(...)`은 호환 래퍼로 유지
  - 서버측 vault 디스크 쓰기, delta merge, `.obsidian`, `_index.md`, `_index.canvas`, `log.md` 유지
- `GET /api/projects/{project_id}/vault/export` 추가
  - `graph.json` 기반으로 vault payload JSON 반환
  - `profiles.json`이 있으면 profile context 포함
  - 기존 `/vault`, `/vault/file`, `/vault/download`는 유지
- CORS에 `http://localhost:5175`, `app://obsidian.md`, `capacitor://localhost` 추가
- `src/obsidian-plugin/` 신규 scaffold
  - Obsidian manifest/package/tsconfig/esbuild
  - settings: Base URL, auto-managed project id, target folder
  - Project panel에서 backend project create/list/select 가능
  - Project ID는 사용자가 직접 기억하지 않아도 됨
  - target folder가 비어 있으면 `ProjectOS/<project name>/`에 동기화해 여러 프로젝트를 한 Obsidian vault/Graph View에서 분리 렌더링 가능
  - side panel: sync, collect/upload+build, document analysis, query streaming
  - QueryAgent는 `Query` 섹션에서 `/api/projects/{project_id}/chat` SSE로 사용
  - 기존 웹의 `AnalysisAgent` 기능은 `Analysis` 섹션에서 `/api/projects/{project_id}/analysis`로 사용
  - payload-to-vault mapping 단위 테스트 추가
  - `styles.css` 추가로 Project/Sync/Collect/Analysis/Query 카드형 UI 적용
  - Mac/Obsidian 수동 설치 문서 추가: `src/obsidian-plugin/README.md`
  - production `main.js` build 산출
  - installable folder: `dist/obsidian-plugin-projectos-vault-sync`

검증:

- Backend full tests: `203 passed`
- `python3 -m py_compile` for changed backend modules: success
- `git diff --check`: clean
- Obsidian plugin: `npm install`, `npm test`, `npm run build` success
- Runtime export check on `a0dfcffa`:
  - `GET /api/projects/a0dfcffa/vault/export`
  - keys: `canvas`, `index`, `log_entry`, `notes`
  - notes: `100`
  - canvas/index/log payload returned successfully

주의:

- `npm install` reported 1 moderate vulnerability. `npm audit fix --force` was not applied because it may introduce breaking changes.
- Obsidian plugin runtime behavior still needs manual validation inside Obsidian.

## Completed In This Session (2026-05-30 Claude Graph Maintenance Split)

- `GraphBuilderAgent` chunk extraction은 계속 `LLMClient(backend="local")` 사용
- `llm_dedup()` 기본 클라이언트는 설정된 backend를 따르도록 변경
  - UI에서 `Claude Code` 선택 시 중복 병합 판단은 Claude가 수행
  - fixed alias table 대신 acronym/context 기반 후보 확장 후 LLM 판정
- `Achievement` schema refinement 단계 추가
  - 성적/수상/장학금/공식 성과는 keep
  - 동기/경험/일반 활동은 drop 또는 Project/Skill/Event 등으로 retype
  - 자격/시험명은 Achievement가 아니라 Skill로 retype
  - 명백한 학점/수상/장학금/honor는 Claude 오판 시에도 유지하는 schema guard 추가
- `entity_canonicalization()` 단계 추가
  - 고유명사/공식명은 유지하고 일반 개념/기술/역할명은 영어 canonical label로 정규화
  - 전체 노드 무차별 검토는 느려서 후보 기반으로 제한
  - `NLP` 같은 짧은 Skill 약어는 `Natural Language Processing` 등으로 LLM 정규화
- 전체 graph rebuild(`delta=False`) 시 generated vault entity folders 정리
  - stale vault pages로 인한 `vault_pages_without_nodes` 제거
- UI 설정 문구 업데이트
  - 그래프 chunk 추출은 local, 중복 병합/노드 타입 검수는 Claude 사용 가능

검증:

- Targeted backend tests: `41 passed`
- Frontend build: success
- `git diff --check`: clean
- Runtime project `a0dfcffa` with `llm_backend=claude_code`:
  - 완료: 108 nodes / 121 edges
  - NLP 계열 skill page: `Natural Language Processing.md` 단일화
  - Achievement pages: `Total GPA`, `Semester High Honors`, `Sanho Scholarship Recipient`, 수상 2건만 유지
  - `TOEIC 7G5`는 Skill로 이동
  - Graph Health: duplicate pairs 1 (`AI-based Simulation` vs `Agent-based Simulation`), graph/vault mismatch 0, isolated 20

## Completed In This Session (2026-05-29 LLM Wiki-Inspired Improvements)

Plan:

- `docs/superpowers/plans/2026-05-29-llmwiki-inspired-improvements.md`

### Task 1 — Local/Claude 역할 분리

- `GraphBuilderAgent`는 전역 설정이 `claude_code`여도 `LLMClient(backend="local")` 사용
- `isolated_reextract`도 GraphBuilderAgent를 통해 로컬 LLM 사용
- graph build 중 `llm_dedup()` 기본 클라이언트도 로컬 LLM 사용
- Claude Code는 ontology/profile/analysis/chat 등 단발 고품질 작업에 유지
- UI 설정 문구에 “그래프 chunk 추출은 속도를 위해 로컬 LLM 사용” 명시

### Task 2 — Vault wiki를 QueryAgent 컨텍스트로 사용

- `chat` API가 project vault path를 QueryAgent에 전달
- QueryAgent가 `vault/_index.md`를 읽고 prompt에 포함
- QueryAgent가 매칭된 graph node의 vault page를 찾아 최대 3개 prompt에 포함
- 그래프 relation context와 원본 chunk context는 유지

### Task 3 — `log.md`

- ObsidianWriterAgent가 vault 작성 시 append-only `log.md` 생성
- project id, node/edge count, source files, changed pages 기록
- QueryAgent가 최근 `log.md` 내용을 prompt에 포함

### Task 4 — Wiki/Graph lint

- Graph Health에 `wiki_graph_lint` 섹션 추가
- 검사 항목:
  - graph nodes without vault pages
  - vault pages without graph nodes
  - orphan pages
  - duplicate pages/entity names
  - missing source/provenance metadata
- API `GET /api/projects/{id}/graph/health`는 project vault path를 전달

### Task 5 — Provenance 강화

- GraphBuilderAgent가 node에 `source_chunk_ids` 저장
- edges는 기존 `source_chunk_id` 유지
- vault note에 `## Sources` 섹션 추가
- QueryAgent prompt에 출처 파일/청크 언급 지시 추가

### 검증

- Backend full test suite:
  - `cd src/backend && python3 -m pytest tests/ -q`
  - Result: `183 passed, 24 warnings`
- Frontend production build:
  - `cd src/frontend && npm run build`
  - Result: success
- `git diff --check`
  - clean

## Completed In This Session (2026-05-29 UI LLM Backend Settings)

### 변경 내역

- `app/api/settings.py` (신규)
  - `GET /api/settings` — 현재 LLM 백엔드 반환
  - `POST /api/settings` — `local` 또는 `claude_code` 저장
  - 저장 즉시 `config.LLM_BACKEND` 갱신
  - `openai`, `claude` legacy alias 허용
- `app/main.py` (수정)
  - settings router 등록
- `app/config.py` (수정)
  - 기본 `LLM_BACKEND`를 `local`로 정리
  - `SETTINGS_PATH` 추가
- `src/frontend/src/views/HomeView.vue` (수정)
  - 헤더에 `설정` 버튼 추가
  - 백엔드 설정 다이얼로그 추가
  - `로컬 LLM` / `Claude Code` 선택 후 저장 가능
- `src/frontend/src/api/client.js` (수정)
  - `settingsApi` 추가
- `src/frontend/vite.config.js` (수정)
  - `VITE_BACKEND_URL`로 dev proxy target 변경 가능
- `.env.example`, `.gitignore` (수정)
  - `LLM_BACKEND=local`
  - `src/backend/settings.json` ignore

### 검증

- `GET /api/settings` → `{"llm_backend":"local"}`
- `POST /api/settings {"llm_backend":"claude_code"}` → 저장 및 즉시 반영 확인
- Backend full test suite:
  - `cd src/backend && python3 -m pytest tests/ -q`
  - Result: `173 passed, 24 warnings`
- Frontend production build:
  - `cd src/frontend && npm run build`
  - Result: success
- Dev server:
  - Backend: `http://localhost:8002`
  - Frontend: `http://localhost:5175`

## Completed In This Session (2026-05-29 Claude Code E2E + Usage Tracking)

### 변경 내역

- `app/utils/llm_client.py` (수정)
  - Claude Code CLI의 `usage`, `modelUsage`, `total_cost_usd`를 누적하는 계측 추가
  - `reset_llm_usage()`, `get_llm_usage()` 추가
  - `chat()` 응답과 `stream-json`의 `type=="result"` 이벤트에서 사용량 집계
- `tests/test_utils/test_llm_client.py` (수정)
  - Claude Code 사용량 누적 테스트 추가

### E2E 검증 결과

임시 1청크 프로젝트를 생성해 실제 Claude Code 백엔드로 아래 경로를 실행:

- parse: 1개 txt 파일 → 1 chunk
- ontology: Claude Code `chat_json()`
- graph build: Claude Code `chat_json()`
- graph post-processing: semantic/LLM dedup, graph restructure, vault write
- graph health: isolated 0, component 1, duplicate 0
- QueryAgent: Claude Code `stream()`

성공한 E2E 산출:

- project id: `4e959617`
- nodes: `12`
- edges: `12`
- health summary:
  - `total_nodes=12`
  - `total_edges=12`
  - `isolated_count=0`
  - `component_count=1`
  - `duplicate_pair_count=0`
  - `hub_count=0`
- QueryAgent 영어 질문 `What technologies does ProjectOS use?`
  - 그래프 관계 기반으로 `Python`, `FastAPI`, `NetworkX`, `Vue.js`, `D3.js` 응답 확인

### 토큰/비용 집계

성공한 E2E 전체 측정값:

```json
{
  "calls": 3,
  "input_tokens": 13,
  "output_tokens": 6223,
  "cache_creation_input_tokens": 40820,
  "cache_read_input_tokens": 154124,
  "web_search_requests": 0,
  "web_fetch_requests": 0,
  "total_cost_usd": 0.2926962
}
```

동일 graph에서 QueryAgent 영어 질문 1회 추가 측정값:

```json
{
  "calls": 1,
  "input_tokens": 3,
  "output_tokens": 723,
  "cache_creation_input_tokens": 10437,
  "cache_read_input_tokens": 13043,
  "total_cost_usd": 0.05390565
}
```

주의:

- Claude Code CLI는 repo/session 컨텍스트와 cache token을 포함해 보고하므로, 일반 OpenAI-compatible API의 prompt token 계산과 다르게 보임
- 첫 E2E 시도는 graph/vault 작성까지 성공했지만 검증 스크립트의 `links`/`edges` 변환 누락으로 후처리 실패했고, 해당 시도분 사용량은 프로세스 종료 전 출력하지 못해 집계값에 포함되지 않음
- 한국어 QueryAgent 질문은 현재 단순 문자열 검색이 영어 graph/chunk와 매칭하지 못할 수 있음. 영어 질문에서는 graph context 사용 확인됨

### 검증

- `cd src/backend && python3 -m pytest tests/ -q`
  - Result: `169 passed, 24 warnings`
- `git diff --check`
  - clean

## Completed In This Session (2026-05-29 Claude Code Backend Verification + Post-Reextract Dedup)

### 변경 내역

- `app/utils/llm_client.py` (수정)
  - Claude Code `stream()` 호출에 `--verbose` 추가
    - Claude Code 2.1.152에서 `claude -p --output-format stream-json`는 실패하고, `--verbose`가 필요함
  - stream subprocess 종료 코드 검사 추가
  - `_extract_json()` 보강
    - 기존: 전체 응답이 JSON 또는 JSON 코드펜스인 경우만 파싱
    - 변경: 앞뒤 설명 텍스트가 섞여도 첫 JSON 객체를 찾아 파싱

- `app/api/graph.py` (수정)
  - `isolated_reextract` 이후 `llm_dedup(graph)` 2차 실행 추가
  - reextract가 새로 연결/추가한 노드 간 중복 후보를 다시 검토

- `tests/test_utils/test_llm_client.py` (신규)
  - JSON 코드펜스 파싱
  - 설명 텍스트가 섞인 JSON 파싱
  - Claude Code stream 호출 인자에 `--verbose --output-format stream-json` 포함 확인

- `.env.example` (수정)
  - `LLM_BACKEND=openai`
  - `LLM_BACKEND=claude_code` 예시 추가

### 검증

- `claude --version` → `2.1.152`
- `claude -p --output-format json ...`
  - 실제 출력에 top-level `result` 필드 존재 확인
- `claude -p --output-format stream-json ...`
  - `--verbose` 없으면 실패 확인
- `claude -p --verbose --output-format stream-json ...`
  - `type=="assistant"` 이벤트의 `message.content[].text`에서 텍스트 수신 확인
- `LLM_BACKEND=claude_code` 직접 호출
  - `LLMClient.chat_json()` → `{'ok': True, 'value': 7}`
  - `LLMClient.stream()` → 텍스트 응답 수신
- Backend full test suite:
  - `cd src/backend && python3 -m pytest tests/ -q`
  - Result: `168 passed, 24 warnings`
- Frontend production build:
  - `cd src/frontend && npm run build`
  - Result: success
  - Warning remains: Vite large chunk over 500 kB
- `git diff --check` → clean

### 아직 미검증

- 기존 대형 프로젝트 `29347d1e` 전체 파일 대상으로 `LLM_BACKEND=claude_code` graph build 장시간 실행

## Completed In This Session (2026-05-29 Claude Code CLI Backend)

### 변경 내역

**`LLM_BACKEND=claude_code` 옵션 추가 — 전체 파이프라인을 Claude Code CLI로 구동**

- `app/config.py` (수정)
  - `LLM_BACKEND: str = "openai"` 추가 (`"openai"` | `"claude_code"`)
  - `.env`에 `LLM_BACKEND=claude_code` 설정 시 Claude Code CLI 백엔드 활성화

- `app/utils/llm_client.py` (전면 재구성)
  - 기존 OpenAI SDK 로직 → `_OpenAIBackend` 클래스로 분리
  - `_ClaudeCodeBackend` 클래스 신규 추가
    - `chat()`: `claude -p --output-format json <prompt>` subprocess 호출, `result` 필드 반환
    - `chat_json()`: JSON 지시문 프롬프트에 삽입 + 마크다운 코드 펜스 제거 후 파싱
    - `stream()`: `claude -p --verbose --output-format stream-json` 파싱; `type==assistant` 이벤트에서 텍스트 추출, fallback으로 `type==result` 사용
  - `LLMClient` → `config.LLM_BACKEND` 기반으로 `_OpenAIBackend` 또는 `_ClaudeCodeBackend` 선택
  - `_messages_to_text()` 헬퍼: messages 리스트를 `<system>`, `<assistant>`, user 텍스트로 직렬화
  - `_extract_json()` 헬퍼: 마크다운 코드 펜스 처리 후 JSON 파싱

### 영향 범위

`LLM_BACKEND=claude_code` 설정 시 아래 모든 에이전트가 Claude Code CLI를 사용:
- `OntologyAgent` — `chat_json()` 사용
- `GraphBuilderAgent` — `chat_json()` 사용
- `ProfileAgent` — `chat_json()` 사용
- `ObsidianWriterAgent` — `chat()` 사용
- `LLMDedupAgent` — `chat_json()` 사용
- `QueryAgent` — `stream()` 사용

### 주의사항

- `chat_json()`은 JSON 강제 모드 없이 프롬프트 지시문에 의존 → 응답이 마크다운 코드 블록이거나 앞뒤 설명 텍스트가 일부 섞이면 첫 JSON 객체를 찾아 파싱
- `stream()`은 token-by-token 스트리밍이 아닐 수 있음 (CLI가 `assistant` 이벤트를 한 번에 출력하면 전체 텍스트가 한꺼번에 전달)
- `top_k`, `min_p`, `repetition_penalty`, `thinking_mode` 등 로컬 LLM 파라미터는 Claude Code 백엔드에서 무시됨
- Claude Code CLI(`claude`)가 PATH에 있어야 동작

### 미검증 항목

- 전체 그래프 빌드 파이프라인 end-to-end 테스트 미실시

---

## Completed In This Session (2026-05-29 Graph Center Node + LLM Dedup)

### 변경 내역

**사용자 노드 그래프 중앙 고정**

- `src/frontend/src/components/GraphView.vue` (수정)
  - `findCenterNodeId(nodes, links)` 헬퍼 추가 — degree 가장 높은 Person 노드 ID 반환
  - 해당 노드 `fx = width/2, fy = height/2` 로 시뮬레이션 시작 시 중앙 고정
  - 드래그 후에도 고정 유지 (다른 노드는 drag end 시 fx/fy 해제, 중앙 노드는 유지)
  - 시각적 구분: 반지름 18 (일반 Person 14), 금색 테두리 `#FFD700`, 두께 4
- Git commit: `434ea95`

**LLM Dedup Pass**

- `app/utils/llm_dedup.py` (신규)
  - `_find_candidate_pairs(graph, low, high)` — 같은 타입, 유사도 [0.60, FUZZY_MATCH_THRESHOLD) 구간 쌍 탐색
  - `_ask_llm_batch(llm_client, batch)` — 최대 20쌍씩 LLM에 질의, JSON 응답으로 merge 여부 결정
  - `llm_dedup(graph)` — 확인된 쌍을 degree 기준으로 canonical 선택 후 병합
  - Person 포함 (Category만 제외) — `인소영` / `인소영 교수님` 등 처리 가능
  - LLM API 오류 시 조용히 스킵 (그래프 보존)
- `app/api/graph.py` (수정)
  - `semantic_dedup` 직후 `llm_dedup` 호출 추가 (progress 73%)
  - 2026-05-29 후속: `isolated_reextract` 이후 `llm_dedup` 2차 호출 추가
- `tests/test_utils/test_llm_dedup.py` (신규) — 9개 테스트
- Git commit: `243b177`

### 검증

- `python3 -m pytest tests/ -q` → **165 passed, 24 warnings**
- Frontend build: 성공
- Frontend dev server: `http://localhost:5174` (PID 4102684)

### LLM Dedup 동작 확인 결과

- 이전 빌드(21:01~21:02) 로그에서 확인:
  - `기후변화 회의` ← `기후변화협약 컨퍼런스` (Event) 병합 ✅
  - `인소영 교수님` ← `인소영` (Person) 병합 ✅
- 현재 빌드(21:03)에서 LLM dedup 시점에 후보 0개 → `isolated_reextract` 이후 15개 후보 생성됨
- 2026-05-29 후속으로 `isolated_reextract` 이후 LLM dedup 2차 실행 반영 완료

### 알려진 잔여 이슈

- `인소영` / `인소영 교수님` 현재 저장된 빌드에서는 여전히 별도 노드일 수 있음 — 새 그래프 빌드에서 2차 dedup 효과 확인 필요

---

## Completed In This Session (2026-05-28 LLM Inference Params + Thinking Mode)

### 변경 내역

**LLM 추론 파라미터 설정**

- `app/config.py` (수정)
  - 7개 LLM 추론 파라미터 추가:
    ```
    LLM_TEMPERATURE: float = 1.0
    LLM_TOP_P: float = 0.95
    LLM_TOP_K: int = 20
    LLM_MIN_P: float = 0.0
    LLM_PRESENCE_PENALTY: float = 1.5
    LLM_REPETITION_PENALTY: float = 1.0
    LLM_THINKING_MODE: bool = True
    ```
- `src/backend/.env` (gitignored, 수동 설정)
  - 위 7개 파라미터 설정값 추가

**Thinking Mode + `<think>` 블록 필터링**

- `app/utils/llm_client.py` (전면 재작성)
  - `_inference_params()`: `top_k`, `min_p`, `repetition_penalty`를 `extra_body`로 전달; `LLM_THINKING_MODE=True`이면 `extra_body.chat_template_kwargs.enable_thinking=True` 추가
  - `_strip_think()`: `<think>.*?</think>` 정규식으로 비스트리밍 응답에서 think 블록 제거
  - `chat()`: `asyncio.wait_for` + `_strip_think` 적용
  - `chat_json()`: `chat()` 기반으로 JSON 파싱
  - `stream()`: 상태 머신(`in_think`, `buf`)으로 청크 경계에서도 think 블록 안전하게 필터링

### 그래프 빌드 전체 비교

| 빌드 | 날짜 | Nodes | Edges | Isolated | Person | 주요 특징 |
|------|------|-------|-------|----------|--------|-----------|
| 베이스라인 | 2026-05-27 초 | 203 | 212 | ~51 (25%) | ? | 이전 세션 기준 |
| Build #1 (P1/P2/P3) | 2026-05-27 | 243 | 267 | 24 (9.9%) | 8 | EntityResolver, cascade reextract, health API |
| Build #2 (EntityResolver 임베딩) | 2026-05-27 말 | 214 | 232 | 26 (12.1%) | 8 | BGE-M3 활성화, 6개 cross-lingual 매칭 |
| **Build #3 (Thinking Mode)** | **2026-05-28** | **172** | **165** | **32 (18.6%)** | **3** | thinking mode 활성화 |

### Build #3 Thinking Mode 효과 분석

**긍정적:**
- Person 노이즈 완전 제거: `발화자`, `패널`, `사회자`, `화자`, `유엔기후변화협약` Person 노드 사라짐
- 실제 인물 3명만 유지 (양필성, 인소영, 인소영 교수님)
- Role 분류 개선: `팀 리더` → `Role:Team Leader` 올바르게 분류; Role 노드 7→12개 증가
- 전반적 정밀도 향상: 불확실하면 추출하지 않는 방향으로 동작

**트레이드오프:**
- 전체 노드/엣지 수 감소 (243→172): 보수적 추출로 일부 유효 엔티티 누락 가능
- 고립 노드 비율 증가: 12.1% → 18.6% (32개)
- `인소영` / `인소영 교수님` 여전히 별도 노드 (fuzzy threshold 미통과)

### 커밋

- `feae7da` — feat: add LLM inference parameters and thinking mode support
- Push: 완료 (GitHub `main` 브랜치)

## Completed In This Session (2026-05-27 P1/P2/P3 Improvements)

### 변경 내역

**P1 — 증분 처리 + 엔티티 해소 (iText2KG 패턴)**

- `app/services/document_hash_store.py` (신규)
  - 파일별 MD5 해시 + 온톨로지 해시를 `hashes.json`에 저장
  - `get_changed_files()` — 온톨로지 변경 시 전체, 파일 변경 시 해당 파일만 반환
- `app/utils/entity_resolver.py` (신규)
  - `find_existing_node()` — SequenceMatcher fuzzy match (동기)
  - `find_existing_node_async()` — fuzzy 우선, BGE-M3 코사인 유사도 fallback (비동기)
  - `EMBEDDING_BASE_URL` 미설정 시 임베딩 완전 스킵
- `app/agents/graph_builder_agent.py` (수정)
  - `_find_existing_node` → EntityResolver 위임
  - `_fuzzy_match` 제거 (EntityResolver 내부로 이동)
  - `_merge_into_graph` → `async def`로 변경, `find_existing_node_async` 호출
- `app/api/graph.py` (수정)
  - `_run_graph`에 DocumentHashStore 연동
  - `incremental=True`일 때 변경된 파일의 청크만 처리, 나머지 스킵
  - 그래프 저장 후 `hash_store.save()`로 해시 영속화

**P2 — Index-First QueryAgent**

- `app/agents/obsidian_writer_agent.py` (수정)
  - `_write_index(vault, graph)` 추가 — 엔티티 이름을 타입별로 정리한 `_index.md` 생성
  - `run()` 종료 직전에 호출
- `app/agents/query_agent.py` (수정)
  - `_search_graph` 재작성: 이름 substring 매칭 2.0점, 설명 단어 매칭 1.0점으로 점수화
  - 결과 점수 내림차순 정렬, 최대 10개 제한
  - BFS `seen_bfs` 세트로 중복 제거

**P3 — 그래프 헬스체크 API**

- `app/utils/graph_health.py` (신규)
  - `check_isolated_nodes()` — degree 0 노드
  - `check_weak_components()` — 약하게 연결된 컴포넌트, 크기 내림차순
  - `check_duplicate_candidates()` — 같은 타입 내 유사 이름 쌍 (SequenceMatcher)
  - `check_hub_nodes()` — degree 초과 노드
  - `run_health_check()` — 4가지 결과 + summary 반환
- `app/api/graph.py` (수정)
  - `GET /api/projects/{id}/graph/health` 엔드포인트 추가

### 검증

- Backend full test suite:
  - `cd src/backend && python3 -m pytest tests/ -q`
  - Result: `156 passed, 24 warnings`
- Smoke test (project `29347d1e`):
  - 그래프: 노드 243개, 엣지 267개, 고립 24개
  - Health API: `components=25, duplicate_candidates=0, hub_nodes=3`
- Git commits: 8개 (`6ed446c` → `6f86e37`)
- Push: 완료

### 알려진 잔여 이슈

- 고립 노드 24개 중 상당수가 노이즈성 Skill (entity_validation 필터로 추가 제거 가능)
- `_index.md` 생성은 vault write 시에만 업데이트 (그래프 재빌드 후 vault 재실행 필요)
- 임베딩 기반 EntityResolver는 새 그래프 빌드 시 처음 효과 확인 가능

## Completed In This Session (2026-05-27 README + Timeout Follow-up)

### 변경 내역

- `README.md`
  - 프로젝트 개요, stack, local run, config, project-specific logs, test commands를 간단히 작성.
- `app/config.py`
  - `LLM_REQUEST_TIMEOUT: 120.0` 추가.
- `app/utils/llm_client.py`
  - OpenAI-compatible LLM 호출을 `asyncio.wait_for()`로 감싸서 chunk 처리 중 무기한 대기를 줄임.
- `app/api/graph.py`
  - 기존 `ontology.json`이 오래되어도 최신 `OntologyAgent.FIXED_EDGE_TYPES`가 graph build 시 보강되도록 처리.
  - 이 보강은 `HAS_ROLE`이 기존 ontology 파일에 없어서 계속 invalid relation으로 skip되던 문제를 해결하기 위한 것.

### 검증

- Backend full test suite:
  - `cd src/backend && python3 -m pytest tests/ -q`
  - Result: `134 passed, 24 warnings`
- Frontend production build:
  - `cd src/frontend && npm run build`
  - Result: success
  - Warning remains: Vite large chunk over 500 kB
- `git diff --check`
  - Result: clean

### 실행 상태

- Backend was restarted once after the timeout/fixed-edge changes.
- Graph task `f34dcf5c-0051-487a-976a-381ff3d3066f` was started, reached at least chunk `21/39`, then backend was stopped due to the user's latest instruction to stop.
- Previous graph task `ce0006da-765b-4648-a76e-cfe6acf678be` stalled around chunk `32/39`; this was the reason for adding explicit LLM timeout.
- Backend is currently stopped.
- Frontend dev server may still be running on `5174`.

## Completed In This Session (2026-05-27 Alias + Noise Cleanup)

### 핵심 판단

- `Skill`/`Technology`는 계속 단일 `Skill`로 유지.
- 사용자 별칭은 LLM 프롬프트, Person 정규화, Person merge, Category hub 기준에서 모두 같은 이름 variant로 취급.
- `HAS_ROLE`은 실제 career graph에서 자연스러운 Person → Role 관계라 고정 관계에 추가.
- `APPLIED_TO`는 새 관계로 늘리지 않고, Project/Skill 방향에 따라 `USES_SKILL`로 정규화.
- `INTERESTED_IN`, `CONTAINS`, `IDENTICAL`은 의미가 넓거나 dedup 정책과 충돌할 수 있어 아직 버림.

### 변경 내역

- `app/utils/user_config.py` 신규
  - user.json의 `name`, `display_name`, `aliases`를 공통 variant 목록으로 제공
  - 문자열 alias와 배열 alias 모두 처리
- `src/backend/user.json`
  - `aliases: ["Phil"]` 추가
- `app/api/user.py`
  - `aliases` 저장/조회 스키마 추가
  - 빈 alias는 저장하지 않음
- `app/agents/graph_builder_agent.py`
  - 프롬프트의 document owner context에 aliases 포함
  - Person name normalization에서 alias도 canonical user name으로 병합
  - `APPLIED_TO Skill -> Project`를 `Project -> Skill / USES_SKILL`로 뒤집음
  - `APPLIED_TO Project -> Skill`은 `USES_SKILL`로 변환
  - `HAS_ROLE` 프롬프트 지침 추가
- `app/agents/ontology_agent.py`
  - fixed edge type에 `HAS_ROLE` 추가
- `app/utils/entity_validation.py`
  - `4학년`, `LLM팀 근무`, `연구자`, `리더`, `석사`, `panelists`, `Presenter`, `Jeju`, `긍정적인 에너지 전달`, `사회자 언급 분석`, `패널 정보 분석`, `30% performance improvement as Skill` 등 노이즈 필터 추가
- `app/utils/semantic_dedup.py`
  - user Person merge에서 aliases 지원
  - canonical은 alias가 아니라 `name` 우선으로 선택
- `app/utils/graph_restructure.py`
  - category hub center 판정에 aliases 포함

### 검증

- Targeted backend tests:
  - `python3 -m pytest tests/test_utils/test_entity_validation.py tests/test_agents/test_graph_builder_agent.py tests/test_utils/test_semantic_dedup.py tests/test_api/test_user_api.py tests/test_utils/test_graph_restructure.py -q`
  - Result: `48 passed`
- Backend full test suite:
  - `cd src/backend && python3 -m pytest tests/ -q`
  - Result: `134 passed, 24 warnings`

## Completed In This Session (2026-05-27 Project Logs + Skill Unification)

### 핵심 판단

- 현재 UI 목적은 핵심 키워드/역량 그래프 시각화이므로 `Skill`과 `Technology`를 분리하지 않기로 함.
- `Technology`는 `Skill`로 흡수. 새 ontology에는 `Technology`를 생성하지 않고, 기존 graph/ontology에 남아 있는 `Technology`도 runtime에서 `Skill`로 정규화.

### 변경 내역

- `app/agents/ontology_agent.py`
  - 고정 엔티티 타입 10개 → 9개: `Technology` 제거
  - 기술 키워드, 도구, 프레임워크, 모델명은 모두 `Skill`로 분류하도록 프롬프트 수정
- `app/agents/graph_builder_agent.py`
  - ontology entity type 로드 시 `Technology -> Skill` 정규화
  - LLM 응답 entity type도 `Technology -> Skill`로 정규화
  - user.json의 `name` + `display_name`이 합쳐져 나오는 `양필성 / Pilseong Yang`을 canonical `양필성`으로 정규화
  - 관계 alias 추가:
    - `LEAD_BY -> LED_BY`
    - `USED_IN` with `Skill -> Project`를 `Project -> Skill / USES_SKILL`로 뒤집어 저장
  - LLM이 `null` source/target/type/relation을 반환해도 chunk 전체가 실패하지 않도록 null-safe 처리
  - Project-Skill 관계 추출 프롬프트 강화
- `app/utils/graph_normalization.py` 신규
  - `normalize_ontology_types()`
  - `normalize_graph_entity_types()`
  - legacy graph/ontology의 `Technology`를 `Skill`로 변환하고 충돌 시 노드 병합
- `app/utils/entity_validation.py`
  - `Technology` alias는 허용하되 canonical type은 `Skill`
  - Person/Role/Project/Organization/Event/Achievement 노이즈 필터 강화
  - `교수님`, `사회자`, `패널`, `학부 4학년`, `석사 과정`, `약 1년간 근무`, `GPT/Gemini as Project` 등 주요 오분류 제거
- `app/utils/logger.py`
  - project context 기반 파일 라우팅 추가
  - background 작업 중 agent/backend 로그가 `logs/projects/{project_id}/projectos.log`에도 저장됨
- `app/services/task_manager.py`
  - task 생성/업데이트를 `logs/projects/{project_id}/tasks.log` JSONL로 저장
  - UI 진행률과 동일한 정량 메시지가 프로젝트별로 누적됨
- `app/api/graph.py`, `app/api/projects.py`
  - parse/ontology/graph/profile/analysis background task에 project log context 주입
  - graph/ontology/stats/global graph 조회 시 legacy `Technology`도 `Skill`로 정규화해서 반환
- `app/agents/obsidian_writer_agent.py`
  - `Category` 노드는 Obsidian markdown 노트로 쓰지 않음. UI graph 구조용으로만 유지
- Frontend
  - `Technology` 색상/표시 제거
  - About 설명을 9개 엔티티 타입 기준으로 수정

### 최종 재생성 결과

- 최종 task: `628cc62c-6de0-4635-94c5-c70323487594`
- 완료 메시지: `완료: 노드 203개, 엣지 212개`
- Graph stats:
  - Person 3
  - Project 28
  - Skill 93
  - Achievement 32
  - Role 13
  - Organization 10
  - Institution 8
  - Event 8
  - Category 8
- `Technology` 노드: 0개
- `Project -> Skill / USES_SKILL` 엣지: 45개
- `Skill -> Project` 역방향 엣지: 0개
- Category vault note: 생성 안 됨 (`Misc/Skills.md` 없음)
- Vault files: 198개 (`vault/29347d1e`)
- 프로젝트별 로그:
  - `logs/projects/29347d1e/projectos.log`
  - `logs/projects/29347d1e/tasks.log`
  - 중단된 이전 실행 로그는 `logs/projects/29347d1e/archive/`로 이동

### 검증

- Backend full test suite:
  - `cd src/backend && python3 -m pytest tests/ -q`
  - Result at that point: `129 passed, 24 warnings`
- Frontend production build:
  - `cd src/frontend && npm run build`
  - Result: success
  - Warning remains: Vite large chunk over 500 kB

### 알려진 잔여 이슈

- 이 섹션의 잔여 이슈 중 `Phil`, `HAS_ROLE`, `APPLIED_TO`, 주요 Skill/Role noise 일부는 다음 세션에서 해결됨.
- `INTERESTED_IN`, `CONTAINS`, `IDENTICAL`은 아직 정책상 버림.

## Completed In This Session (2026-05-27 User Name Context Injection)

### 배경

CV 목록 형식 (`● Total GPA 4.35/4.50`) 에서 주어가 없어 LLM이 관계 추출 실패. 사용자 이름을 프롬프트에 명시하여 implicit subject 처리.

### 변경 내역

- `app/agents/graph_builder_agent.py`:
  - `_load_user_context()` 정적 메서드 추가: user.json에서 `name` + `display_name` 두 이름 읽어 프롬프트 스니펫 생성
    - 출력 예: `"Document owner: 양필성 / Pilseong Yang. When the subject of an item is not explicitly stated (e.g. bullet-list entries in a CV or resume), treat 양필성 / Pilseong Yang as the implicit subject and extract relations accordingly."`
  - `__init__`에서 `self._user_context = self._load_user_context()` 초기화
  - `_extract_from_chunk()` 수정: user_context를 프롬프트 상단에 삽입 (허용 엔티티/관계 목록 앞)
- `tests/test_agents/test_graph_builder_agent.py`: 3개 테스트 추가
  - `test_user_context_includes_both_names` — user.json 있을 때 양필성 + Pilseong Yang 포함 확인
  - `test_user_context_empty_when_no_user_json` — user.json 없으면 빈 문자열
  - `test_prompt_contains_user_context` — 실제 프롬프트에 두 이름 포함 확인

### 검증

- `python3 -m pytest tests/ -q` → **117 passed**
- 그래프 재빌드 결과:
  - 노드 215개, 엣지 177개 (이전: 180노드, 157엣지)
  - 고립 노드: 68개 → 51개 (37.8% → 23.7% isolation rate)
  - 재추출 7/61 연결, semantic dedup 8개 병합
  - Category 허브 9개 생성

### 알려진 한계

- 고립 노드 51개 중 상당수는 노이즈 엔티티 (교수님, 패널, 사회자 등 entity_validation 미통과 항목들이 여전히 추출됨)
- CV 목록의 암시적 주어 처리는 향상됐으나, 긴 설명형 엔티티 이름은 여전히 추출 품질이 낮음

## Completed In This Session (2026-05-27 Isolated Node Cascade Re-extraction)

### 배경

173개 노드 중 72개(42%)가 고립(degree=0). 원인: LLM이 엔티티는 추출하지만 청크에 명시적 주어가 없으면 관계 추출 실패 (예: CV 목록 형식 `● Total GPA 4.35/4.50`).

### 변경 내역

- `app/utils/isolated_reextract.py` (신규): `reextract_isolated_nodes()` cascade 함수
  - **Pass 2**: 고립 노드의 source_file에서 노드명을 언급하는 청크 탐색 → ±2 이웃 청크 윈도우로 재추출
  - **Pass 3**: 여전히 고립이면 같은 파일의 첫 2청크(문서 헤더) 추가 후 재추출
  - 동일 컨텍스트 윈도우 중복 LLM 호출 방지 (seen_contexts 캐시)
  - Category 타입 노드는 스킵
- `app/agents/graph_builder_agent.py`: `reextract_with_context()` 메서드 추가
  - 합성 청크로 `_extract_from_chunk` 호출 → `_merge_into_graph`로 새 엣지만 추가
  - 새 노드 추가도 허용 (fuzzy match로 기존 노드 우선 매칭)
- `app/api/graph.py` `_run_graph()`: dedup → **reextract_isolated_nodes** → add_category_hubs 순서
  - progress 72~80% 구간에서 재추출 진행 메시지 표시
- `tests/test_utils/test_isolated_reextract.py` (신규): 9개 테스트

### 검증

- `python3 -m pytest tests/ -v` → **114 passed** (user context 추가 후 117 passed)
- 실제 효과: 61개 고립 노드 중 7개 재연결 성공 (11%)

### 알려진 한계

- Pass 2/3에서도 실패하면 노드는 고립 유지 (제거하지 않음)
- 재추출 시 새 잘못된 노드가 추가될 가능성 있음 (entity_validation 필터가 1차 방어)
- LLM이 같은 내용을 반복 추출하는 오버헤드: 72개 고립 → seen_contexts 캐시로 실제 호출은 ~15-25회 예상

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

## Completed In This Session (2026-06-01 Graph Detail + Obsidian Project Delete)

- Graph/detail role split:
  - `graph_restructure.py` now promotes independent primary entities under category hubs even when they only appeared through semantic links such as `Project -> Skill`.
  - Project context leaves that look like implementation details/features can be demoted into project `context_items` instead of remaining graph nodes.
  - `build_entity_details()` creates type-specific structured `details.sections` for primary entities.
  - Graph API runs context demotion, category hub creation, and detail generation before saving.
  - `GET /graph` also backfills details for existing graphs returned to the frontend.
- Obsidian entity page rendering:
  - `ObsidianWriterAgent.build_payload()` now ensures details are generated before notes are rendered.
  - Notes render `## Details` before `## Sources`.
  - Sources in generated markdown now show file names only; chunk IDs remain in graph JSON provenance but are not rendered in pages.
- Obsidian plugin project management:
  - Project delete button added to the Project tab.
  - Delete calls backend `DELETE /api/projects/{id}` and clears selected project settings when applicable.
  - Delete now also removes the local Obsidian sync folder for that project:
    - selected project with explicit `targetFolder` deletes that explicit folder
    - non-selected projects delete `ProjectOS/{project name}`
    - unsafe paths such as empty paths, `.obsidian`, or paths containing `..` are rejected
  - Collect flow now runs `upload(parse) -> ontology -> graph`; previous `upload -> graph` failed on new projects because `ontology.json` did not exist.
- Live verification on project `0ceaa5b9` / `KAIST CV`:
  - Initial graph run failed as expected before the Collect fix: missing `projects/0ceaa5b9/ontology.json`.
  - Manual recovery run completed:
    - ontology task `37e0d019-5d32-442c-ab37-dbfa4f488a06`: completed, 9 entity types
    - graph task `35aa0b13-b3a1-4c9c-a7d3-e50cb8336a84`: completed, 120 nodes / 162 edges
  - Applied latest writer/detail post-processing to the completed graph without rerunning LLM extraction:
    - 112 entity pages contain `## Details`
    - generated markdown contains 0 `Chunks:` lines
    - graph health: isolated `0`, components `1`, graph/vault mismatch `0`
    - remaining health notes: duplicate candidate `AI-Based Simulation` vs `Agent-Based Simulation`; duplicate page label for `master's program`
- Verification:
  - `cd src/backend && pytest tests/test_agents/test_obsidian_writer_agent.py tests/test_api/test_projects_api.py tests/test_utils/test_graph_restructure.py` -> `53 passed`
  - `cd src/backend && pytest tests/test_agents/test_graph_builder_agent.py tests/test_agents/test_claude_task_graph_builder_agent.py tests/test_api/test_projects_api.py` -> `40 passed`
  - `cd src/backend && pytest tests/test_utils/test_graph_health.py tests/test_utils/test_isolated_reextract.py` -> `19 passed`
  - `cd src/frontend && npm run build` -> success; large chunk warning remains
  - `cd src/obsidian-plugin && npm test` -> `11 passed`
  - `cd src/obsidian-plugin && npm run build` -> success
- Runtime note:
  - The currently running backend on port `8002` did not include the latest backend source changes during the first live run. Restart backend before relying on future graph builds to apply detail/source changes automatically.
