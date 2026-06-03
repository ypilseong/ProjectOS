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


_LIST_CAP = 20


def _cap_lines(rendered: list[str]) -> list[str]:
    if len(rendered) <= _LIST_CAP:
        return rendered
    extra = len(rendered) - _LIST_CAP
    return rendered[:_LIST_CAP] + [f"- ... 외 {extra}개"]


def _render_markdown(
    date_str: str,
    total_nodes: int,
    total_edges: int,
    new_node_names: list[str],
    isolated: list[dict],
    missing_source: list[dict],
    analysis: dict,
    suggestions: list[str],
) -> str:
    lines = [f"# Digest {date_str}", "", "## 요약", ""]
    lines.append(f"- 노드 {total_nodes}개 / 엣지 {total_edges}개")
    lines.append(f"- 신규 노드 {len(new_node_names)}개")
    lines.append(f"- 고립 노드 {len(isolated)}개")
    lines.append("")

    lines.append("## 신규 노드")
    lines.append("")
    if new_node_names:
        lines.extend(_cap_lines([f"- [[{n}]]" for n in new_node_names]))
    else:
        lines.append("- (없음)")
    lines.append("")

    lines.append("## 경고")
    lines.append("")
    lines.append(f"### 고립 노드 ({len(isolated)})")
    if isolated:
        lines.extend(_cap_lines(
            [f"- [[{n.get('name', '?')}]] ({n.get('type', '?')})" for n in isolated]
        ))
    else:
        lines.append("- (없음)")
    lines.append(f"### source 누락 노드 ({len(missing_source)})")
    if missing_source:
        lines.extend(_cap_lines(
            [f"- [[{n.get('name', '?')}]] ({n.get('type', '?')})" for n in missing_source]
        ))
    else:
        lines.append("- (없음)")
    lines.append("")

    lines.append("## 약점 (직전 분석)")
    lines.append("")
    summary = analysis.get("summary", "")
    if summary:
        lines.append(summary)
        lines.append("")
    issues = analysis.get("issues", [])
    if issues:
        for issue in issues[:5]:
            desc = issue.get("description", "")
            if desc:
                lines.append(f"- {desc}")
    else:
        lines.append("- (분석 없음)")
    lines.append("")

    lines.append("## 다음 보강 제안")
    lines.append("")
    if suggestions:
        lines.extend(f"- {s}" for s in suggestions)
    else:
        lines.append("- (없음)")
    lines.append("")

    return "\n".join(lines)
