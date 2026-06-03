# Phase 2b Scheduled Digest Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a deterministic daily digest (`Digests/YYYY-MM-DD.md`) per built project that summarizes new nodes, isolated-node warnings, prior AnalysisAgent weaknesses, and reinforcement suggestions — driven by a single asyncio lifespan task plus manual/list/read API endpoints.

**Architecture:** A new `app/services/digest.py` holds pure helpers (`should_run`, `_reinforcement_suggestions`, `_render_markdown`), a `compose_digest` (loads graph, runs health check, diffs new nodes, reuses `analysis.json`), a `generate_digest` (writes the vault file + `digest_state.json` + trace), and a `DigestService` background loop mirroring the Phase 2a `WatcherService`. A new `app/api/digest.py` router exposes POST/GET endpoints. **No LLM calls** — digest is fully deterministic.

**Tech Stack:** Python 3, FastAPI, networkx, pytest. Reuses `app/utils/graph_health.run_health_check`, `app/utils/trace.record_trace`, `app/config.config`.

---

## Working Directory & Conventions

- All commands run from `src/backend/` (where `pyproject.toml` lives).
- Tests run with `python3 -m pytest`.
- Service tests monkeypatch config like: `monkeypatch.setattr("app.services.digest.config.PROJECTS_DIR", str(tmp_path))`.
- API tests use `from app.main import app` + `TestClient(app)` and `monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))` (the `config` singleton is shared across modules).
- Graph nodes carry `name` and `type` attributes; node ids are strings. Load with `nx.node_link_graph(json.loads(...))`.
- `analysis.json` issue shape: `{"category","severity","description","suggestion"}`; top-level `{"summary","issues","improved_draft","generated_at"}`.
- `run_health_check(graph, vault_path=...)` returns keys: `isolated_nodes`, `weak_components`, `duplicate_candidates`, `hub_nodes`, `wiki_graph_lint` (which has `missing_source_nodes`, `graph_nodes_without_pages`, ...), `summary`.

---

### Task 1: Config settings + `should_run` scheduling predicate

**Files:**
- Modify: `app/config.py` (after the `WATCHER_POLL_SECONDS: int = 15` line, ~line 10)
- Create: `app/services/digest.py`
- Test: `tests/test_services/test_digest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_services/test_digest.py`:

```python
from datetime import date, datetime

from app.config import config
from app.services.digest import should_run


def test_config_digest_defaults():
    assert config.DIGEST_ENABLED is False
    assert config.DIGEST_HOUR == 7
    assert config.DIGEST_POLL_SECONDS == 300


def test_should_run_false_when_already_ran_today():
    now = datetime(2026, 6, 3, 9, 0)
    assert should_run(now, date(2026, 6, 3), hour=7) is False


def test_should_run_true_when_new_day_and_hour_passed():
    now = datetime(2026, 6, 3, 9, 0)
    assert should_run(now, date(2026, 6, 2), hour=7) is True


def test_should_run_true_when_never_ran_and_hour_passed():
    now = datetime(2026, 6, 3, 7, 0)
    assert should_run(now, None, hour=7) is True


def test_should_run_false_before_hour():
    now = datetime(2026, 6, 3, 6, 59)
    assert should_run(now, None, hour=7) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_services/test_digest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.digest'` (and config attrs missing).

- [ ] **Step 3: Add config fields**

In `app/config.py`, immediately after `WATCHER_POLL_SECONDS: int = 15`:

```python
    DIGEST_ENABLED: bool = False
    DIGEST_HOUR: int = 7
    DIGEST_POLL_SECONDS: int = 300
```

- [ ] **Step 4: Create `app/services/digest.py` with imports + `should_run`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_services/test_digest.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add app/config.py app/services/digest.py tests/test_services/test_digest.py
git commit -m "feat(digest): config settings + should_run scheduling predicate"
```

---

### Task 2: `_reinforcement_suggestions` deterministic deriver

**Files:**
- Modify: `app/services/digest.py`
- Test: `tests/test_services/test_digest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_services/test_digest.py`:

```python
from app.services.digest import _reinforcement_suggestions


def _health(isolated=None, missing_source=None, without_pages=None):
    return {
        "isolated_nodes": isolated or [],
        "wiki_graph_lint": {
            "missing_source_nodes": missing_source or [],
            "graph_nodes_without_pages": without_pages or [],
        },
    }


