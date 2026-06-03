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


def _read_digest_state(project_id: str) -> dict:
    state_path = Path(config.PROJECTS_DIR) / project_id / "digest_state.json"
    if not state_path.exists():
        return {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _read_last_digest_date(project_id: str) -> date | None:
    raw = _read_digest_state(project_id).get("last_digest_date")
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


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


def compose_digest(project_id: str) -> dict | None:
    from app.utils.graph_health import run_health_check

    proj_dir = Path(config.PROJECTS_DIR) / project_id
    graph_path = proj_dir / "graph.json"
    if not graph_path.exists():
        return None
    graph = nx.node_link_graph(json.loads(graph_path.read_text(encoding="utf-8")))

    vault_path = str(Path(config.VAULT_DIR) / project_id)
    health = run_health_check(graph, vault_path=vault_path)

    last_ids = _read_digest_state(project_id).get("last_node_ids", [])
    if not isinstance(last_ids, list):
        last_ids = []

    current_ids = list(graph.nodes)
    last_set = set(last_ids)
    new_ids = [i for i in current_ids if i not in last_set]
    new_names = [graph.nodes[i].get("name", str(i)) for i in new_ids]

    analysis: dict = {}
    analysis_path = proj_dir / "analysis.json"
    if analysis_path.exists():
        try:
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        except Exception:
            analysis = {}

    isolated = health.get("isolated_nodes", [])
    missing_source = health.get("wiki_graph_lint", {}).get("missing_source_nodes", [])
    suggestions = _reinforcement_suggestions(health, analysis)

    date_str = date.today().isoformat()
    markdown = _render_markdown(
        date_str=date_str,
        total_nodes=graph.number_of_nodes(),
        total_edges=graph.number_of_edges(),
        new_node_names=new_names,
        isolated=isolated,
        missing_source=missing_source,
        analysis=analysis,
        suggestions=suggestions,
    )

    return {
        "date": date_str,
        "markdown": markdown,
        "new_node_count": len(new_names),
        "new_node_names": new_names,
        "isolated_count": len(isolated),
        "suggestion_count": len(suggestions),
        "current_node_ids": current_ids,
    }


def generate_digest(project_id: str, trigger: str = "manual") -> dict | None:
    from app.utils.trace import record_trace

    result = compose_digest(project_id)
    if result is None:
        return None

    proj_dir = Path(config.PROJECTS_DIR) / project_id
    digests_dir = Path(config.VAULT_DIR) / project_id / "Digests"
    digests_dir.mkdir(parents=True, exist_ok=True)
    (digests_dir / f"{result['date']}.md").write_text(
        result["markdown"], encoding="utf-8"
    )

    current_ids = result.pop("current_node_ids")
    (proj_dir / "digest_state.json").write_text(
        json.dumps(
            {"last_node_ids": current_ids, "last_digest_date": result["date"]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    try:
        record_trace(
            project_id,
            "digest",
            trigger=trigger,
            new_nodes=result["new_node_count"],
            isolated=result["isolated_count"],
            suggestions=result["suggestion_count"],
        )
    except Exception:
        pass

    return result


class DigestService:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._stop = False
        self._last_run_date: date | None = None

    def eligible_projects(self) -> list[str]:
        root = Path(config.PROJECTS_DIR)
        if not root.exists():
            return []
        result = []
        for proj in sorted(root.iterdir()):
            if proj.is_dir() and (proj / "graph.json").exists():
                result.append(proj.name)
        return result

    def _seed_last_run_date(self, project_ids: list[str], today: date) -> None:
        if self._last_run_date is not None or not project_ids:
            return
        last_dates = [_read_last_digest_date(project_id) for project_id in project_ids]
        if last_dates and all(last_date == today for last_date in last_dates):
            self._last_run_date = today

    def _run_scheduled_digest_cycle(self, project_ids: list[str], run_date: date) -> None:
        for project_id in project_ids:
            if _read_last_digest_date(project_id) == run_date:
                continue
            try:
                generate_digest(project_id, trigger="scheduled")
            except Exception as e:
                logger.error(f"Digest: {project_id} 생성 실패: {e}")

    async def poll_once(self, now: datetime | None = None) -> None:
        now = now or datetime.now()
        project_ids = self.eligible_projects()
        self._seed_last_run_date(project_ids, now.date())
        if not should_run(now, self._last_run_date, config.DIGEST_HOUR):
            return
        await asyncio.to_thread(self._run_scheduled_digest_cycle, project_ids, now.date())
        # The scheduled digest is best-effort: once the cycle has considered every
        # eligible project, wait until the next local day before trying again.
        self._last_run_date = now.date()

    async def _loop(self) -> None:
        while not self._stop:
            try:
                await self.poll_once()
            except Exception as e:
                logger.error(f"Digest 폴링 사이클 실패: {e}")
            await asyncio.sleep(config.DIGEST_POLL_SECONDS)

    def start(self) -> None:
        if not config.DIGEST_ENABLED:
            return
        self._stop = False
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"Digest 시작 (간격 {config.DIGEST_POLL_SECONDS}s, 시각 {config.DIGEST_HOUR}시)"
        )

    async def stop(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
