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
- 작업 완료 후 반드시 `docs/claude-code-handoff.md`를 업데이트할 것 — 변경 내역, 검증 결과, 다음 작업 후보 포함

## 서버 환경 (dgx02)

포트 8000과 5173이 다른 서비스에 점유됨:
- Backend: `uvicorn app.main:app --port 8001`
- Frontend: `npm run dev -- --port 5174`
- `vite.config.js` proxy를 8001로 변경 후 실행 (커밋하지 말 것)

Git push: `git -c credential.helper='' push https://<TOKEN>@github.com/ypilseong/ProjectOS.git main`

브라우저 스크린샷: `libatk` 등 GTK 라이브러리 미설치, sudo 없음 → Playwright/Puppeteer 직접 실행 불가.
Docker `zenika/alpine-chrome:with-node` 또는 `mcr.microsoft.com/playwright/python:v1.59.0-noble` 이미지 활용 필요.