def test_suggestions_empty_when_clean():
    assert _reinforcement_suggestions(_health(), {}) == []


def test_suggestions_flag_isolated_nodes():
    health = _health(isolated=[{"name": "Foo", "type": "Concept"}])
    out = _reinforcement_suggestions(health, {})
    assert any("고립 노드 1개" in s and "Foo" in s for s in out)


def test_suggestions_flag_missing_source_and_pages():
    health = _health(
        missing_source=[{"name": "Bar"}],
        without_pages=[{"name": "Baz"}],
    )
    out = _reinforcement_suggestions(health, {})
    assert any("provenance" in s for s in out)
    assert any("vault 노트" in s for s in out)


def test_suggestions_include_analysis_suggestions():
    analysis = {"issues": [{"suggestion": "정량적 성과를 추가하세요."}]}
    out = _reinforcement_suggestions(_health(), analysis)
    assert "정량적 성과를 추가하세요." in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_services/test_digest.py -k suggestions -v`
Expected: FAIL — `ImportError: cannot import name '_reinforcement_suggestions'`.

- [ ] **Step 3: Implement**

Append to `app/services/digest.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_services/test_digest.py -k suggestions -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add app/services/digest.py tests/test_services/test_digest.py
git commit -m "feat(digest): deterministic reinforcement suggestions"
```

---

### Task 3: `_render_markdown` + 20-item cap helper

**Files:**
- Modify: `app/services/digest.py`
- Test: `tests/test_services/test_digest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_services/test_digest.py`:

```python
from app.services.digest import _cap_lines, _render_markdown


def test_cap_lines_appends_overflow_note():
    lines = [f"- item {i}" for i in range(25)]
    capped = _cap_lines(lines)
    assert len(capped) == 21
    assert capped[-1] == "- ... 외 5개"


def test_cap_lines_no_change_under_limit():
    lines = ["- a", "- b"]
    assert _cap_lines(lines) == ["- a", "- b"]


def test_render_markdown_has_all_sections():
    md = _render_markdown(
        date_str="2026-06-03",
        total_nodes=10,
        total_edges=20,
        new_node_names=["Alpha", "Beta"],
        isolated=[{"name": "Foo", "type": "Concept"}],
        missing_source=[],
        analysis={"summary": "전반 평가", "issues": [{"description": "약점1"}]},
        suggestions=["제안1"],
    )
    assert "# Digest 2026-06-03" in md
    assert "## 요약" in md
    assert "## 신규 노드" in md
    assert "- [[Alpha]]" in md
    assert "## 경고" in md
    assert "[[Foo]]" in md
    assert "## 약점 (직전 분석)" in md
    assert "약점1" in md
    assert "## 다음 보강 제안" in md
    assert "- 제안1" in md


def test_render_markdown_caps_new_nodes():
    md = _render_markdown(
        date_str="2026-06-03",
        total_nodes=30,
        total_edges=0,
        new_node_names=[f"N{i}" for i in range(25)],
        isolated=[],
        missing_source=[],
        analysis={},
        suggestions=[],
    )
    assert "... 외 5개" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_services/test_digest.py -k "render or cap_lines" -v`
Expected: FAIL — `ImportError: cannot import name '_cap_lines'`.

- [ ] **Step 3: Implement**

Append to `app/services/digest.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_services/test_digest.py -k "render or cap_lines" -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add app/services/digest.py tests/test_services/test_digest.py
git commit -m "feat(digest): markdown renderer with 20-item cap"
```

---

### Task 4: `compose_digest` (load graph, health, new-node diff, reuse analysis)

**Files:**
- Modify: `app/services/digest.py`
- Test: `tests/test_services/test_digest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_services/test_digest.py`:

```python
import networkx as nx

from app.services.digest import compose_digest


def _write_graph(proj_dir, nodes: list[tuple[str, str, str]], edges=None):
    """nodes: list of (id, name, type)."""
    g = nx.DiGraph()
    for nid, name, ntype in nodes:
        g.add_node(nid, name=name, type=ntype, source_files=["f.txt"])
    for a, b in (edges or []):
        g.add_edge(a, b)
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(g), ensure_ascii=False), encoding="utf-8"
    )


