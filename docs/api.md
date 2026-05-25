# ProjectOS — API Reference

Base URL: `http://localhost:8000/api`

## Projects

| Method | Path | Description |
|--------|------|-------------|
| POST | /projects | 프로젝트 생성 |
| GET | /projects | 프로젝트 목록 |
| GET | /projects/{id} | 프로젝트 상세 |
| DELETE | /projects/{id} | 프로젝트 삭제 |
| POST | /projects/{id}/files | 파일 업로드 (초기) |
| POST | /projects/{id}/files/add | 파일 추가 (증분) |

## Graph & Ontology

| Method | Path | Description |
|--------|------|-------------|
| POST | /projects/{id}/ontology | OntologyAgent 실행 |
| GET | /projects/{id}/ontology | 온톨로지 조회 |
| POST | /projects/{id}/graph | 그래프 구축 |
| POST | /projects/{id}/graph/incremental | 증분 업데이트 |
| GET | /projects/{id}/graph | 그래프 조회 |
| GET | /projects/{id}/graph/stats | 그래프 통계 |
| GET | /projects/{id}/profiles | 커리어 프로필 목록 |

## Vault

| Method | Path | Description |
|--------|------|-------------|
| GET | /projects/{id}/vault | vault 파일 트리 |
| GET | /projects/{id}/vault/download | vault ZIP 다운로드 |

## Chat & Tasks

| Method | Path | Description |
|--------|------|-------------|
| POST | /projects/{id}/chat | QueryAgent 채팅 (SSE) |
| GET | /tasks/{task_id} | 태스크 상태 |
| GET | /tasks/{task_id}/stream | 실시간 진행률 SSE |

## SSE Format

```json
{"status": "running", "progress": 45, "message": "엔티티 추출 중..."}
{"status": "completed", "progress": 100, "message": "완료: 노드 42개"}
```

Chat SSE:
```json
{"token": "답변 내용..."}
{"done": true}
```

See design spec: docs/superpowers/specs/2026-05-24-projectos-design.md
