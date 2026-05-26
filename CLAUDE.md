# ProjectOS

로컬 파일(이력서, 프로젝트 문서, 논문) → LLM 분석 → NetworkX 그래프 → Obsidian vault

## Quick Start

```bash
# Backend
cd src/backend && pip install -e ".[dev]" && uvicorn app.main:app --reload

# Frontend
cd src/frontend && npm install && npm run dev
```

## Docs

- Architecture: docs/superpowers/specs/2026-05-24-projectos-design.md
- Agents: docs/agents.md
- API: docs/api.md

## Subdirectory CLAUDE.md

- [Backend](src/backend/CLAUDE.md) — 설치, 테스트, 패키지 구조
- [Agents](src/backend/app/agents/CLAUDE.md) — 에이전트 추가 방법, LLM 패턴
- [API](src/backend/app/api/CLAUDE.md) — 라우터 패턴, SSE, 순환 임포트 방지
- [Frontend](src/frontend/CLAUDE.md) — 빌드, 컴포넌트 패턴, API 클라이언트

## Key Rules

- MiroFish (../MiroFish/) is READ-ONLY reference
- Local graph only — no Zep Cloud
- TDD: write tests first
- Languages: Korean + English
