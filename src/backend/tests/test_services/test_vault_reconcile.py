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


from app.services.vault_reconcile import reconcile_vault


def _load_graph_for_test(path: Path) -> nx.DiGraph:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    return nx.node_link_graph(data)


def test_reconcile_dry_run_does_not_mutate_graph(reconcile_env):
    pid, vault, _ = reconcile_env
    _page(vault, "Skills", "Python", "Skill", "변경된 설명")
    graph_path = Path(config.PROJECTS_DIR) / pid / "graph.json"
    before = graph_path.read_text(encoding="utf-8")
    out = reconcile_vault(pid, apply=False)
    assert out["applied"] is False
    assert out["summary"]["nodes_update"] >= 1
    assert "patch" in out
    assert graph_path.read_text(encoding="utf-8") == before


def test_reconcile_apply_persists_description_change(reconcile_env):
    pid, vault, _ = reconcile_env
    _page(vault, "Skills", "Python", "Skill", "변경된 설명")
    _page(vault, "Projects", "OS", "Project", "graph builder",
          "- USES_SKILL: [[Python]]\n")
    out = reconcile_vault(pid, apply=True)
    assert out["applied"] is True
    g = _load_graph_for_test(Path(config.PROJECTS_DIR) / pid / "graph.json")
    assert g.nodes["Skill:Python"]["description"] == "변경된 설명"
