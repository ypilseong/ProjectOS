# Claude Code Handoff

Last updated: 2026-05-27

## Current Objective

P1/P2/P3 improvements implemented and verified. All 8 tasks complete. Backend running on port 8001 with latest code.

## 다음 작업 후보

1. **그래프 재생성** — 새 코드(EntityResolver 임베딩 매칭)로 프로젝트 `29347d1e` 그래프를 재빌드해서 품질 변화 확인
2. **고립 노드 필터 강화** — 현재 24개 고립 노드 중 노이즈성 Skill(`발언자 특정`, `풍력 발전기` 등) entity_validation에 추가
3. **`INTERESTED_IN`, `CONTAINS`, `IDENTICAL` 관계** — 계속 버릴지 명시적 관계로 추가할지 결정
4. **Graph health UI** — `/api/projects/{id}/graph/health` 결과를 프론트엔드에 표시하는 진단 패널
5. **WritingAgent** — 그래프 품질이 충분히 올라간 후 이력서/자기소개서 초안 생성 에이전트

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
