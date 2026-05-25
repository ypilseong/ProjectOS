# ProjectOS

로컬 파일(이력서, 프로젝트 문서, 논문) → LLM 분석 → NetworkX 그래프 → Obsidian vault

## Quick Start

```bash
# Backend
cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

## Docs

- Architecture: docs/superpowers/specs/2026-05-24-projectos-design.md
- Agents: docs/agents.md
- API: docs/api.md

## Key Rules

- MiroFish (../MiroFish/) is READ-ONLY reference
- Local graph only — no Zep Cloud
- TDD: write tests first
- Languages: Korean + English
