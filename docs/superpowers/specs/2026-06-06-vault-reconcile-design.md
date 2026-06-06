# Vault Manual-Edit → Graph Reconcile 설계

> 개선 항목 #2. Obsidian vault에서 사람이 직접 수정한 내용을 NetworkX 그래프로 역방향 반영한다.

**목표:** vault `.md` 페이지의 수동 편집(설명/연결/노드 추가·삭제)을 감지해 `graph_patch` 형식의 패치로 변환하고, dry-run 프리뷰 후 그래프에 적용한다.

**범위 결정 (사용자 확정):**
- 필드 범위: 설명(description) + 연결(connections) + 노드 추가/삭제. rename/retype은 제외.
- 트리거: 온디맨드 (MCP 도구 + API 엔드포인트). 파일 와처 연동은 제외.
- 안전성: dry-run 프리뷰 후 별도 apply 호출로 확정.

**기술 스택:** Python, NetworkX, 기존 `app/utils/graph_patch.py` 적용 계층 재사용.

---

## 배경

ProjectOS 파이프라인은 단방향이다: 소스 파일 → LLM → NetworkX 그래프(`graph.json`, source of truth) → Obsidian vault(렌더 결과). `ObsidianWriterAgent`가 그래프를 vault로 렌더링하지만, 사용자가 vault에서 직접 고친 내용을 다시 그래프로 가져오는 경로가 없다. 전체 재빌드(`delta=False`)는 엔티티 폴더를 `rmtree`하므로 수동 편집이 사라진다.

이미 존재하는 자산:
- `app/utils/graph_patch.py` — `apply_project_graph_patch(project_id, patch)` 구조적 패치 적용 계층. MCP 도구 `projectos_apply_graph_patch`로 노출됨.
- `app/agents/obsidian_writer_agent.py` — 그래프→vault 렌더러. 페이지 구조(frontmatter, `## Overview`, `## Connections`)가 결정적이라 역파싱 대상이 명확.

빠진 조각: vault를 **읽어서** 그래프와 **비교(diff)**하는 역방향 경로.

## 접근 방식

**선택: 결정적 구조 섹션 파서 + 집합 차분(set-diff).** vault 페이지는 기계 생성물이라 구조가 알려져 있다. 같은 구조를 역파싱해 그래프와 비교하면 LLM 없이 결정적·저비용으로 패치를 만들 수 있다. 기존 패치/적용 계층에 그대로 연결된다.

탈락:
- **LLM 추출** — 비용/비결정성, 구조화 렌더링이 피하려 했던 환각 위험 재도입.
- **vault 전체를 소스로 재유도** — provenance(sources, confidence, 빌드 메타) 손실, 페이지로 렌더된 적 없는 그래프 상태를 덮어씀.

## 컴포넌트

신규 모듈 `app/services/vault_reconcile.py`.

### 1. Vault 페이지 파서

```
parse_vault_page(path: Path) -> dict | None
```

반환: `{"type": str, "name": str, "description": str, "connections": list[dict]}` 또는 파싱 불가 시 `None`.

- frontmatter에서 `type`, `name` 추출. 둘 중 하나라도 없으면 `None`.
- `## Overview` 섹션 본문 → `description`. `"(설명 없음)"`는 빈 문자열로 정규화.
- `## Connections` 섹션의 라인 파싱:
  - `- {relation}: [[{target}]]` → successor 방향 연결 `{relation, direction: "out", other: target}`
  - `- ← {relation}: [[{source}]]` → predecessor 방향 연결 `{relation, direction: "in", other: source}`
- `## Sources`, `## Details`, 프로필 섹션 등은 무시.

### 2. Differ

```
diff_vault_against_graph(project_id: str) -> dict
```

vault 디렉터리의 모든 엔티티 페이지를 파싱하고 그래프와 비교해 `graph_patch` 형식 패치를 만든다:

- **description 변경** → `nodes_update` 항목 `{type, name, set: {description}}`
- **vault에만 있는 연결** → `edges_add` 항목 `{source_name, target_name, relation, confidence}`
- **page 없는 그래프 노드** → `nodes_delete`
- **그래프에 없는 `.md` 페이지** → `nodes_add` 항목 `{type, name, description}`
- **edge 삭제** → **union 의미론**: source 페이지의 successor 목록과 target 페이지의 predecessor 목록 **양쪽 모두**에 없을 때만 `edges_delete` 방출. 한쪽 페이지만 편집된 상태에서의 거짓 삭제 방지.

연결의 양방향 표현(out/in)을 정규화해 (source, target, relation) 유향 간선 집합으로 환원한 뒤 그래프 간선 집합과 비교한다.

### 3. Orchestrator

```
reconcile_vault(project_id: str, apply: bool = False) -> dict
```

- `apply=False` (dry-run): `{patch, summary}` 반환, 그래프 변경 없음. `summary`는 각 변경 유형별 카운트.
- `apply=True`: `apply_project_graph_patch(project_id, patch)` 호출 후 적용 결과 반환.

### 4. 트리거

- **API**: `POST /projects/{project_id}/reconcile?apply={bool}` — 기본 dry-run. `app/api/projects.py` 또는 graph 라우터에 추가.
- **MCP 도구**: `projectos_reconcile_vault(project_id, apply=False)` — `app/mcp_tools.py`에 등록. `projectos_apply_graph_patch` 패턴을 미러링.

## 데이터 흐름

```
vault/*/*.md ──parse_vault_page──> [{type,name,description,connections}]
                                          │
graph.json ──load──> NetworkX ──────────┐ │
                                        ▼ ▼
                              diff_vault_against_graph
                                        │
                                        ▼
                                graph_patch 형식 patch
                              ┌─────────┴─────────┐
                       apply=False            apply=True
                              │                    │
                       {patch, summary}   apply_project_graph_patch
```

## 에러 처리

- 파싱 불가 페이지(frontmatter 누락 등)는 건너뛰고 경고 로그. 전체 reconcile은 실패시키지 않음.
- `graph.json` 부재 → 명확한 에러 반환 (reconcile할 그래프 없음).
- vault 디렉터리 부재 → 빈 패치 + 경고.
- 적용 실패는 `apply_project_graph_patch`의 검증/에러 처리에 위임 (is_valid_entity, normalize_entity_type 등).

## 테스트 (TDD)

`tests/test_services/test_vault_reconcile.py`:

1. `parse_vault_page` — frontmatter type/name 추출, Overview→description, "(설명 없음)"→빈 문자열.
2. `parse_vault_page` — Connections successor/predecessor 양방향 라인 파싱.
3. `parse_vault_page` — frontmatter 누락 시 None.
4. differ — description 변경 시 nodes_update 생성.
5. differ — vault에만 있는 연결 시 edges_add.
6. differ — union 의미론: 한쪽 페이지에서만 사라진 간선은 삭제 안 함.
7. differ — 양쪽에서 사라진 간선은 edges_delete.
8. differ — page 없는 그래프 노드 → nodes_delete.
9. differ — 그래프에 없는 새 .md → nodes_add.
10. `reconcile_vault(apply=False)` — 그래프 불변, patch/summary 반환.
11. `reconcile_vault(apply=True)` — apply_project_graph_patch 호출.
12. API 엔드포인트 — dry-run 기본, apply 쿼리 파라미터.
13. MCP 도구 등록 및 호출.

## 비범위 (YAGNI)

- rename/retype 감지 (편집 추적 없이는 add+delete와 구분 불가).
- 파일 와처 자동 트리거.
- 충돌 해결 UI (dry-run 프리뷰로 충분).
- 프로필 섹션/Sources의 역파싱.
