# User Config + Profile Generation Refactor Design

**Date:** 2026-05-26  
**Scope:** User 설정, 프로필 생성 분리, Role 추출 개선

---

## Goal

1. 앱 최초 실행 시 사용자 이름을 받아 저장한다.
2. 그래프 빌드와 프로필 생성을 분리한다.
3. 프로필 생성 시 저장된 사용자 이름으로 Person 노드를 자동 매칭한다.
4. Role 추출 기준을 공식 직함/직위로 좁힌다.

---

## Architecture

### 전체 흐름

```
최초 방문
  └─ user.json 없음 → 이름 입력 모달 → POST /api/user → user.json 저장

프로젝트 작업
  └─ 프로젝트 생성 → 파일 업로드 → 온톨로지 → 그래프 빌드 (graph.json + vault 초기 생성)
                                                          ↓
                                               프로필 생성 버튼 클릭
                                                          ↓
                                          POST /api/projects/{id}/profiles
                                          └─ user.json name → fuzzy match Person 노드
                                          └─ profiles.json 생성 + vault Person 노드 업데이트
```

---

## Backend

### User Config

**파일:** `{PROJECTS_DIR}/../user.json` (프로젝트 루트 기준 `src/backend/user.json`)  
**환경변수:** `USER_CONFIG_PATH` (기본값 `./user.json`, `config.py`에 추가)

```json
{
  "name": "양필성",
  "display_name": "Pilseong Yang"
}
```

**API:**

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/user` | user.json 반환. 없으면 `404` |
| `POST` | `/api/user` | `{"name": str, "display_name": str}` 저장 |

**파일:** `src/backend/app/api/user.py` (신규)  
**등록:** `app/main.py`에 `user_router` prefix `/api/user`

---

### Graph Build — Profile/Vault 분리

`graph.py` `_run_graph()` 에서 ProfileAgent, ObsidianWriterAgent 호출 제거.  
그래프 빌드 완료 후 vault는 **그래프 노드 기반**으로만 초기 생성 (Person profile 없이).

변경 전:
```
_run_graph: graph → profiles → vault
```

변경 후:
```
_run_graph:    graph → vault (profiles 없이)
_run_profiles: profiles (user name fuzzy match) → vault Person 노드 업데이트
```

`ObsidianWriterAgent.run()`에 `profiles` 파라미터를 optional로 변경:
- `profiles=None` → Person 노드 기본 메모만 작성
- `profiles=[...]` → Person 노드에 profile summary 추가

---

### Profile Generation Endpoint

**신규:** `POST /api/projects/{id}/profiles`

```python
async def run_profiles(project_id: str):
    # graph.json 존재 확인
    # user.json 로드 → name
    # task 생성 → _run_profiles 백그라운드 실행
    return {"task_id": ...}
```

**`_run_profiles()` 로직:**
1. `graph.json` 로드
2. `user.json`에서 이름 로드 (없으면 오류)
3. 그래프에서 user name과 fuzzy match되는 Person 노드 탐색
   - `SequenceMatcher ratio >= 0.7` (display_name, name 둘 다 시도)
   - 매칭 실패 → degree 가장 높은 Person으로 fallback + `logger.warning`
4. 매칭된 Person에 대해 BFS 컨텍스트 수집 (기존 ProfileAgent 로직 유지, 최대 50노드)
5. LLM 프로필 생성 → `profiles.json` 저장
6. `ObsidianWriterAgent.run(graph, profiles, vault_path, delta=True)` 로 vault 업데이트

**기존 `GET /api/projects/{id}/profiles`** 유지.

---

### ProfileAgent 변경

`run()` 시그니처 변경:

```python
async def run(
    self,
    graph: nx.DiGraph,
    person_ids: list[str] | None = None,   # None → user.json 기반 매칭 (호출자가 처리)
    progress_callback: ... | None = None,
) -> list[CareerProfile]:
```

실제 user name 매칭 로직은 `_run_profiles()`(API 레이어)에서 처리.  
ProfileAgent는 `person_ids`로 넘겨받은 노드만 처리.

---

### Role 추출 규칙 강화

`graph_builder_agent.py` 프롬프트에 추가:

```
Role extraction rules:
- Role is ONLY for formal job titles or academic positions that could appear on a resume or business card.
  Examples: "Research Engineer", "PhD Student", "Professor", "Team Lead", "Software Engineer", "Undergraduate Researcher"
