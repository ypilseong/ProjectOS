# Vault Reconcile 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Obsidian vault의 수동 편집(설명/연결/노드 추가·삭제)을 감지해 `graph_patch` 패치로 변환하고, dry-run 프리뷰 후 그래프에 적용한다.

**Architecture:** 신규 모듈 `app/services/vault_reconcile.py`에 (1) vault 페이지 파서, (2) 렌더링 인지 differ, (3) dry-run/apply orchestrator를 구현한다. 기존 `app/utils/graph_patch.py` 적용 계층을 재사용하고 `POST /projects/{id}/reconcile` 엔드포인트와 `projectos_reconcile_vault` MCP 도구로 노출한다.

**Tech Stack:** Python, NetworkX, FastAPI, 기존 graph_patch / graph_restructure / obsidian_writer_agent 유틸.

**핵심 정확성 제약:** differ는 실제 `graph.json`(=G)을 직접 비교하지 않는다. `ObsidianWriterAgent`는 `demote_project_context_nodes`(노드 제거 + 합성 Skill 추가)와 `build_entity_details`를 적용한 뒤 렌더링하며 `Category`·무명 노드는 페이지가 없다. 따라서 differ는 렌더링된 그래프 `R = build_entity_details(demote_project_context_nodes(G.copy()))`과 vault를 비교해 "사용자가 바꾼 것"을 판정하고, 패치는 G에 안전하게 적용 가능한 항목만 보수적으로 방출한다.

---

## File Structure

- Create: `src/backend/app/services/vault_reconcile.py` — 파서 + differ + orchestrator (단일 책임: vault→graph 역동기화)
- Create: `src/backend/tests/test_services/test_vault_reconcile.py` — 단위 테스트
- Modify: `src/backend/app/api/projects.py` — `POST /{project_id}/reconcile` 엔드포인트
- Modify: `src/backend/app/mcp_tools.py` — `projectos_reconcile_vault` 도구 등록 + 핸들러
- Modify: `src/backend/tests/test_api/test_mcp_api.py` — MCP 도구 테스트

**중요:** 모든 pytest/git 명령은 working directory 주의. pytest는 `cd src/backend`에서, git은 repo root에서 실행.

---

### Task 1: Vault 페이지 파서

**Files:**
- Create: `src/backend/app/services/vault_reconcile.py`
- Test: `src/backend/tests/test_services/test_vault_reconcile.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/backend/tests/test_services/test_vault_reconcile.py`:

```python
from pathlib import Path
from app.services.vault_reconcile import parse_vault_page


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_parse_vault_page_extracts_type_name_description(tmp_path):
    page = tmp_path / "Skills" / "Python.md"
    _write(page, '---\ntype: Skill\nname: "Python"\ntags: [skill]\n---\n\n'
                 '# Python\n\n## Overview\n프로그래밍 언어\n\n## Sources\n- cv.pdf\n')
    parsed = parse_vault_page(page)
    assert parsed["type"] == "Skill"
    assert parsed["name"] == "Python"
    assert parsed["description"] == "프로그래밍 언어"


def test_parse_vault_page_treats_placeholder_as_empty(tmp_path):
    page = tmp_path / "Skills" / "X.md"
    _write(page, '---\ntype: Skill\nname: "X"\n---\n\n## Overview\n(설명 없음)\n')
    assert parse_vault_page(page)["description"] == ""


def test_parse_vault_page_parses_connections_both_directions(tmp_path):
    page = tmp_path / "Career" / "Yang.md"
    _write(page, '---\ntype: Person\nname: "Yang"\n---\n\n## Overview\nML\n\n'
                 '## Connections\n\n- USES_SKILL: [[Python]]\n- ← DEVELOPED: [[ProjectOS]]\n')
    conns = parse_vault_page(page)["connections"]
    assert {"relation": "USES_SKILL", "direction": "out", "other": "Python"} in conns
    assert {"relation": "DEVELOPED", "direction": "in", "other": "ProjectOS"} in conns


def test_parse_vault_page_returns_none_without_frontmatter(tmp_path):
    page = tmp_path / "Misc" / "junk.md"
    _write(page, "# no frontmatter here\n\njust text\n")
    assert parse_vault_page(page) is None
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd src/backend && python3 -m pytest tests/test_services/test_vault_reconcile.py -v`
Expected: FAIL with `ImportError` / `ModuleNotFoundError: app.services.vault_reconcile`.