def test_compose_returns_none_when_no_graph(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.digest.config.PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.digest.config.VAULT_DIR", str(tmp_path / "vault"))
    (tmp_path / "p1").mkdir()
    assert compose_digest("p1") is None


def test_compose_new_nodes_diff_against_state(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.digest.config.PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.digest.config.VAULT_DIR", str(tmp_path / "vault"))
    proj = tmp_path / "p1"
    _write_graph(proj, [("n1", "Alpha", "Skill"), ("n2", "Beta", "Project")],
                 edges=[("n1", "n2")])
    (proj / "digest_state.json").write_text(
        json.dumps({"last_node_ids": ["n1"]}), encoding="utf-8"
    )
    result = compose_digest("p1")
    assert result["new_node_count"] == 1
    assert result["new_node_names"] == ["Beta"]
    assert result["current_node_ids"] == ["n1", "n2"]


def test_compose_all_new_when_no_state(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.digest.config.PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.digest.config.VAULT_DIR", str(tmp_path / "vault"))
    proj = tmp_path / "p1"
    _write_graph(proj, [("n1", "Alpha", "Skill")])
    result = compose_digest("p1")
    assert result["new_node_count"] == 1
    assert "# Digest" in result["markdown"]


def test_compose_includes_isolated_warning(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.digest.config.PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.digest.config.VAULT_DIR", str(tmp_path / "vault"))
    proj = tmp_path / "p1"
    # n3 has no edges -> isolated
    _write_graph(proj, [("n1", "Alpha", "Skill"), ("n2", "Beta", "Project"),
                        ("n3", "Lonely", "Concept")], edges=[("n1", "n2")])
    result = compose_digest("p1")
    assert result["isolated_count"] >= 1
    assert "Lonely" in result["markdown"]


def test_compose_without_analysis_file(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.digest.config.PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.digest.config.VAULT_DIR", str(tmp_path / "vault"))
    proj = tmp_path / "p1"
    _write_graph(proj, [("n1", "Alpha", "Skill")])
    result = compose_digest("p1")
    assert "(분석 없음)" in result["markdown"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_services/test_digest.py -k compose -v`
Expected: FAIL — `ImportError: cannot import name 'compose_digest'`.

- [ ] **Step 3: Implement**

Append to `app/services/digest.py`:

```python
def compose_digest(project_id: str) -> dict | None:
    from app.utils.graph_health import run_health_check

    proj_dir = Path(config.PROJECTS_DIR) / project_id
    graph_path = proj_dir / "graph.json"
    if not graph_path.exists():
        return None
    graph = nx.node_link_graph(json.loads(graph_path.read_text(encoding="utf-8")))

    vault_path = str(Path(config.VAULT_DIR) / project_id)
    health = run_health_check(graph, vault_path=vault_path)

    last_ids: list[str] = []
    state_path = proj_dir / "digest_state.json"
    if state_path.exists():
        try:
            last_ids = json.loads(state_path.read_text(encoding="utf-8")).get(
                "last_node_ids", []
            )
        except Exception:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_services/test_digest.py -k compose -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add app/services/digest.py tests/test_services/test_digest.py
git commit -m "feat(digest): compose_digest with new-node diff and analysis reuse"
```

---

### Task 5: `generate_digest` (write vault file + state + trace, idempotent)

**Files:**
- Modify: `app/services/digest.py`
- Test: `tests/test_services/test_digest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_services/test_digest.py`:

```python
from app.services.digest import generate_digest


def test_generate_writes_file_and_state(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.digest.config.PROJECTS_DIR", str(tmp_path))
    vault = tmp_path / "vault"
    monkeypatch.setattr("app.services.digest.config.VAULT_DIR", str(vault))
    # trace.record_trace uses config.PROJECTS_DIR via its own import
    monkeypatch.setattr("app.utils.trace.config.PROJECTS_DIR", str(tmp_path))
    proj = tmp_path / "p1"
    _write_graph(proj, [("n1", "Alpha", "Skill")])

    result = generate_digest("p1", trigger="manual")

    digest_file = vault / "p1" / "Digests" / f"{result['date']}.md"
    assert digest_file.exists()
    assert "# Digest" in digest_file.read_text(encoding="utf-8")

    state = json.loads((proj / "digest_state.json").read_text(encoding="utf-8"))
    assert state["last_node_ids"] == ["n1"]
    assert state["last_digest_date"] == result["date"]

    assert "current_node_ids" not in result  # popped before return

    traces = (proj / "traces.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert any('"operation": "digest"' in t for t in traces)


def test_generate_idempotent_same_day(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.digest.config.PROJECTS_DIR", str(tmp_path))
    vault = tmp_path / "vault"
    monkeypatch.setattr("app.services.digest.config.VAULT_DIR", str(vault))
    monkeypatch.setattr("app.utils.trace.config.PROJECTS_DIR", str(tmp_path))
    proj = tmp_path / "p1"
    _write_graph(proj, [("n1", "Alpha", "Skill")])

    r1 = generate_digest("p1")
    r2 = generate_digest("p1")

    digest_dir = vault / "p1" / "Digests"
    files = list(digest_dir.glob("*.md"))
    assert len(files) == 1
    assert r1["date"] == r2["date"]


def test_generate_returns_none_when_no_graph(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.digest.config.PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.digest.config.VAULT_DIR", str(tmp_path / "vault"))
    (tmp_path / "p1").mkdir()
    assert generate_digest("p1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_services/test_digest.py -k generate -v`
Expected: FAIL — `ImportError: cannot import name 'generate_digest'`.

- [ ] **Step 3: Implement**

Append to `app/services/digest.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_services/test_digest.py -k generate -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add app/services/digest.py tests/test_services/test_digest.py
git commit -m "feat(digest): generate_digest writes vault file, state, trace"
```

---

### Task 6: `DigestService` background loop

**Files:**
- Modify: `app/services/digest.py`
- Test: `tests/test_services/test_digest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_services/test_digest.py`:

```python
import asyncio

from app.services.digest import DigestService


def test_eligible_projects_requires_graph(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.digest.config.PROJECTS_DIR", str(tmp_path))
    built = tmp_path / "built"
    built.mkdir()
    (built / "graph.json").write_text("{}", encoding="utf-8")
    (tmp_path / "unbuilt").mkdir()
    svc = DigestService()
    assert svc.eligible_projects() == ["built"]


def test_poll_once_runs_generate_when_due(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.digest.config.PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.digest.config.DIGEST_HOUR", 0)
    built = tmp_path / "p1"
    built.mkdir()
    (built / "graph.json").write_text("{}", encoding="utf-8")

    calls = []
    monkeypatch.setattr(
        "app.services.digest.generate_digest",
        lambda pid, trigger="scheduled": calls.append((pid, trigger)),
    )

    svc = DigestService()
    asyncio.run(svc.poll_once(now=datetime(2026, 6, 3, 9, 0)))
    assert calls == [("p1", "scheduled")]
    assert svc._last_run_date == date(2026, 6, 3)


def test_poll_once_skips_when_not_due(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.digest.config.PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.digest.config.DIGEST_HOUR", 7)
    built = tmp_path / "p1"
    built.mkdir()
    (built / "graph.json").write_text("{}", encoding="utf-8")

    calls = []
    monkeypatch.setattr(
        "app.services.digest.generate_digest",
        lambda pid, trigger="scheduled": calls.append(pid),
    )

    svc = DigestService()
    asyncio.run(svc.poll_once(now=datetime(2026, 6, 3, 6, 0)))  # before hour
    assert calls == []


def test_poll_once_continues_after_project_error(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.digest.config.PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.digest.config.DIGEST_HOUR", 0)
    for pid in ("p1", "p2"):
        d = tmp_path / pid
        d.mkdir()
        (d / "graph.json").write_text("{}", encoding="utf-8")

    seen = []

    def flaky(pid, trigger="scheduled"):
        seen.append(pid)
        if pid == "p1":
            raise RuntimeError("boom")

    monkeypatch.setattr("app.services.digest.generate_digest", flaky)
    svc = DigestService()
    asyncio.run(svc.poll_once(now=datetime(2026, 6, 3, 9, 0)))
    assert seen == ["p1", "p2"]  # p2 still processed despite p1 error


def test_start_noop_when_disabled(monkeypatch):
    monkeypatch.setattr("app.services.digest.config.DIGEST_ENABLED", False)
    svc = DigestService()
    svc.start()
    assert svc._task is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_services/test_digest.py -k "DigestService or poll_once or eligible or start_noop" -v`
Expected: FAIL — `ImportError: cannot import name 'DigestService'`.

- [ ] **Step 3: Implement**

Append to `app/services/digest.py`:

```python
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

    async def poll_once(self, now: datetime | None = None) -> None:
        now = now or datetime.now()
        if not should_run(now, self._last_run_date, config.DIGEST_HOUR):
            return
        for project_id in self.eligible_projects():
            try:
                generate_digest(project_id, trigger="scheduled")
            except Exception as e:
                logger.error(f"Digest: {project_id} 생성 실패: {e}")
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_services/test_digest.py -k "DigestService or poll_once or eligible or start_noop" -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the full digest service suite**

Run: `python3 -m pytest tests/test_services/test_digest.py -v`
Expected: PASS (all green — 26 tests).

- [ ] **Step 6: Commit**

```bash
git add app/services/digest.py tests/test_services/test_digest.py
git commit -m "feat(digest): DigestService background loop with daily scheduling"
```

---

### Task 7: API router + wire into main.py lifespan

**Files:**
- Create: `app/api/digest.py`
- Modify: `app/main.py` (imports line 5-6, `_watcher` line 11, lifespan lines 14-20, router registration lines 38-45)
- Test: `tests/test_api/test_digest_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api/test_digest_api.py`:

```python
import json

import networkx as nx
from fastapi.testclient import TestClient

from app.config import config
from app.main import app


def _write_graph(proj_dir, nodes):
    g = nx.DiGraph()
    for nid, name, ntype in nodes:
        g.add_node(nid, name=name, type=ntype, source_files=["f.txt"])
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(g), ensure_ascii=False), encoding="utf-8"
    )


def test_post_digest_creates_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    _write_graph(tmp_path / "p1", [("n1", "Alpha", "Skill")])

    client = TestClient(app)
    resp = client.post("/api/projects/p1/digest")
    assert resp.status_code == 200
    body = resp.json()
    assert "markdown" in body
    assert body["new_node_count"] == 1
    assert (tmp_path / "vault" / "p1" / "Digests" / f"{body['date']}.md").exists()


def test_post_digest_404_when_no_graph(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    (tmp_path / "p1").mkdir()
    client = TestClient(app)
    resp = client.post("/api/projects/p1/digest")
    assert resp.status_code == 404


def test_list_digests_descending(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    d = tmp_path / "vault" / "p1" / "Digests"
    d.mkdir(parents=True)
    (d / "2026-06-01.md").write_text("a", encoding="utf-8")
    (d / "2026-06-03.md").write_text("b", encoding="utf-8")
    client = TestClient(app)
    resp = client.get("/api/projects/p1/digests")
    assert resp.status_code == 200
    assert resp.json() == {"dates": ["2026-06-03", "2026-06-01"]}


def test_list_digests_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    client = TestClient(app)
    resp = client.get("/api/projects/unknown/digests")
    assert resp.status_code == 200
    assert resp.json() == {"dates": []}


def test_get_digest_returns_markdown(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    d = tmp_path / "vault" / "p1" / "Digests"
    d.mkdir(parents=True)
    (d / "2026-06-03.md").write_text("# Digest 2026-06-03", encoding="utf-8")
    client = TestClient(app)
    resp = client.get("/api/projects/p1/digests/2026-06-03")
    assert resp.status_code == 200
    assert resp.json()["markdown"] == "# Digest 2026-06-03"


def test_get_digest_404(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    client = TestClient(app)
    resp = client.get("/api/projects/p1/digests/2099-01-01")
    assert resp.status_code == 404


def test_main_has_digest_service():
    import app.main as main_mod
    assert hasattr(main_mod, "DigestService")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api/test_digest_api.py -v`
Expected: FAIL — 404 on POST/GET (router not registered) and `AttributeError` for `DigestService`.

- [ ] **Step 3: Create the router `app/api/digest.py`**

```python
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.config import config
from app.services.digest import generate_digest

router = APIRouter()


def _digests_dir(project_id: str) -> Path:
    return Path(config.VAULT_DIR) / project_id / "Digests"


@router.post("/{project_id}/digest")
async def create_digest(project_id: str):
    result = generate_digest(project_id, trigger="manual")
    if result is None:
        raise HTTPException(404, "graph not found for project")
    return result


@router.get("/{project_id}/digests")
async def list_digests(project_id: str):
    d = _digests_dir(project_id)
    if not d.exists():
        return {"dates": []}
    dates = sorted(
        (p.stem for p in d.glob("*.md") if p.is_file()), reverse=True
    )
    return {"dates": dates}


@router.get("/{project_id}/digests/{digest_date}")
async def get_digest(project_id: str, digest_date: str):
    path = _digests_dir(project_id) / f"{digest_date}.md"
    if not path.exists():
        raise HTTPException(404, "digest not found")
    return {"date": digest_date, "markdown": path.read_text(encoding="utf-8")}
```

- [ ] **Step 4: Wire into `app/main.py`**

Change the import line (currently `from app.api import projects, graph, chat, tasks, user, settings, skills`) to add `digest`:

```python
from app.api import projects, graph, chat, tasks, user, settings, skills, digest
from app.services.watcher import WatcherService
from app.services.digest import DigestService
```

Change the service instantiation (currently `_watcher = WatcherService()`) to:

```python
_watcher = WatcherService()
_digest = DigestService()
```

Change the lifespan body to start/stop both:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    _watcher.start()
    _digest.start()
    try:
        yield
    finally:
        await _watcher.stop()
        await _digest.stop()
```

Add the router registration after the `skills.router` line:

```python
app.include_router(digest.router, prefix="/api/projects", tags=["digest"])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api/test_digest_api.py -v`
Expected: PASS (7 passed).

- [ ] **Step 6: Run the full backend suite for regressions**

Run: `python3 -m pytest tests/ -q`
Expected: PASS — previous 269 + 26 service + 7 api = 302 passed (count approximate; all green).

- [ ] **Step 7: Commit**

```bash
git add app/api/digest.py app/main.py tests/test_api/test_digest_api.py
git commit -m "feat(digest): API endpoints + DigestService wired into lifespan"
```

---

### Task 8: Update handoff doc

**Files:**
- Modify: `docs/claude-code-handoff.md` (prepend a dated section)

- [ ] **Step 1: Prepend a section** (use the absolute repo-root path; the doc lives at repo root, not under `src/backend/`)

Add at the top of `docs/claude-code-handoff.md`:

```markdown
## 2026-06-03 Phase 2b — Scheduled Digest Agent

**What:** Deterministic daily digest per built project → `vault/<id>/Digests/YYYY-MM-DD.md`.
No LLM calls; composed from `run_health_check` + new-node diff (`digest_state.json`) +
reused `analysis.json`.

**New files:** `app/services/digest.py` (compose/generate/should_run/DigestService),
`app/api/digest.py` (POST `/api/projects/{id}/digest`, GET `/digests`, GET `/digests/{date}`).

**Config:** `DIGEST_ENABLED=False` (opt-in), `DIGEST_HOUR=7`, `DIGEST_POLL_SECONDS=300`.

**Wiring:** `DigestService` started/stopped in `app/main.py` lifespan alongside `WatcherService`.

**Verification:** `python3 -m pytest tests/ -q` → all green.

**Next candidates:** local-LLM prose synthesis (optional layer), Obsidian plugin "new digest"
badge (polls the list endpoint), weekly cadence, deleted-node tracking.
```

- [ ] **Step 2: Commit**

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS
git add docs/claude-code-handoff.md
git commit -m "docs: handoff note for Phase 2b digest agent"
```

---

## Self-Review Notes

- **Spec coverage:** §3 architecture → Tasks 6-7; §4 components → `should_run` (T1), suggestions (T2), render (T3), `compose_digest` (T4), `generate_digest` (T5), `DigestService` (T6), router (T7); §5 data flow → T4/T5; §6 markdown → T3; §7 eligibility (`graph.json` only) → T6 `eligible_projects`; §8 config → T1; §9 API contract → T7; §10 safety (opt-in, single task, idempotent, per-project except) → T6/T5; §11 errors → T4 (None on missing graph), T5 (trace best-effort), T6 (per-project + per-cycle try/except); §12 tests → every task; §13 file changes → all tasks; §14 non-goals respected (no LLM, no badge UI, no weekly).
- **Signatures consistent across tasks:** `should_run(now, last_run_date, hour)`, `_reinforcement_suggestions(health, analysis)`, `_cap_lines(rendered)`, `_render_markdown(date_str, total_nodes, total_edges, new_node_names, isolated, missing_source, analysis, suggestions)`, `compose_digest(project_id) -> dict|None` (includes `current_node_ids`), `generate_digest(project_id, trigger="manual")` (pops `current_node_ids`), `DigestService.poll_once(now=None)`.
- **No placeholders:** every code/test step shows complete code and exact run/expected lines.
```
