import asyncio
import json
from datetime import date, datetime
from pathlib import Path

import networkx as nx

from app.config import config
from app.utils.logger import get_logger

logger = get_logger(__name__)


def should_run(now: datetime, last_run_date: date | None, hour: int) -> bool:
    """True iff no digest has run today and the local hour has reached `hour`."""
    if last_run_date == now.date():
        return False
    return now.hour >= hour


def _reinforcement_suggestions(health: dict, analysis: dict) -> list[str]:
    out: list[str] = []
    isolated = health.get("isolated_nodes", [])
    if isolated:
        names = ", ".join(n.get("name", "?") for n in isolated[:5])
        out.append(f"고립 노드 {len(isolated)}개를 관련 노드와 연결하세요: {names}")
    wiki = health.get("wiki_graph_lint", {})
    missing_source = wiki.get("missing_source_nodes", [])
    if missing_source:
        out.append(f"provenance 없는 노드 {len(missing_source)}개에 출처 문서를 추가하세요.")
    without_pages = wiki.get("graph_nodes_without_pages", [])
    if without_pages:
        out.append(f"vault 노트가 없는 노드 {len(without_pages)}개 — 빌드/노트 생성을 권장합니다.")
    for issue in analysis.get("issues", [])[:3]:
        suggestion = issue.get("suggestion")
        if suggestion:
            out.append(suggestion)
    return out
