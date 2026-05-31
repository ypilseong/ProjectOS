# ProjectOS Obsidian 플러그인 (vault 공유 방식 1번) 설계

- 작성일: 2026-05-30
- 상태: 승인됨 (구현 계획 진행)

## 배경 / 문제

ProjectOS 백엔드는 dgx02 원격 서버에서 실행되고, `ObsidianWriterAgent`는 백엔드 로컬
디스크의 `VAULT_DIR`에 노트를 직접 기록한다. 그러나 Obsidian 앱은 사용자 로컬 머신에서
실행되므로 "백엔드가 vault에 쓰면 → 로컬 Obsidian Graph View가 자동 갱신"이 성립하지
않는다(원격 디스크와 로컬 vault가 분리).

선택지 비교 후 **방식 1번**을 채택한다: 백엔드가 결과를 페이로드로 반환하고, **Obsidian
플러그인이 그 페이로드를 로컬 vault에 직접 기록**한다. 그러면 Graph View가 자동 갱신된다.

## 목표

- Obsidian 플러그인이 백엔드와 통신하여 로컬 vault에 노트/캔버스/인덱스를 기록한다.
- 플러그인 v1 기능 범위: **동기화 + 수집 + 쿼리** (다이어그램 1의 사이드 패널 의도 반영).
- 기존 Vue 웹 프론트엔드는 손대지 않고 **병행 유지**한다.
- 플러그인 ↔ 백엔드 인증은 두지 않는다(개인/신뢰 네트워크 가정, Base URL만 설정).

## 비목표 (v1 범위 밖)

- 로컬 vault의 사용자 수동 편집을 보존하는 머지(플러그인은 생성 폴더만 덮어씀).
- 자동 스케줄/폴링 수집, 외부 커넥터(Drive/Mail/Calendar OAuth).
- 양방향 동기화(로컬 vault 편집 → 그래프 반영).
- 플러그인 인증/토큰.

## 핵심 제약과 화해

웹앱과 다른 기능이 **디스크에 쓰인 서버측 vault에 실제로 의존**한다:

- `VaultTree.vue` → `GET /api/projects/{id}/vault`(트리), `/vault/file`, `/vault/download`
  (`api/projects.py:96-125`)
- `query_agent`(채팅 RAG)는 `vault_path`로 노트를 읽어 컨텍스트로 사용 (`chat.py:39`)
- `graph_health`는 `vault_path`로 깨진 링크 검사 (`graph.py:188`)

따라서 디스크 쓰기를 완전히 제거하면 "웹앱 그대로 유지"와 충돌한다. 화해책으로
`ObsidianWriterAgent`를 **2계층(렌더러 + 디스크 라이터)** 으로 리팩터한다. 렌더러는
페이로드를 반환하고, 디스크 라이터는 그 페이로드를 서버측 `VAULT_DIR`에 저장한다.
파이프라인은 계속 디스크 라이터를 호출하므로 웹앱·RAG·헬스체크·다운로드는 무손상이며,
플러그인은 신규 export 엔드포인트로 같은 페이로드를 받아 로컬에 기록한다.

## 아키텍처 개요

- **신규 Obsidian 플러그인**: `src/obsidian-plugin/` (TypeScript). Obsidian 앱 내부에서
  실행되고 로컬 vault에 직접 기록.
- **백엔드(dgx02 FastAPI)**: `obsidian_writer` 2계층 리팩터 + export 엔드포인트 추가.
  나머지 에이전트 파이프라인·웹앱은 변경 없음.
- **연결**: 플러그인 설정의 Base URL로 HTTP/SSE 호출(인증 없음).
- **핵심 흐름**: 백엔드 그래프 빌드 → 플러그인이 export로 페이로드 수신 → Obsidian
  Vault API로 로컬 기록 → Graph View 자동 갱신.

## 백엔드 변경

### (a) `VaultPayload` 모델 (`app/models/`)

```
VaultPayload {
  notes:     [{ folder: str, filename: str, content: str }]  # 엔티티 노트
  canvas:    { filename: "_index.canvas", content: str }
  index:     { filename: "_index.md", content: str }
  log_entry: str   # 이번 빌드의 로그 라인 (서버측에서 log.md에 append)
}
```

### (b) `ObsidianWriterAgent` 2계층 리팩터

