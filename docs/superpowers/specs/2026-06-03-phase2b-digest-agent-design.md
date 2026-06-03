# Phase 2b — Scheduled Digest Agent 설계

**Date**: 2026-06-03
**Status**: Design (구현 전, 승인 대기)
**상위 문서**: [ProjectOS × OpenJarvis 방향성](2026-06-02-projectos-openjarvis-direction.md) §4.1
**선행**: Phase 1 (routing/budget guard, trace sink) + Phase 2a (Continuous File Watcher) 완료

---

## 0. 한 줄 요약

매일 정해진 시각에 각 프로젝트의 vault·graph 변화를 합성한 **브리핑(digest)** 을 `Digests/YYYY-MM-DD.md` 로 생성한다. 기존 `graph_health` + `analysis.json` 을 **결정론적으로 재사용**(새 LLM 호출 0회)하며, Phase 2a 워처와 동일한 단일 asyncio 백그라운드 태스크로 구동된다. 사용자가 트리거하지 않아도 "오늘의 그래프 상태"를 능동적으로 요약해 주는 살아있는 비서의 두 번째 가시적 성과.

---

## 1. 목표와 비목표

### 목표
- 매일 1회(설정 시각) 빌드 완료 프로젝트마다 digest 생성.
- digest 내용: 신규 노드, 고립 노드 경고, source 누락 노드 경고, AnalysisAgent가 찾은 약점 요약, "다음에 보강할 항목" 제안.
- 기존 인프라(`run_health_check`, `analysis.json`, `record_trace`, vault 디렉터리) 최대 재사용. **digest 자체는 LLM을 호출하지 않는다**(저비용·결정론·테스트 용이).
- 즉시 생성용 수동 API + digest 조회 API 노출(플러그인이 추후 폴링 가능).
- 안전: opt-in, 단일 인스턴스, 멱등(같은 날 재실행 시 덮어쓰기), 프로젝트별 예외 격리.

### 비목표
- **삭제/변경 노드 추적 안 함** — "신규 노드"만 보고. 노드 제거 diff는 별도 단계.
- **로컬 LLM 합성 안 함** — 산문 다듬기는 향후 옵션. 이번엔 결정론적 템플릿만.
- **플러그인 배지 UI 안 함** — 백엔드 API만 노출. Svelte 배지는 후속(프런트 작업과 분리).
- **주간/월간 digest 안 함** — 일일만. cadence 일반화는 수요 확인 후.
- **AnalysisAgent 재실행 안 함** — 가장 최근 `analysis.json` 을 재사용. digest가 분석을 새로 돌리지 않음.

---

## 2. 설계 근거

### 2.1 왜 결정론적 템플릿인가
- `run_health_check` 는 이미 LLM 없이 고립 노드·weak component·source 누락·중복 후보를 계산한다(`app/utils/graph_health.py`).
- `AnalysisAgent` 의 약점 분석은 이미 `projects/<id>/analysis.json` 에 저장된다(`app/api/projects.py:_run_analysis`).
- 따라서 digest는 이 두 산출물을 **읽어서 조립**하면 충분하다. 새 LLM 호출은 불필요하며, 방향성 문서 §7이 경고하는 비용 폭주 리스크가 0이 된다.
- 출력이 입력에 대해 결정론적이므로 단위 테스트가 단순하다(LLM mock 불필요).

### 2.2 왜 Phase 2a 워처와 같은 패턴인가
- 이미 `WatcherService`(`app/services/watcher.py`)가 `lifespan` 단일 asyncio 태스크로 검증됐다. APScheduler 등 새 의존성을 들이지 않고 동일 구조를 재사용한다.
- 단일 태스크 = 본질적 single-instance(좀비/중복 없음). `DIGEST_ENABLED=False` 면 시작 안 함.

### 2.3 왜 수동 API + 조회 API인가
- 수동 `POST` 엔드포인트가 있어야 즉시 확인·테스트가 쉽다.
- 조회 `GET` 엔드포인트를 두면 플러그인이 추후 폴링해서 "새 digest" 배지를 붙일 수 있다(이번 spec은 백엔드만, UI는 후속).

---

## 3. 아키텍처

