# merge_candidates 리뷰 UI 설계

**작성일:** 2026-06-19
**상태:** 승인됨 (구현 대기)

## 목표

`graph.graph["merge_candidates"]`에 저장된 노드 병합 후보를 사용자가 검토하는 프론트엔드 UI를 추가한다. 사용자는 후보를 **승인**(실제 그래프 병합 적용)하거나 **거부**(denylist에 영속화하여 재빌드 시 다시 제안되지 않도록)할 수 있다.

## 배경

- `collect_merge_candidates(graph, threshold=None)`는 임베딩 유사도 기반으로 중복 가능성이 있는 노드 쌍을 수집해 `graph.graph["merge_candidates"]`에 저장한다. 의도적으로 자동 병합하지 않는다.
- 후보 dict 형태: `{type, keep_id, keep_name, candidate_id, candidate_name, confidence, aliases[]}`, confidence 내림차순 정렬.
- 노드 id는 안정적인 `Type:Name` 형식(예: `Skill:SOT fine-tuning`) → `(keep_id, candidate_id)` 쌍은 그래프 재빌드 사이에 안정적이다.
- 현재 후보는 그래프 JSON에 저장되지만 전용 프론트엔드 검토 UI가 없다 (handoff 갭, item #3).

## 아키텍처

### 데이터 흐름

```
build 시: collect_merge_candidates(graph, denylist=load_denylist(id))
          → graph.graph["merge_candidates"]
          → projects/{id}/graph.json 에 저장

조회 시:  GET /{id}/graph → data["graph"]["merge_candidates"]
          → 프론트 extractMergeCandidates(graphData)
          → MergeReviewPanel 카드 렌더

승인 시:  POST /{id}/graph/merge-candidates/apply {keep_id, candidate_id}
          → graph.json 로드 → 노드 존재 검증 → _merge_node → 재수집(denylist) → 저장
          → {merged: true, merge_candidates: [...]} 반환
          → 프론트 패널 갱신 + 'merged' emit → 그래프 refetch

거부 시:  POST /{id}/graph/merge-candidates/reject {keep_id, candidate_id}
          → add_denied_pair → 저장된 후보에서 해당 쌍 제거 → 저장
          → {rejected: true, merge_candidates: [...]} 반환
          → 프론트 패널 갱신
```

## 컴포넌트

### 백엔드

#### `app/utils/merge_denylist.py` (신규)

denylist를 별도 파일 `projects/{id}/merge_denylist.json`에 저장 (Approach A).

- 파일 형식: `[[id_a, id_b], ...]` — 각 쌍은 정렬된 2-원소 리스트.
- `load_denylist(project_id) -> set[frozenset]`
  - 파일이 없으면 빈 set 반환.
  - 각 `[a, b]`를 `frozenset({a, b})`로 변환.
- `add_denied_pair(project_id, id_a, id_b) -> None`
  - 기존 denylist 로드 → `frozenset({id_a, id_b})` 추가 → 정렬된 리스트 형태로 직렬화 저장.
  - 이미 존재하면 중복 추가하지 않음(set 특성).

#### `app/utils/merge_review.py` (수정)

`collect_merge_candidates(graph, threshold=None, denylist=None)`:
- `denylist`가 주어지면 후보 루프에서 `frozenset({keep_id, cand_id}) in denylist`인 쌍을 건너뛴다.
- `denylist=None`이면 기존 동작과 동일.

#### `app/api/graph.py` (수정)

빌드 경로 (현재 line 499-503):
```python
merge_candidates = collect_merge_candidates(graph, denylist=load_denylist(project_id))
graph.graph["merge_candidates"] = merge_candidates
```

신규 엔드포인트 2개:

`POST /{id}/graph/merge-candidates/apply`
- body: `{keep_id: str, candidate_id: str}`
- graph.json 로드 → DiGraph 복원.
- `keep_id`/`candidate_id` 중 하나라도 노드에 없으면 **409 Conflict** (이미 병합됐거나 stale).
- `_merge_node(graph, keep_id, candidate_id)` 호출.
- `collect_merge_candidates(graph, denylist=load_denylist(id))`로 재수집 → `graph.graph["merge_candidates"]` 갱신.
- graph.json 저장.
- 반환: `{merged: true, merge_candidates: [...]}`

`POST /{id}/graph/merge-candidates/reject`
- body: `{keep_id: str, candidate_id: str}`
- `add_denied_pair(id, keep_id, candidate_id)`.
- graph.json 로드 → 저장된 `merge_candidates`에서 해당 쌍 제거 → 저장.
- 반환: `{rejected: true, merge_candidates: [...]}`

### 프론트엔드

#### `src/lib/mergeCandidates.js` (신규, 순수 함수)

`extractMergeCandidates(graphData) -> []`:
- `graphData?.graph?.merge_candidates`를 안전하게 읽음, 없으면 `[]`.
- confidence 내림차순 정렬 보장.

#### `src/api/client.js` (수정)

`projectsApi`에 추가:
```js
applyMergeCandidate: (id, data) => api.post(`/projects/${id}/graph/merge-candidates/apply`, data),
rejectMergeCandidate: (id, data) => api.post(`/projects/${id}/graph/merge-candidates/reject`, data),
```

#### `src/components/MergeReviewPanel.vue` (신규)

- props: `projectId`, `graphData`.
- `extractMergeCandidates(graphData)`로 로컬 후보 리스트 초기화.
- 각 카드: type 배지, `keep_name ← candidate_name`, confidence %, aliases chips, [승인]/[거부] 버튼.
- 승인: `applyMergeCandidate` 호출 → 응답의 `merge_candidates`로 로컬 리스트 교체 → `'merged'` emit.
- 거부: `rejectMergeCandidate` 호출 → 응답의 `merge_candidates`로 로컬 리스트 교체.
- 진행 중 버튼 비활성화(중복 클릭 방지).
- 빈 상태: "검토할 병합 후보가 없습니다".

#### `src/views/ProjectDetail.vue` (수정)

- `el-tabs`에 `<el-tab-pane label="병합 검토" name="merge">` 추가.
- 내부에 `<MergeReviewPanel :project-id="..." :graph-data="..." @merged="refetchGraph" />`.
- 탭 라벨에 후보 개수 배지.

## 에러 처리

- apply 시 노드 부재 → 409, 프론트는 메시지 표시 후 그래프 refetch로 동기화.
- denylist 파일 손상/부재 → 빈 set으로 graceful 처리.
- API 실패 → 버튼 재활성화, 에러 toast.

## 테스트

### 백엔드
- `tests/test_utils/test_merge_review.py` (확장): denylist 필터링 — denied 쌍이 후보에서 제외되는지, `denylist=None`이면 기존 동작 유지.
- `tests/test_utils/test_merge_denylist.py` (신규): load/add 라운드트립, 파일 부재 시 빈 set, 중복 add 무시.
- `tests/test_api/test_graph_merge_candidates.py` (신규): apply 정상 병합 + 후보 갱신, apply stale 노드 → 409, reject → denylist 기록 + 후보 제거.

### 프론트엔드
- `src/lib/mergeCandidates.test.js` (신규): 후보 추출, 부재 시 `[]`, confidence 정렬.

## 범위 밖 (YAGNI)

- 일괄 승인/거부.
- denylist 항목 해제(undo) UI.
- 병합 미리보기/diff 시각화.