- [ ] **Step 3: 파서 구현**

`src/backend/app/services/vault_reconcile.py`:

```python
import json
import re
from pathlib import Path

import networkx as nx

from app.agents.obsidian_writer_agent import TYPE_TO_FOLDER
from app.config import config
from app.utils.graph_patch import apply_project_graph_patch
from app.utils.graph_restructure import build_entity_details, demote_project_context_nodes
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm: dict = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        fm[key.strip()] = val.strip().strip('"')
    return fm


def _section_body(text: str, title: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(title)}\s*$", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return ""
    start = m.end()
    nxt = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + nxt.start() if nxt else len(text)
    return text[start:end].strip()


def parse_vault_page(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    ntype = fm.get("type")
    name = fm.get("name")
    if not ntype or not name:
        return None

    overview = _section_body(text, "Overview")
    if overview == "(설명 없음)":
        overview = ""

    connections: list[dict] = []
    for line in _section_body(text, "Connections").splitlines():
        line = line.strip()
        m_in = re.match(r"^-\s*←\s*(.*?):\s*\[\[([^\]]+)\]\]", line)
        if m_in:
            connections.append({"relation": m_in.group(1).strip(),
                                "direction": "in", "other": m_in.group(2).strip()})
            continue
        m_out = re.match(r"^-\s*(.*?):\s*\[\[([^\]]+)\]\]", line)
        if m_out:
            connections.append({"relation": m_out.group(1).strip(),
                                "direction": "out", "other": m_out.group(2).strip()})
    return {"type": ntype, "name": name, "description": overview,
            "connections": connections}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_services/test_vault_reconcile.py -v`
Expected: 4 passed.

- [ ] **Step 5: 커밋**

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS
git add src/backend/app/services/vault_reconcile.py src/backend/tests/test_services/test_vault_reconcile.py
git commit -m "feat(reconcile): parse vault pages into type/name/description/connections"
```

---

### Task 2: 렌더링 인지 Differ

**Files:**
- Modify: `src/backend/app/services/vault_reconcile.py`
- Test: `src/backend/tests/test_services/test_vault_reconcile.py`

- [ ] **Step 1: 실패하는 테스트 작성** (파일 끝에 append)

```python
import json
import networkx as nx
import pytest
from app.config import config
from app.services.vault_reconcile import diff_vault_against_graph


def _save_graph(project_dir: Path, graph: nx.DiGraph):
    project_dir.mkdir(parents=True, exist_ok=True)
    data = nx.node_link_data(graph)
    if "edges" in data and "links" not in data:
        data["links"] = data.pop("edges")
    (project_dir / "graph.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _page(vault: Path, folder: str, name: str, ntype: str,
          overview: str, connections: str = ""):
    body = (f'---\ntype: {ntype}\nname: "{name}"\n---\n\n# {name}\n\n'
            f'## Overview\n{overview}\n')
    if connections:
        body += f'\n## Connections\n\n{connections}\n'
    p = vault / folder / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


