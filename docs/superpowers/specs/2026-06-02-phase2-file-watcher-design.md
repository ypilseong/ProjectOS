# Phase 2a — Continuous File Watcher 설계

**Date**: 2026-06-02
**Status**: Design (구현 전, 승인 대기)
**상위 문서**: [ProjectOS × OpenJarvis 방향성](2026-06-02-projectos-openjarvis-direction.md) §4.2
**선행**: Phase 1 (routing/budget guard, trace sink) 완료

---

## 0. 한 줄 요약

`projects/<id>/files/`의 신규·수정 파일을 주기적 해시 폴링으로 감지해 **재파싱 → incremental 그래프 빌드**를 자동 트리거한다. 사용자가 트리거하지 않아도 그래프가 항상 최신으로 유지되는 "능동성"의 토대.

---

## 1. 목표와 비목표

### 목표
- 백그라운드에서 `files/` 변경을 감지해 그래프를 자동 갱신.
- 신규 파일과 기존 파일의 in-place 수정 모두 반영.
- 기존 인프라(`DocumentHashStore`, incremental 빌드, ParserAgent, Phase 1 trace/budget) 최대 재사용.
- 안전: opt-in, 비용 상한, 사용자 수동 vault 편집 보존, 빌드 중복 방지.

### 비목표
- **삭제 파일 처리 안 함** — 그래프 노드/청크 제거·provenance 정리는 복잡도가 커서 별도 단계로 미룸.
- **Scheduled Digest Agent 안 함** — Phase 2b 별도 스펙/플랜.
- **실시간 이벤트(watchdog/inotify) 안 함** — Syncthing 동기 디렉터리에서 이벤트 누락 위험. 해시 폴링 채택.
- **ontology 재생성 안 함** — 기존 ontology 재사용(incremental 빌드와 동일).

---

## 2. 왜 "incremental 빌드 단독"으로는 부족한가 (설계 근거)

기존 incremental 빌드(`app/api/graph.py:_run_graph(incremental=True)`)는:
1. `chunks.json`을 읽고, 청크의 `source_file`에서 파일 목록을 도출.
2. `DocumentHashStore`로 `files/`의 raw 파일 해시를 비교해 변경 파일 집합 산출.
3. **변경된 파일의 청크만** 필터링해 그래프 재추출.

따라서:
- **신규 raw 파일**: `chunks.json`에 청크가 없으므로 `source_files`에 포함되지 않음 → 무시됨.
- **수정 raw 파일**: `chunks.json`의 청크가 옛 내용 그대로 → 스테일 청크로 재추출 → 그래프가 새 내용 미반영.

결론: Watcher는 incremental 빌드를 호출하기 **전에** 변경 파일을 재파싱해 `chunks.json`을 갱신해야 한다.

---

## 3. 아키텍처

FastAPI `lifespan`에서 시작되는 **단일 asyncio 백그라운드 태스크** `WatcherService`. 단일 태스크이므로 본질적으로 single-instance(좀비/중복 없음). `WATCHER_ENABLED=False`면 시작하지 않음.

```
main.py (lifespan)
  └─ WatcherService.start()  →  asyncio.create_task(loop)
        loop: 매 WATCHER_POLL_SECONDS
          └─ for each 빌드완료 프로젝트:
               detect_changes()  →  stable changed/new files
               if changes and not build_running:
                   run_auto_update(project_id, files)
                       ├─ reparse_and_replace_chunks(files)
                       └─ _run_graph(task_id, project_id, incremental=True)
                       └─ record_trace(..., trigger="watcher")
```

---

## 4. 컴포넌트 (각 단일 책임)

| 유닛 | 파일 | 책임 | 의존 |
|------|------|------|------|
| `WatcherService` | `app/services/watcher.py` (신규) | 폴링 루프, 프로젝트 순회, 디바운스 상태, 빌드 중복 방지, 시작/정지 | config, task_manager, DocumentHashStore |
| 변경 감지 `detect_changes` | 위 파일 내 | `files/` 열거 → 해시 비교 → 신규+수정 파일 집합. 안정성 디바운스 적용 | DocumentHashStore |
| 청크 교체 `reparse_and_replace_chunks` | `app/services/watcher.py` 또는 `app/utils/chunk_store.py` | 변경 파일 재파싱 → `chunks.json`에서 해당 `source_file` 기존 청크 제거 후 새 청크로 교체 | ParserAgent |
| 자동 빌드 트리거 | 위 파일 내 | task 생성 후 `_run_graph(incremental=True)` 호출, trace 기록 | api/graph._run_graph, trace |

**경계**: `WatcherService`는 변경 감지·스케줄링만. 실제 파싱/빌드는 기존 함수에 위임. 청크 교체는 독립 함수로 단위 테스트 가능.

---

## 5. 데이터 흐름 (한 폴링 사이클)

1. 대상 프로젝트 선별: `PROJECTS_DIR/<id>/`에 `chunks.json` + `ontology.json` + `graph.json`이 모두 존재(=최소 1회 빌드 완료)하는 프로젝트만.
2. 각 프로젝트의 `files/` 디렉터리 파일 목록 열거(지원 확장자: PDF/DOCX/TXT 등 ParserAgent 지원 형식).
3. 각 파일의 현재 해시(md5) 계산.
   - `DocumentHashStore`에 저장된 해시와 다르거나(수정), 저장된 해시가 없으면(신규) → **변경 후보**.