- `build_payload(graph, profiles, project_id) -> VaultPayload`
  - 순수 함수, 디스크 접근 없음. 기존 `_render_note` / `_write_canvas` / `_write_index`
    렌더링 로직을 문자열 생성으로 전환하여 페이로드를 구성.
- `write_payload(payload, vault_path, delta)`
  - 페이로드를 서버측 `VAULT_DIR`에 저장. 기존 `delta` 머지(`_merge_note`),
    `_clear_generated_notes`, `_setup_vault`(.obsidian/graph.json), `_write_log` 동작 유지.
- 기존 `run(...)` = `write_payload(build_payload(...), vault_path, delta)` 얇은 래퍼.
  - → 에이전트 파이프라인·웹앱·RAG·헬스체크·다운로드 **무손상**.

### (c) export 엔드포인트

`GET /api/projects/{id}/vault/export`

- `build_payload`로 만든 `VaultPayload`를 JSON으로 반환.
- 그래프가 없으면 404(기존 패턴: "graph not found / build first").
- **전체 스냅샷**(생성 폴더 기준) 반환. 로컬 사용자 편집 보존 머지는 v1 범위 밖이며,
  플러그인은 생성 폴더만 덮어쓴다.

## 플러그인 구성 (`src/obsidian-plugin/`)

표준 Obsidian 스캐폴드: `manifest.json`, `package.json`, `tsconfig.json`,
`esbuild.config.mjs`, `main.ts`.

### 설정 탭 (PluginSettingTab)

- Base URL (백엔드 주소)
- 대상 project id (백엔드 프로젝트 목록에서 선택)
- 기록 대상 폴더 (기본: vault 루트)

### 사이드 패널 (ItemView) — 3개 섹션

- **수집**: 파일 선택 → `POST /api/projects/{id}/files` 업로드 →
  `POST /api/projects/{id}/graph` 빌드 트리거. 진행률은 `/api/tasks/{id}/stream`(SSE).
- **동기화**: "백엔드에서 가져오기" 버튼 → `GET /vault/export` 호출 →
  `this.app.vault.create / modify`로 노트·캔버스·인덱스 기록 → Graph View 자동 갱신.
- **쿼리**: 질문 입력 → `POST /api/projects/{id}/chat`(SSE) 스트리밍 응답 표시.

### 안전장치

- 생성 폴더(Career / Projects / Skills / Organizations / Publications / Roles /
  Achievements / Events / Institutions / Misc + `_index.md` / `_index.canvas` / `log.md`)
  만 건드리고, 사용자의 다른 노트는 절대 변경하지 않는다.
- 쓰기는 멱등(존재하면 modify, 없으면 create).

## 데이터 흐름

1. **수집**: 플러그인 → 파일 업로드 → 빌드 트리거 → 태스크 SSE로 진행률.
2. **동기화**: 빌드 완료 → export → 페이로드 수신 → Vault API로 로컬 기록 → Graph View 갱신.
3. **쿼리**: 질문 → chat SSE → 패널에 스트리밍 답변.

## 에러 처리

- 백엔드 불통 → 패널에 에러 표시 + 재시도.
- export 시 그래프 없음 → 404 안내 메시지.
- vault 쓰기 실패 → 해당 파일 스킵 + 알림(Notice), 생성 폴더 한정.

## 테스트 전략 (TDD)

- **백엔드**
  - `build_payload` 순수 함수 단위 테스트(엔티티→노트, 캔버스, 인덱스 산출 검증).
  - `write_payload`가 리팩터 전과 동일한 파일을 산출하는지 골든 테스트.
  - export 엔드포인트 계약 테스트(payload 구조, 그래프 없을 때 404).
  - 기존 `test_obsidian_writer_agent.py`는 래퍼(`run`) 경유로 그대로 통과해야 함.
- **플러그인**
  - 순수 로직(페이로드 → 파일 연산 매핑)을 mock vault 어댑터로 단위 테스트.
  - UI는 Obsidian에서 수동 검증(헤드리스 브라우저 불가 환경).

## 영향 받는 파일 (예상)

- 변경: `app/agents/obsidian_writer_agent.py`, `app/api/projects.py`(export 엔드포인트),
  `app/models/`(VaultPayload).
- 신규: `src/obsidian-plugin/*`, 백엔드 테스트 추가.
- 무변경: Vue 웹 프론트엔드, 나머지 에이전트, query/health/download 경로.