```
main.py (lifespan)
  └─ DigestService.start()  →  asyncio.create_task(loop)   # DIGEST_ENABLED일 때만
        loop: 매 DIGEST_POLL_SECONDS
          └─ if should_run(now, last_run_date, DIGEST_HOUR):
               for each 빌드완료 프로젝트:
                   generate_digest(project_id, trigger="scheduled")
               last_run_date = today

api/digest.py (신규 라우터, main.py에서 prefix="/api/projects"로 등록)
  POST /{id}/digest          →  generate_digest(id, trigger="manual")  →  결과 반환
  GET  /{id}/digests         →  날짜 목록
  GET  /{id}/digests/{date}  →  단건 마크다운
  (외부 경로는 /api/projects/{id}/digest 등)
```

`compose_digest`(순수 데이터·렌더) ↔ `generate_digest`(부수효과: 파일 기록·state 갱신·trace) 를 분리해 테스트 가능성을 확보한다.

---

## 4. 컴포넌트 (각 단일 책임)

| 유닛 | 파일 | 책임 | 의존 |
|------|------|------|------|
| `compose_digest(project_id) -> dict` | `app/services/digest.py` (신규) | graph 로드 → health check → 신규노드 diff → analysis 재사용 → 보강제안 → 마크다운 렌더. **부수효과 없음** | graph_health, networkx, config |
| `generate_digest(project_id, trigger) -> dict` | 위 파일 | compose 호출 → `Digests/<date>.md` 기록 → `digest_state.json` 갱신 → `record_trace` | compose_digest, trace |
| `should_run(now, last_run_date, hour) -> bool` | 위 파일 | 순수 함수: 날짜가 바뀌었고 `now.hour >= hour` 면 True | 없음 |
| `_reinforcement_suggestions(health, analysis) -> list[str]` | 위 파일 | health/analysis에서 결정론적 제안 문자열 도출 | 없음 |
| `_render_markdown(...) -> str` | 위 파일 | 구조화 데이터 → 마크다운 문자열 | 없음 |
| `DigestService` | 위 파일 | 폴링 루프, opt-in start/stop, 프로젝트 순회, 프로젝트별 try/except | config, generate_digest |
| digest 라우터 | `app/api/digest.py` (신규) | POST 생성 / GET 목록 / GET 단건 | generate_digest, compose |

**경계**: `DigestService` 는 스케줄링만. 실제 합성/기록은 `generate_digest` 에 위임. `compose_digest` 는 부수효과가 없어 독립 테스트 가능.

---

## 5. 데이터 흐름 (`compose_digest` 한 번)

1. `PROJECTS_DIR/<id>/graph.json` 로드 → `nx.node_link_graph`. 없으면 `None` 반환(상위에서 스킵/404).
2. `run_health_check(graph, vault_path=str(VAULT_DIR/<id>))` 호출.
3. `PROJECTS_DIR/<id>/digest_state.json` 로드 → `last_node_ids: list[str]`. 없으면 `[]`.
4. `current_node_ids = set(graph.nodes)`. `new_node_ids = current_node_ids - set(last_node_ids)`. 신규 노드 이름은 `graph.nodes[id]["name"]`. (표시는 20개 캡, 초과 시 `... 외 N개`.)
5. `PROJECTS_DIR/<id>/analysis.json` 있으면 로드 → `summary`, `issues`(상위 N개). 없으면 빈 값.
6. `_reinforcement_suggestions(health, analysis)`:
   - `health["isolated_nodes"]` → "고립 노드 X개 — 관계 연결 또는 문서 보강 필요" + 상위 노드명.
   - `health["wiki_graph_lint"]["missing_source_nodes"]` → "provenance 없는 노드 — 출처 문서 추가 권장".
   - `health["wiki_graph_lint"]["graph_nodes_without_pages"]` → "vault 노트 미생성 노드 — 빌드/노트 생성 권장".
   - `analysis["issues"]` 상위 → 약점 기반 보강 항목.
7. `_render_markdown(date, graph_summary, new_nodes, health, analysis, suggestions)` → 마크다운 문자열.
8. 반환: `{"date", "markdown", "new_node_count", "new_node_names", "isolated_count", "suggestion_count"}`.

### `generate_digest` (부수효과)
1. `result = compose_digest(project_id)`. `None`이면 조용히 반환(스킵) — 수동 API는 404.
2. `VAULT_DIR/<id>/Digests/` mkdir, `<date>.md` 에 `result["markdown"]` 기록(같은 날 재실행=덮어쓰기, 멱등).
3. `digest_state.json` 갱신: `{"last_node_ids": [...현재...], "last_digest_date": date}`.
4. `record_trace(project_id, "digest", trigger=trigger, new_nodes=..., isolated=..., suggestions=...)` — best-effort try/except.
5. `result` 반환.

