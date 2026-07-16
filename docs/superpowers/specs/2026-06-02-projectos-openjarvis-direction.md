# ProjectOS × OpenJarvis — 방향성 분석 및 로드맵

**Date**: 2026-06-02
**Status**: Direction (전략 문서, 구현 전 단계)
**참고 대상**: [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) (Stanford Hazy Research & Scaling Intelligence Lab)

---

## 0. 한 줄 요약

ProjectOS는 "무엇을 아는가(기억)"가 강하고 "무엇을 하는가(행동)"가 약하다. OpenJarvis는 정확히 그 반대다. 둘은 경쟁이 아니라 **상보적**이므로, ProjectOS는 자신의 도메인·스택을 유지한 채 OpenJarvis의 **실행 패턴**을 차용하고, 자신을 **스킬/MCP로 노출**해 어떤 에이전트 런타임에든 "커리어 기억"으로 꽂힐 수 있게 한다.

---

## 1. 두 프로젝트 포지셔닝

| 축 | **ProjectOS** | **OpenJarvis** |
|---|---|---|
| 본질 | 개인 지식의 **데이터/기억 레이어** | 개인 에이전트의 **실행/오케스트레이션 런타임** |
| 핵심 산출물 | NetworkX 그래프 + Obsidian vault (큐레이션된 지식) | 8개 빌트인 에이전트 + skills 카탈로그 + 외부 통합 |
| 질문 형태 | "내 커리어/프로젝트에 대해 무엇을 아는가" | "나를 위해 무엇을 자동으로 해주는가" |
| 실행 모델 | 사용자가 트리거하는 파이프라인 (parse→ontology→graph→query) | scheduled / on-demand / continuous 3-모드 상시 동작 |
| LLM | local(OpenAI 호환) + Claude Code CLI (usage/cost 추적 내장) | Ollama 로컬 서빙 중심 |
| 외부 통합 | Obsidian | Gmail/Calendar/Tasks OAuth, TTS 음성 |
| 학습 | 정적 파이프라인 (학습 루프 없음) | trace 기반 learning loop |
| UI | FastAPI + Vue + Obsidian Svelte 플러그인 | Tauri 데스크톱 + Rust 확장 |
| 설계 철학 | 도메인 특화 (커리어/프로젝트) | 범용 프레임워크 + 제약(energy/FLOPs/latency/cost) first-class |

---

## 2. 차이 분석 (상세)

### 2.1 ProjectOS가 이미 강한 것
- **풍부하고 큐레이션된 지식 그래프**: ontology 고정 타입, dedup/canonicalization/refinement, graph health/lint, provenance(`source_chunk_ids`), `log.md`, `_index`.
- **이중 LLM 백엔드**와 **작업별 분리**: chunk 추출=local, dedup/canonical/analysis/query=Claude. 비용/usage 추적이 이미 구현됨.
- **출력 채널**: Obsidian vault(.md + wikilinks + canvas) + Svelte 플러그인(workflow strip, runtime 설정).
- **도메인 에이전트**: Analysis(문서 약점/개선 초안), Persona Simulation(그래프 노드 → 멀티 페르소나 시뮬레이션).

### 2.2 ProjectOS에 없는 것 (OpenJarvis가 채워주는 영역)
1. **상시 동작(scheduled/continuous)** — 모든 작업이 사용자 트리거. "살아있는 비서"의 능동성 부재.
2. **skills 카탈로그 표준** — 에이전트가 내부 함수로만 묶여 있어 외부 런타임이 호출·재조합 불가.
3. **learning loop** — 사용자 정정(dedup 오판, alias 등)이 축적·재사용되지 않음. 매 빌드가 무상태.
4. **제약 인식 라우팅의 일반화** — local/Claude 분리는 있으나 비용 예산·강등 정책으로 체계화되지 않음.
5. **외부 맥락** — 메일/캘린더 등 실시간 외부 신호가 없어 digest/조언이 정적 문서에 갇힘.