4. **안정성 디바운스**: WatcherService는 직전 폴링에서 관측한 파일별 해시를 in-memory로 보관. 변경 후보 중 **직전 폴링과 해시가 동일(=안정)** 한 파일만 실제 처리 대상. (Syncthing 동기 진행 중·편집 중 파일은 다음 사이클로 이연.)
5. 처리 대상이 있고, 해당 프로젝트의 빌드 task가 **실행 중이 아니면**(task_manager 조회) → 자동 파이프라인 실행.
6. 자동 파이프라인:
   a. `reparse_and_replace_chunks(project_id, changed_files)` — 변경 파일만 재파싱, `chunks.json`에서 그 `source_file`의 기존 청크 제거 후 새 청크 추가.
   b. `task = task_manager.create(project_id, "graph_watcher")`.
   c. `await _run_graph(task.task_id, project_id, incremental=True)` — 내부에서 DocumentHashStore가 변경 파일을 감지해 해당 청크만 재추출, 그래프 머지, ObsidianWriter delta write.
   d. 빌드 trace에 `trigger="watcher"` 기록(Phase 1 trace sink는 `_run_graph` 내부에서 이미 기록; trigger 필드 추가).

---

## 6. 설정 (config.py 추가)

```python
WATCHER_ENABLED: bool = False           # opt-in; True여야 lifespan에서 시작
WATCHER_POLL_SECONDS: int = 15          # 폴링 간격
```

디바운스는 별도 설정 없이 "직전 폴링 대비 안정" 규칙으로 충분(추가 노브 YAGNI). 필요 시 후속 추가.

---

## 7. 안전장치 (방향성 문서 §7 리스크 대응)

- **opt-in**: `WATCHER_ENABLED` 기본 `False`. 명시적으로 켜야 동작.
- **백그라운드 안정성**: 단일 asyncio 태스크 = single-instance. `lifespan` 종료 시 태스크 취소.
- **루프 견고성**: 한 프로젝트 처리 중 예외가 전체 루프를 죽이지 않도록 프로젝트 단위 try/except, 로깅 후 다음 프로젝트 계속.
- **비용 폭주**: Phase 1 budget guard가 Claude 누적 비용 상한 → 초과 시 local 강등. 추출이 local이면 비용 거의 0.
- **빌드 중복**: 프로젝트별 in-flight 빌드 1개만(task_manager 확인). 진행 중이면 스킵.
- **사용자 수동 편집 보존**: incremental + delta write/provenance(기존 구현). Watcher는 그래프·자동 생성 노트만 갱신, 수동 vault 편집 미덮어씀.
- **추적/관측성**: 자동 빌드마다 trace 기록(`trigger="watcher"`). task는 기존 SSE로 노출되어 플러그인/프런트에서 진행 확인 가능.

---

## 8. 에러 처리

| 상황 | 처리 |
|------|------|
| `files/` 디렉터리 없음 | 해당 프로젝트 스킵 |
| 파싱 실패(손상 파일) | 해당 파일 스킵·로깅, 나머지 진행, 다음 폴링에서 해시 동일하면 재시도 안 함 |
| 빌드 중 예외 | `_run_graph`의 기존 except가 task FAILED 처리; 루프는 계속 |
| trace 기록 실패 | best-effort(Phase 1에서 graph build trace는 이미 try/except로 감쌈) |
| 폴링 사이클 예외 | 루프 최상위 try/except로 로깅 후 다음 사이클 |

---

## 9. 테스트 전략 (TDD)

`tests/test_services/test_watcher.py` 신규.

- **변경 감지**: 신규/수정/무변경 파일을 올바르게 분류(tmp_path + 가짜 hash store).
- **안정성 디바운스**: 직전 폴링과 해시가 다른(불안정) 파일은 트리거 대상에서 제외.
- **빌드 중복 방지**: task_manager에 RUNNING 빌드가 있으면 트리거 안 함.
- **대상 프로젝트 필터**: `graph.json` 없는(미빌드) 프로젝트는 스킵.
- **청크 교체**: 수정 파일 재파싱 시 `chunks.json`에 동일 `source_file` 청크가 중복되지 않고 새 내용으로 교체.
- **통합(파이프라인 mock)**: 안정적 변경 → `reparse_and_replace_chunks`와 `_run_graph(incremental=True)`가 각 1회 호출됨(ParserAgent/LLM은 mock).
- **opt-in**: `WATCHER_ENABLED=False`면 `start()`가 태스크를 만들지 않음.

LLM 호출·실제 빌드는 mock. 파일시스템은 tmp_path.

---

## 10. 미해결/후속 (이 스펙 범위 밖)

- 삭제 파일 → 그래프 노드/청크 정리 (별도 단계).
- 플러그인 "새 갱신" 알림 배지 (Digest와 함께 Phase 2b에서 다룰지 결정).
- 프로젝트별 watcher on/off 토글(현재는 전역). 수요 확인 후.
- ontology 자동 재생성(현재 재사용).