---

## 6. 마크다운 구조

```markdown
# Digest 2026-06-03

## 요약
- 노드 142개 / 엣지 318개
- 신규 노드 5개
- 고립 노드 3개

## 신규 노드
- [[GraphQL Federation]] (Skill)
- [[ProjectOS]] (Project)
... (20개 초과 시) ... 외 7개

## 경고
### 고립 노드 (3)
- [[Foo]] (Concept)
### source 누락 노드 (2)
- [[Bar]] (Skill)

## 약점 (직전 분석)
이력서의 정량적 성과 서술이 부족합니다.
- 프로젝트 임팩트가 수치로 표현되지 않음
- 기술 스택 나열에 그쳐 역할이 모호함

## 다음 보강 제안
- 고립 노드 3개를 관련 프로젝트/스킬과 연결하세요.
- provenance 없는 노드 2개에 출처 문서를 추가하세요.
- 정량적 성과(숫자)를 이력서에 보강하세요.
```

신규 노드/고립 노드 등 리스트는 20개에서 자르고 `... 외 N개` 를 덧붙인다(`obsidian_writer_agent._render_log_entry` 와 동일 관례).

---

## 7. 대상 프로젝트 선별

워처와 동일 기준 재사용: `PROJECTS_DIR/<id>/` 에 `graph.json` 이 존재(=최소 1회 빌드 완료). `analysis.json`·`digest_state.json` 은 선택(없어도 동작). `chunks.json`/`ontology.json` 은 digest에 불필요하므로 요구하지 않는다.

---

## 8. 설정 (config.py 추가)

```python
DIGEST_ENABLED: bool = False        # opt-in; True여야 lifespan에서 시작
DIGEST_HOUR: int = 7                # 0-23, 일일 digest 실행 시각(로컬)
DIGEST_POLL_SECONDS: int = 300      # 루프가 시계를 확인하는 간격
```

`DIGEST_POLL_SECONDS` 300초면 시각 정밀도로 충분(분 단위 노브 YAGNI). `last_run_date` 는 in-memory(`DigestService` 인스턴스 속성)로 추적 — 재시작 시 그날 이미 vault에 `<date>.md` 가 있어도 멱등 덮어쓰기라 무해.

---

## 9. API 계약

라우터는 `app/api/digest.py` 에 신규 생성하고 `main.py` 에서 `app.include_router(digest.router, prefix="/api/projects", tags=["digest"])` 로 등록한다(기존 라우터 7개 → 8개). 라우터 내부 경로는 아래처럼 `/{project_id}` 로 시작하고, 외부 경로는 `/api/projects/...` 가 된다.

### `POST /{project_id}/digest`  (외부: `/api/projects/{project_id}/digest`)
- 동작: `generate_digest(project_id, trigger="manual")` 동기 실행(저비용, LLM 없음).
- 200: `{"date","markdown","new_node_count","new_node_names","isolated_count","suggestion_count"}`.
- 404: `graph.json` 없음(미빌드 프로젝트).

### `GET /{project_id}/digests`  (외부: `/api/projects/{project_id}/digests`)
- 200: `{"dates": ["2026-06-03", "2026-06-02", ...]}` — `VAULT_DIR/<id>/Digests/*.md` 파일명(stem) 내림차순.
- 디렉터리 없으면 `{"dates": []}`.

### `GET /{project_id}/digests/{date}`  (외부: `/api/projects/{project_id}/digests/{date}`)
- 200: `{"date","markdown"}` — 해당 파일 내용.
- 404: 파일 없음.

`app/services/digest.py` 는 `graph_health`·`trace`·`config` 만 의존하고 API를 임포트하지 않으므로 순환 임포트 위험이 없다(라우터가 서비스를 임포트하는 단방향).

---

## 10. 안전장치 (방향성 문서 §7 대응)

- **opt-in**: `DIGEST_ENABLED` 기본 `False`.
- **단일 인스턴스**: 단일 asyncio 태스크. `lifespan` 종료 시 취소.
- **비용**: digest는 LLM 호출 0회 → 비용 0. budget guard 무관.
- **멱등**: 같은 날 재실행은 `<date>.md` 덮어쓰기. 중복 파일/누적 없음.
- **사용자 편집 보존**: digest는 `Digests/` 전용 폴더에만 기록. 그래프 노트·수동 vault 편집 미접촉.
- **루프 견고성**: 프로젝트 단위 try/except + 사이클 단위 try/except(워처와 동일 삼중 격리: trace best-effort, 프로젝트별, 사이클별).
- **관측성**: digest마다 `record_trace(operation="digest", trigger=...)`.