@pytest.fixture
def reconcile_env(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    vault_root = tmp_path / "vault"
    monkeypatch.setattr(config, "PROJECTS_DIR", str(projects))
    monkeypatch.setattr(config, "VAULT_DIR", str(vault_root))
    pid = "p1"
    g = nx.DiGraph()
    g.add_node("Skill:Python", type="Skill", name="Python", description="언어")
    g.add_node("Project:OS", type="Project", name="OS", description="graph builder")
    g.add_edge("Project:OS", "Skill:Python", relation="USES_SKILL", confidence=1.0)
    _save_graph(projects / pid, g)
    vault = vault_root / pid
    return pid, vault, g


def test_diff_detects_description_change(reconcile_env):
    pid, vault, _ = reconcile_env
    _page(vault, "Skills", "Python", "Skill", "수정된 설명")
    _page(vault, "Projects", "OS", "Project", "graph builder",
          "- USES_SKILL: [[Python]]\n")
    patch = diff_vault_against_graph(pid)
    updates = {(u["type"], u["name"]): u["set"]["description"]
               for u in patch["nodes_update"]}
    assert updates[("Skill", "Python")] == "수정된 설명"


def test_diff_detects_new_edge(reconcile_env):
    pid, vault, _ = reconcile_env
    # Add a brand-new connection Python -> OS that is not in the graph
    _page(vault, "Skills", "Python", "Skill", "언어",
          "- RELATED_TO: [[OS]]\n")
    _page(vault, "Projects", "OS", "Project", "graph builder",
          "- USES_SKILL: [[Python]]\n")
    patch = diff_vault_against_graph(pid)
    adds = {(e["source_name"], e["target_name"], e["relation"])
            for e in patch["edges_add"]}
    assert ("Python", "OS", "RELATED_TO") in adds


def test_diff_union_semantics_keeps_half_deleted_edge(reconcile_env):
    pid, vault, _ = reconcile_env
    # Edge removed from OS page (out) but still present on Python page (in)
    _page(vault, "Skills", "Python", "Skill", "언어",
          "- ← USES_SKILL: [[OS]]\n")
    _page(vault, "Projects", "OS", "Project", "graph builder")
    patch = diff_vault_against_graph(pid)
    assert patch["edges_delete"] == []


def test_diff_deletes_edge_absent_from_both_pages(reconcile_env):
    pid, vault, _ = reconcile_env
    _page(vault, "Skills", "Python", "Skill", "언어")
    _page(vault, "Projects", "OS", "Project", "graph builder")
    patch = diff_vault_against_graph(pid)
    dels = {(e["source_name"], e["target_name"], e["relation"])
            for e in patch["edges_delete"]}
    assert ("OS", "Python", "USES_SKILL") in dels


def test_diff_deletes_node_missing_page(reconcile_env):
    pid, vault, _ = reconcile_env
    # Only Python page exists; OS page deleted by user
    _page(vault, "Skills", "Python", "Skill", "언어")
    patch = diff_vault_against_graph(pid)
    dels = {(n["type"], n["name"]) for n in patch["nodes_delete"]}
    assert ("Project", "OS") in dels


def test_diff_adds_node_for_new_page(reconcile_env):
    pid, vault, _ = reconcile_env
    _page(vault, "Skills", "Python", "Skill", "언어",
          "- ← USES_SKILL: [[OS]]\n")
    _page(vault, "Projects", "OS", "Project", "graph builder",
          "- USES_SKILL: [[Python]]\n")
    _page(vault, "Skills", "Rust", "Skill", "시스템 언어")
    patch = diff_vault_against_graph(pid)
    adds = {(n["type"], n["name"]) for n in patch["nodes_add"]}
    assert ("Skill", "Rust") in adds


def test_diff_excludes_category_nodes_from_deletion(reconcile_env, tmp_path):
    pid, vault, g = reconcile_env
    g.add_node("Category:Skills", type="Category", name="Skills", description="")
    _save_graph(tmp_path / "projects" / pid, g)
    _page(vault, "Skills", "Python", "Skill", "언어",
          "- ← USES_SKILL: [[OS]]\n")
    _page(vault, "Projects", "OS", "Project", "graph builder",
          "- USES_SKILL: [[Python]]\n")
    patch = diff_vault_against_graph(pid)
    dels = {(n["type"], n["name"]) for n in patch["nodes_delete"]}
    assert ("Category", "Skills") not in dels
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd src/backend && python3 -m pytest tests/test_services/test_vault_reconcile.py -v`
Expected: 새 테스트들이 `ImportError: cannot import name 'diff_vault_against_graph'`로 FAIL.

- [ ] **Step 3: Differ 구현** (`vault_reconcile.py`의 파서 함수들 뒤에 append)

```python
def _load_graph(graph_path: Path) -> nx.DiGraph:
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    return nx.node_link_graph(data)


def _rendered_graph(graph: nx.DiGraph) -> nx.DiGraph:
    g = graph.copy()
    g, _ = demote_project_context_nodes(g)
    g, _ = build_entity_details(g)
    return g


def _read_vault_pages(vault: Path) -> dict[tuple[str, str], dict]:
    pages: dict[tuple[str, str], dict] = {}
    for folder in set(TYPE_TO_FOLDER.values()) | {"Misc"}:
        d = vault / folder
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            parsed = parse_vault_page(md)
            if parsed:
                pages[(parsed["type"], parsed["name"])] = parsed
    return pages


def _rendered_pages(rendered: nx.DiGraph) -> dict[tuple[str, str], dict]:
    pages: dict[tuple[str, str], dict] = {}
    for node_id, data in rendered.nodes(data=True):
        if data.get("type") == "Category":
            continue
        name = data.get("name")
        if not name:
            continue
        pages[(data.get("type"), name)] = {
            "id": node_id,
            "description": data.get("description", "") or "",
        }
    return pages


def _rendered_edges(rendered: nx.DiGraph) -> set[tuple[str, str, str]]:
    edges: set[tuple[str, str, str]] = set()
    for u, v, d in rendered.edges(data=True):
        un = rendered.nodes[u].get("name")
        vn = rendered.nodes[v].get("name")
        if not un or not vn:
            continue
        if (rendered.nodes[u].get("type") == "Category"
                and rendered.nodes[v].get("type") == "Category"):
            continue
        edges.add((un, vn, str(d.get("relation", "")).strip().upper()))
    return edges


def _vault_edges(pages: dict[tuple[str, str], dict]) -> set[tuple[str, str, str]]:
    edges: set[tuple[str, str, str]] = set()
    for (_t, pname), parsed in pages.items():
        for c in parsed["connections"]:
            rel = str(c["relation"]).strip().upper()
            if c["direction"] == "out":
                edges.add((pname, c["other"], rel))
            else:
                edges.add((c["other"], pname, rel))
    return edges


def _name_index(graph: nx.DiGraph) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for nid, data in graph.nodes(data=True):
        nm = data.get("name")
        if nm:
            idx.setdefault(nm, []).append(nid)
    return idx


def diff_vault_against_graph(project_id: str) -> dict:
    graph_path = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    if not graph_path.exists():
        raise ValueError("Graph not built yet")
    vault = Path(config.VAULT_DIR) / project_id

    graph = _load_graph(graph_path)
    rendered = _rendered_graph(graph)

    expected = _rendered_pages(rendered)
    vault_pages = _read_vault_pages(vault) if vault.is_dir() else {}
    g_nodes = {
        (data.get("type"), data.get("name")): nid
        for nid, data in graph.nodes(data=True)
        if data.get("name")
    }
    name_idx = _name_index(graph)
    new_names = {nm for (_t, nm) in vault_pages if (_t, nm) not in g_nodes}

    patch: dict = {
        "nodes_add": [], "nodes_update": [], "nodes_delete": [],
        "edges_add": [], "edges_delete": [],
    }

    for key, parsed in vault_pages.items():
        if key in expected and key in g_nodes:
            current = graph.nodes[g_nodes[key]].get("description", "") or ""
            if parsed["description"] != current:
                patch["nodes_update"].append({
                    "type": key[0], "name": key[1],
                    "set": {"description": parsed["description"]},
                })
        elif key not in expected and key not in g_nodes:
            patch["nodes_add"].append({
                "type": key[0], "name": key[1],
                "description": parsed["description"],
            })

    for key in expected:
        if key not in vault_pages and key in g_nodes:
            patch["nodes_delete"].append({"type": key[0], "name": key[1]})

    rendered_e = _rendered_edges(rendered)
    vault_e = _vault_edges(vault_pages)

    def _unique(nm: str) -> bool:
        return len(name_idx.get(nm, [])) == 1

    def _resolvable(nm: str) -> bool:
        return _unique(nm) or nm in new_names

    for (sn, tn, rel) in (vault_e - rendered_e):
        if _resolvable(sn) and _resolvable(tn):
            patch["edges_add"].append({
                "source_name": sn, "target_name": tn,
                "relation": rel, "confidence": 1.0,
            })

    for (sn, tn, rel) in (rendered_e - vault_e):
        if _unique(sn) and _unique(tn):
            su, tv = name_idx[sn][0], name_idx[tn][0]
            if graph.has_edge(su, tv):
                existing = str(graph.edges[su, tv].get("relation", "")).strip().upper()
                if existing == rel:
                    patch["edges_delete"].append({
                        "source_name": sn, "target_name": tn, "relation": rel,
                    })

    return patch
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_services/test_vault_reconcile.py -v`
Expected: 모든 테스트 passed (Task 1의 4개 + Task 2의 7개).

- [ ] **Step 5: 커밋**

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS
git add src/backend/app/services/vault_reconcile.py src/backend/tests/test_services/test_vault_reconcile.py
git commit -m "feat(reconcile): render-aware diff of vault edits into graph_patch"
```

---

### Task 3: Orchestrator (dry-run / apply)

**Files:**
- Modify: `src/backend/app/services/vault_reconcile.py`
- Test: `src/backend/tests/test_services/test_vault_reconcile.py`

- [ ] **Step 1: 실패하는 테스트 작성** (파일 끝에 append)

```python
from app.services.vault_reconcile import reconcile_vault


def test_reconcile_dry_run_does_not_mutate_graph(reconcile_env):
    pid, vault, _ = reconcile_env
    _page(vault, "Skills", "Python", "Skill", "변경된 설명")
    graph_path = Path(config.PROJECTS_DIR) / pid / "graph.json"
    before = graph_path.read_text(encoding="utf-8")
    out = reconcile_vault(pid, apply=False)
    assert out["applied"] is False
    assert out["summary"]["nodes_update"] >= 1
    assert "patch" in out
    assert graph_path.read_text(encoding="utf-8") == before  # unchanged


def test_reconcile_apply_persists_description_change(reconcile_env):
    pid, vault, _ = reconcile_env
    _page(vault, "Skills", "Python", "Skill", "변경된 설명")
    _page(vault, "Projects", "OS", "Project", "graph builder",
          "- USES_SKILL: [[Python]]\n")
    out = reconcile_vault(pid, apply=True)
    assert out["applied"] is True
    g = _load_graph_for_test(Path(config.PROJECTS_DIR) / pid / "graph.json")
    assert g.nodes["Skill:Python"]["description"] == "변경된 설명"


def _load_graph_for_test(path: Path) -> nx.DiGraph:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    return nx.node_link_graph(data)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd src/backend && python3 -m pytest tests/test_services/test_vault_reconcile.py -v -k reconcile`
Expected: `ImportError: cannot import name 'reconcile_vault'`로 FAIL.

- [ ] **Step 3: Orchestrator 구현** (`vault_reconcile.py` 끝에 append)

```python
def reconcile_vault(project_id: str, apply: bool = False) -> dict:
    patch = diff_vault_against_graph(project_id)
    summary = {key: len(patch[key]) for key in patch}
    if not apply:
        logger.info(f"reconcile_vault dry-run for {project_id}: {summary}")
        return {"project_id": project_id, "applied": False,
                "patch": patch, "summary": summary}
    result = apply_project_graph_patch(project_id, patch)
    logger.info(f"reconcile_vault applied for {project_id}: {result['changes']}")
    return {"project_id": project_id, "applied": True,
            "patch": patch, "summary": summary, "result": result}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_services/test_vault_reconcile.py -v`
Expected: 전체 passed.

참고: `apply=True` 경로는 `apply_project_graph_patch`가 `ObsidianWriterAgent().run(...)`을 호출하므로 vault를 다시 렌더링한다. 테스트는 `config.VAULT_DIR`/`PROJECTS_DIR`이 tmp_path로 monkeypatch되어 있어 안전.

- [ ] **Step 5: 커밋**

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS
git add src/backend/app/services/vault_reconcile.py src/backend/tests/test_services/test_vault_reconcile.py
git commit -m "feat(reconcile): add dry-run/apply orchestrator"
```

---

### Task 4: API 엔드포인트

**Files:**
- Modify: `src/backend/app/api/projects.py`
- Test: `src/backend/tests/test_api/test_projects_api.py`

- [ ] **Step 1: 실패하는 테스트 작성** (`test_projects_api.py` 끝에 append)

먼저 파일 상단의 기존 import/fixture 패턴(`client`, `config` monkeypatch)을 확인한다. 아래 테스트는 기존 테스트가 사용하는 동일한 `client` fixture와 `tmp_path` 기반 `config` 설정을 재사용한다. 기존 픽스처 이름이 다르면 그에 맞춘다.

```python
def test_reconcile_endpoint_dry_run_returns_patch(client, tmp_path, monkeypatch):
    import json
    import networkx as nx
    from app.config import config

    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    pid = "pApi"
    g = nx.DiGraph()
    g.add_node("Skill:Python", type="Skill", name="Python", description="언어")
    pdir = tmp_path / "projects" / pid
    pdir.mkdir(parents=True)
    data = nx.node_link_data(g)
    if "edges" in data and "links" not in data:
        data["links"] = data.pop("edges")
    (pdir / "graph.json").write_text(json.dumps(data), encoding="utf-8")
    page = tmp_path / "vault" / pid / "Skills" / "Python.md"
    page.parent.mkdir(parents=True)
    page.write_text('---\ntype: Skill\nname: "Python"\n---\n\n## Overview\n새 설명\n',
                    encoding="utf-8")

    resp = client.post(f"/api/projects/{pid}/reconcile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is False
    assert body["summary"]["nodes_update"] >= 1


def test_reconcile_endpoint_missing_graph_returns_400(client, tmp_path, monkeypatch):
    from app.config import config
    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    resp = client.post("/api/projects/nope/reconcile")
    assert resp.status_code == 400
```

주의: 라우터 prefix가 `/api/projects`인지 `test_projects_api.py`의 기존 테스트 URL로 확인하고 일치시킬 것.

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd src/backend && python3 -m pytest tests/test_api/test_projects_api.py -v -k reconcile`
Expected: 404 (엔드포인트 없음)로 FAIL.

- [ ] **Step 3: 엔드포인트 구현**

`app/api/projects.py` 상단 import에 `HTTPException`이 없으면 추가 (대개 `from fastapi import ... HTTPException ...` 형태로 이미 존재). 파일 끝(다른 `@router.post` 들과 같은 위치)에 추가:

```python
@router.post("/{project_id}/reconcile")
async def reconcile_vault_endpoint(project_id: str, apply: bool = False):
    from app.services.vault_reconcile import reconcile_vault
    try:
        return reconcile_vault(project_id, apply=apply)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_api/test_projects_api.py -v -k reconcile`
Expected: 2 passed.

- [ ] **Step 5: 커밋**

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS
git add src/backend/app/api/projects.py src/backend/tests/test_api/test_projects_api.py
git commit -m "feat(reconcile): add POST /projects/{id}/reconcile endpoint"
```

---

### Task 5: MCP 도구

**Files:**
- Modify: `src/backend/app/mcp_tools.py`
- Test: `src/backend/tests/test_api/test_mcp_api.py`

- [ ] **Step 1: 실패하는 테스트 작성**

먼저 `test_mcp_api.py`에서 도구 목록/호출을 검증하는 기존 테스트(예: `projectos_apply_graph_patch` 관련)를 찾아 동일한 호출 헬퍼/픽스처를 재사용한다. 아래는 두 가지를 검증: (1) 도구가 list에 등록됨, (2) dry-run 호출이 patch/summary를 반환.

```python
def test_reconcile_tool_is_registered():
    from app.mcp_tools import list_tools  # 기존 도구 목록 헬퍼 이름에 맞출 것
    names = {t["name"] for t in list_tools()}
    assert "projectos_reconcile_vault" in names


@pytest.mark.asyncio
async def test_reconcile_tool_dry_run(tmp_path, monkeypatch):
    import json
    import networkx as nx
    from app.config import config
    from app.mcp_tools import call_tool  # 기존 호출 헬퍼 이름에 맞출 것

    monkeypatch.setattr(config, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(config, "VAULT_DIR", str(tmp_path / "vault"))
    pid = "pMcp"
    g = nx.DiGraph()
    g.add_node("Skill:Python", type="Skill", name="Python", description="언어")
    pdir = tmp_path / "projects" / pid
    pdir.mkdir(parents=True)
    data = nx.node_link_data(g)
    if "edges" in data and "links" not in data:
        data["links"] = data.pop("edges")
    (pdir / "graph.json").write_text(json.dumps(data), encoding="utf-8")
    page = tmp_path / "vault" / pid / "Skills" / "Python.md"
    page.parent.mkdir(parents=True)
    page.write_text('---\ntype: Skill\nname: "Python"\n---\n\n## Overview\n새 설명\n',
                    encoding="utf-8")

    result = await call_tool("projectos_reconcile_vault", {"project_id": pid})
    # call_tool 반환 형태(structured content)는 기존 테스트와 동일하게 파싱
    assert result is not None
```

주의: `list_tools`/`call_tool`의 실제 함수 이름과 시그니처는 기존 `test_mcp_api.py`/`mcp_tools.py`를 보고 정확히 맞춘다. `_require_project`가 프로젝트 디렉터리 존재를 요구하므로 위에서 `projects/pMcp`를 생성했다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd src/backend && python3 -m pytest tests/test_api/test_mcp_api.py -v -k reconcile`
Expected: 도구 미등록으로 FAIL.

- [ ] **Step 3: 도구 등록 + 핸들러 구현**

`app/mcp_tools.py`의 `_tool("projectos_apply_graph_patch", ...)` 항목 바로 뒤(라인 ~191)에 추가:

```python
        _tool(
            "projectos_reconcile_vault",
            "Reconcile manual Obsidian vault edits back into the graph. "
            "Dry-run by default; pass apply=true to persist and rebuild the vault.",
            {
                "project_id": {"type": "string"},
                "apply": {"type": "boolean"},
            },
            ["project_id"],
        ),
```

핸들러 디스패치에서 `if name == "projectos_apply_graph_patch":` 블록(라인 ~604) 바로 뒤에 추가:

```python
        if name == "projectos_reconcile_vault":
            from app.services.vault_reconcile import reconcile_vault

            project_id = str(args["project_id"])
            _require_project(project_id)
            apply = bool(args.get("apply", False))
            result = reconcile_vault(project_id, apply=apply)
            return _text_result(json.dumps(result, ensure_ascii=False), result)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd src/backend && python3 -m pytest tests/test_api/test_mcp_api.py -v -k reconcile`
Expected: passed.

- [ ] **Step 5: 전체 테스트 회귀 확인 + 커밋**

```bash
cd src/backend && python3 -m pytest tests/ -q
```
Expected: 전체 그린 (기존 + 신규).

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS
git add src/backend/app/mcp_tools.py src/backend/tests/test_api/test_mcp_api.py
git commit -m "feat(reconcile): expose projectos_reconcile_vault MCP tool"
```

---

### Task 6: 핸드오프 문서 업데이트

**Files:**
- Modify: `docs/claude-code-handoff.md`

- [ ] **Step 1: 개선 #2 완료 내역 기록**

`docs/claude-code-handoff.md` 상단의 `## 2026-06-05 claude-obsidian 비교 개선 (진행 중)` 섹션에서 #2 항목을 완료로 표시하고, 다음을 포함: 신규 모듈 `app/services/vault_reconcile.py`, 엔드포인트 `POST /projects/{id}/reconcile`, MCP 도구 `projectos_reconcile_vault`, dry-run/apply 동작, render-aware diff 설계 요지, 테스트 결과(전체 pass 수), 다음 작업 후보(#3 hot cache).

- [ ] **Step 2: 커밋**

```bash
cd /raid/home/a202121010/workspace/projects/ProjectOS
git add docs/claude-code-handoff.md
git commit -m "docs: record vault-reconcile (#2) completion in handoff"
```

---

## Self-Review

- **Spec coverage:** parse_vault_page(파서) ✓ Task1, diff_vault_against_graph(render-aware differ, union/Category/demote 가드) ✓ Task2, reconcile_vault(dry-run/apply) ✓ Task3, API ✓ Task4, MCP ✓ Task5. 스펙 테스트 1–13 + 9b/9c 모두 매핑됨.
- **Placeholder scan:** 모든 코드 블록 완전. "기존 픽스처/헬퍼 이름에 맞출 것"은 placeholder가 아니라 실행자가 기존 테스트 규약을 따르라는 지시(테스트 인프라는 레포마다 다름).
- **Type consistency:** patch 키(nodes_add/nodes_update/nodes_delete/edges_add/edges_delete)는 graph_patch.apply_project_graph_patch가 읽는 키와 일치. edges는 source_name/target_name/relation/confidence — `_resolve_node`의 `source_`/`target_` prefix가 `source_name`/`target_name`을 resolve. nodes_update는 `{type,name,set:{description}}` — `_update_node`가 set 병합 지원. 일관됨.
- **비범위 준수:** rename/retype 미감지, 와처 미연동(YAGNI).
```
