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


import json

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