---

## 11. 에러 처리

| 상황 | 처리 |
|------|------|
| `graph.json` 없음 | `compose_digest` → `None`. 루프는 스킵, 수동 API는 404 |
| `analysis.json` 없음 | 약점 섹션 생략(빈 값), 나머지 정상 |
| `digest_state.json` 없음/손상 | `last_node_ids=[]` 로 간주(최초 실행=baseline) |
| vault 기록 실패(권한 등) | 예외 전파 → 루프 프로젝트별 except가 로깅 후 다음 프로젝트, 수동 API는 500 |
| trace 기록 실패 | best-effort try/except, 무시 |
| 폴링 사이클 예외 | 루프 최상위 try/except 로깅 후 다음 사이클 |

---

## 12. 테스트 전략 (TDD)

`tests/test_services/test_digest.py` 신규. tmp_path + 가짜 `graph.json`/`analysis.json`/`digest_state.json`. **LLM mock 불필요**(digest는 LLM 미사용).

- **신규노드 diff**: `digest_state.json` 의 `last_node_ids` 대비 현재 graph 노드에서 신규만 산출. state 없으면 전부 신규(baseline).
- **health 통합**: 고립 노드가 있는 graph → digest 마크다운에 "고립 노드" 섹션과 노드명 포함.
- **보강 제안 산출**: `_reinforcement_suggestions` 가 health(고립/ source누락)·analysis 이슈에서 기대 문자열 도출.
- **마크다운 섹션**: 렌더 결과에 `# Digest`, `## 요약`, `## 신규 노드`, `## 다음 보강 제안` 포함. 20개 캡 동작.
- **analysis 부재**: `analysis.json` 없어도 예외 없이 약점 섹션만 비고 digest 생성.
- **generate 부수효과**: `Digests/<date>.md` 생성, `digest_state.json` 의 `last_node_ids` 가 현재 노드로 갱신, trace 1줄 기록.
- **멱등**: 같은 날 두 번 `generate_digest` → 파일 1개, 내용 덮어쓰기.
- **should_run**: `last_run_date == today` → False; 날짜 다르고 `hour` 지남 → True; 시각 이전 → False.
- **대상 필터**: `graph.json` 없는 프로젝트는 `compose_digest` → None.
- **opt-in**: `DIGEST_ENABLED=False` 면 `DigestService.start()` 가 태스크 미생성.

`tests/test_api/test_digest_api.py` 신규(FastAPI TestClient):
- `POST /projects/{id}/digest` → 200 + 결과 키 존재, `Digests/<date>.md` 생성.
- 미빌드 프로젝트 POST → 404.
- `GET /projects/{id}/digests` → 날짜 목록 내림차순.
- `GET /projects/{id}/digests/{date}` → 마크다운 반환; 없는 날짜 → 404.

---

## 13. 파일 변경 요약

| 파일 | 변경 |
|------|------|
| `app/services/digest.py` | 신규: compose/generate/should_run/suggestions/render/DigestService |
| `app/api/digest.py` | 신규: POST 생성 + GET 목록/단건 라우터 |
| `app/config.py` | `DIGEST_ENABLED`, `DIGEST_HOUR`, `DIGEST_POLL_SECONDS` 추가 |
| `app/main.py` | `DigestService` import·인스턴스, lifespan에 `_digest.start()`/`await _digest.stop()` 추가, `digest.router` 를 `prefix="/api/projects"` 로 등록 |
| `tests/test_services/test_digest.py` | 신규 |
| `tests/test_api/test_digest_api.py` | 신규 |

---

## 14. 미해결/후속 (이 스펙 범위 밖)

- 로컬 LLM 산문 합성(결정론 템플릿 위에 옵션으로).
- 플러그인 "새 digest" 알림 배지(이번엔 조회 API만 노출).
- 주간/월간 cadence, 프로젝트별 on/off 토글.
- 삭제/변경 노드 추적, digest 간 그래프 delta 상세.
- 외부 맥락(메일/캘린더) 통합 — Phase 3, 가치 확인 후.