- Do NOT use Role for: activity descriptions, responsibilities, task descriptions, generic participant labels,
  or phrases describing what someone did. Examples to EXCLUDE: "발표자", "사회자", "데이터 검수",
  "약 1년간 근무", "지역 주민", "기업", "투자자", "reviewing model evaluation frameworks".
- If an item describes a concrete outcome or result → use Achievement.
- If an item describes participation in an event → use Event (not Role).
- If an item is a vague description or generic label → do not extract it as any entity.
```

---

## Frontend

### 최초 방문 모달 (`UserSetupModal.vue`)

- `GET /api/user` → 404이면 모달 표시
- 이름(name), 표시이름(display_name) 입력
- `POST /api/user` 후 모달 닫기
- `App.vue` 또는 `HomeView.vue`의 `onMounted`에서 체크

### 프로필 생성 섹션 (`ProjectDetail.vue`)

그래프 빌드 완료 후 사이드바에 "프로필 생성" 섹션 추가:
- `profiles.json` 없음 → "프로필 생성" 버튼 (POST /api/projects/{id}/profiles)
- `profiles.json` 있음 → "프로필 보기" + "재생성" 버튼
- ProgressPanel로 진행 표시

### API Client (`client.js`)

```js
export const userApi = {
  get: () => api.get('/user'),
  set: (data) => api.post('/user', data),
}

// projectsApi에 추가
runProfiles: (id) => api.post(`/projects/${id}/profiles`),
```

---

## Data Model

`CareerProfile` 모델 변경 없음.  
`user.json` 스키마:

```json
{
  "name": "양필성",
  "display_name": "Pilseong Yang"
}
```

---

## Testing

| 테스트 파일 | 항목 |
|------------|------|
| `test_api/test_user_api.py` | GET 404 (미설정), POST 저장, GET 200 |
| `test_agents/test_profile_agent.py` | person_ids 필터, 빈 그래프 처리 |
| `test_api/test_projects_api.py` | profiles 엔드포인트 400 (graph 없음), 200 (task_id 반환) |

---

## File Map

| 파일 | 변경 유형 |
|------|----------|
| `src/backend/app/config.py` | `USER_CONFIG_PATH` 추가 |
| `src/backend/app/api/user.py` | 신규 |
| `src/backend/app/main.py` | user_router 등록 |
| `src/backend/app/api/graph.py` | `_run_graph()`에서 profile/vault 분리 |
| `src/backend/app/api/projects.py` | `POST/GET /{id}/profiles` 엔드포인트 이동 |
| `src/backend/app/agents/profile_agent.py` | `person_ids` 파라미터 추가 |
| `src/backend/app/agents/obsidian_writer_agent.py` | `profiles` optional 처리 |
| `src/backend/app/agents/graph_builder_agent.py` | Role 프롬프트 강화 |
| `src/backend/tests/test_api/test_user_api.py` | 신규 |
| `src/backend/tests/test_agents/test_profile_agent.py` | person_ids 테스트 |
| `src/frontend/src/api/client.js` | userApi, runProfiles 추가 |
| `src/frontend/src/components/UserSetupModal.vue` | 신규 |
| `src/frontend/src/views/HomeView.vue` | UserSetupModal 연동 |
| `src/frontend/src/views/ProjectDetail.vue` | 프로필 생성 섹션 추가 |

---

## Known Constraints

- 단일 사용자 전제 (user.json 1개)
- `display_name` fuzzy match 실패 시 degree-based fallback은 Person 노드가 1개 이상 있어야 동작
- Vault 업데이트는 `delta=True`로 Person 노드만 덮어씀 (다른 노드는 건드리지 않음)