### 2.3 핵심 통찰: 상보성
- **ProjectOS = memory substrate (기억)**: 사용자에 대한 정제된 지식.
- **OpenJarvis = action layer (행동)**: 스케줄·모니터·통합·skills·학습.
- 따라서 올바른 질문은 "ProjectOS를 OpenJarvis로 바꿀까?"가 아니라 **"ProjectOS에 OpenJarvis의 행동 패턴을 어떻게 이식할까, 그리고 ProjectOS를 어떻게 호출 가능한 기억으로 노출할까?"** 이다.

---

## 3. 채택 전략 결정: B + C

검토한 3가지 안:

- **A. OpenJarvis를 런타임으로 전면 채택** — 스케줄링·통합·음성을 "공짜"로 얻지만 Ollama/Tauri/Rust 중심 대규모 재작성, Claude Code 백엔드·Obsidian 강점 희석. **기각** (초점 상실, 비용 과다).
- **B. 패턴 차용** — OpenJarvis 개념을 ProjectOS 스택에 흡수(스케줄 digest, continuous monitor, skills 표준, learning loop, 제약 라우팅). **채택.**
- **C. 양방향 브리지** — ProjectOS를 MCP/agentskills 스킬로 노출해 OpenJarvis·Claude·기타 런타임에 꽂을 수 있게. **부분 채택** (잠금 없이 미래 선택지 확보).

**결정: B를 본류로, C를 토대로 병행.** ProjectOS는 명확한 도메인과 강한 스택을 가졌으므로 통째 채택(A)은 부적합하다. 가장 가치 높은 차용은 *실행 모드 + skills 표준 + 학습 루프*이며, 동시에 ProjectOS를 스킬/MCP로 노출하면 미래에 OpenJarvis든 다른 런타임이든 ProjectOS를 "커리어 기억"으로 재사용할 수 있다.

---

## 4. 차용할 OpenJarvis 패턴 → ProjectOS 구체 적용

### 4.1 Scheduled Digest Agent (← `morning_digest`)
- **무엇**: 매일/매주 vault·graph 변화를 합성한 브리핑 생성.
- **내용**: 신규 노드, 고립 노드 경고, AnalysisAgent가 찾은 약점, "다음에 보강할 문서/스킬" 제안.
- **재사용**: 기존 `AnalysisAgent` + `graph_health`/`wiki_graph_lint` 결과를 digest로 합성.
- **출력**: vault에 `Digests/YYYY-MM-DD.md` append + (선택) Obsidian 플러그인 알림 배지.
- **실행**: 백엔드 스케줄러(APScheduler) 또는 외부 cron. local LLM로 저비용 합성.

### 4.2 Continuous File/Vault Watcher (← `monitor_operative`)
- **무엇**: `projects/<id>/files/` 변경 감지 → incremental graph build 자동 트리거.
- **재사용**: incremental 모드와 `DocumentHashStore`가 이미 존재. watch + 디바운스만 추가.
- **안전장치**: delta write/provenance가 사용자 수정 덮어쓰기를 방지(이미 구현). 작은 변경은 해당 chunk만 처리.

### 4.3 Skills 카탈로그 표준 (← agentskills.io)
- **무엇**: 각 에이전트를 입력/출력/비용/제약 메타데이터를 가진 **skill descriptor**로 정형화.
- **효과**: 내부 오케스트레이션을 skill 호출로 일반화 → 동일 카탈로그를 외부 런타임(C)이 재사용 가능.
- **범위**: Phase 1에서는 descriptor(JSON/YAML)만. 런타임 재작성 없음.

### 4.4 Trace 기반 Learning Loop
- **무엇**: ProjectOS는 이미 LLM usage/cost를 추적한다. 이를 **결정 trace**로 확장.
- **저장**: 각 graph build/query의 입력 크기·모델·비용·health 결과·**사용자 정정**(dedup 병합/되돌림, alias 추가, 노드 retype).
- **루프**: 축적된 정정으로 ① fuzzy/semantic threshold 자동 보정, ② alias table 자동 보강, ③ dedup/canonical few-shot 예시 자동 갱신.
- **비목표**: 로컬 모델 fine-tune은 하지 않음. threshold/few-shot/alias 자동 튜닝 수준까지만.

### 4.5 Constraint-aware Model Routing
- **무엇**: local vs Claude 분리를 **작업별 라우팅 정책 테이블**로 일반화.
- **정책 예**: chunk extraction=local(대량/저비용), dedup·canonical·analysis=Claude(저빈도/고품질), digest=local.
- **추가**: 비용 **budget** 설정 + 초과 시 자동 강등(Claude→local). 이미 있는 `llm_backend`/`graph_extraction_backend`를 policy로 통합.

### 4.6 상호운용 노출 (C)
- **MCP 서버**: `query_career_graph`, `get_vault_note`, `run_analysis`, `simulate_persona` 등을 MCP 툴로 노출.
- **agentskills descriptor 동시 제공** (4.3과 공유).
- **효과**: Claude Code / OpenJarvis / 기타 에이전트가 ProjectOS를 "커리어 기억"으로 호출. ProjectOS는 데이터 주권을 유지하면서 임의 런타임의 백엔드가 됨.

---

## 5. 단계별 로드맵

### Phase 1 — 기반 정비 (저위험, 외부 의존 없음)
- 4.3 skills descriptor 정형화 (기존 에이전트 메타데이터화)
- 4.5 constraint-aware routing **policy table**로 `llm_backend`/`graph_extraction_backend` 통합 + budget guard
- 4.4 trace 로깅 확장 (usage에 결정/정정 컨텍스트 추가)
- 산출: 재구성 위주, 신규 외부 의존 0. 이후 단계의 토대.

### Phase 2 — 자동화 레이어 ("살아있는 비서" 첫 체감)
- 4.1 Scheduled Digest Agent (vault `Digests/`, 플러그인 알림)
- 4.2 Continuous File Watcher (auto incremental build)
- 산출: 사용자가 트리거하지 않아도 ProjectOS가 능동적으로 갱신·브리핑.

### Phase 3 — 상호운용 + 학습
- 4.6 MCP/agentskills 노출
- 4.4 trace 기반 자동 튜닝(threshold/alias/few-shot) 활성화
- (선택) OAuth 통합(메일/캘린더)으로 digest에 외부 맥락 추가 — 가치 확인 후 결정.

---

## 6. Non-goals (명시적 비채택)
- OpenJarvis 코드베이스 fork/전면 채택 안 함 (Ollama/Tauri/Rust 재작성 회피).
- 음성/TTS 후순위 — 텍스트·vault 중심 도메인에서 가치 낮음.
- 로컬 모델 fine-tune 안 함 — 학습은 threshold/few-shot/alias 튜닝까지.
- 멀티유저/클라우드 동기화 안 함 (기존 non-goal 유지).

---

## 7. 리스크 및 완화
- **백그라운드 안정성**: 스케줄러/워처 중복 실행·좀비 프로세스 → 단일 인스턴스 락 + 디바운스.
- **자동 갱신이 사용자 수정 덮어쓰기**: delta write/provenance로 이미 완화. 워처는 그래프만 갱신하고 vault 수동 편집 보존.
- **비용 폭주**: 자동 트리거가 Claude 호출 폭증 유발 → budget guard + 자동 강등(4.5).
- **추상화 과설계**: skills/MCP를 너무 일찍 일반화 → Phase 1은 최소 descriptor만, 실제 외부 호출 수요 확인 후 확장.

---

## 8. 권장 첫 단계
Phase 1의 **constraint-aware routing policy table + budget guard**가 가장 위험이 낮고 즉시 가치를 준다(현재 분산된 백엔드 설정을 한 곳으로 모으고 비용 통제). 이후 trace 로깅 확장 → skills descriptor 순으로 진행. Phase 2의 Digest Agent가 "능동성"의 첫 가시적 성과가 된다.
