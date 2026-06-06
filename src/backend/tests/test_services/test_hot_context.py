import networkx as nx

from app.services.hot_context import compose_hot_context


def _graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("p1", type="Person", name="Alice", description="A researcher in ML and graphs.")
    g.add_node("p2", type="Person", name="Bob", description="Engineer")
    g.add_node("pr1", type="Project", name="ProjectOS")
    g.add_node("pr2", type="Project", name="MiroFish")
    g.add_node("s1", type="Skill", name="Python")
    g.add_node("s2", type="Skill", name="NetworkX")
    g.add_node("iso", type="Skill", name="Rust")
    g.add_node("cat", type="Category", name="Skills")
    # Alice is the top hub: 4 edges
    g.add_edge("p1", "pr1", relation="DEVELOPED")
    g.add_edge("p1", "pr2", relation="DEVELOPED")
    g.add_edge("p1", "s1", relation="USES_SKILL")
    g.add_edge("p1", "s2", relation="USES_SKILL")
    # Bob: 1 edge
    g.add_edge("p2", "pr1", relation="DEVELOPED")
    # ProjectOS gets extra edges to be top Project hub
    g.add_edge("pr1", "s1", relation="USES_SKILL")
    return g


def test_persona_top_person_by_degree():
    ctx = compose_hot_context(_graph(), project_id="proj", top_n=5)
    persona = ctx["persona"]
    assert persona[0]["name"] == "Alice"
    assert persona[0]["type"] == "Person"
    assert persona[0]["degree"] >= persona[1]["degree"]
    assert persona[0]["description"].startswith("A researcher")
    assert all(p["type"] == "Person" for p in persona)


def test_persona_respects_top_n():
    ctx = compose_hot_context(_graph(), top_n=1)
    assert len(ctx["persona"]) == 1


def test_hubs_by_type_excludes_person_and_category():
    ctx = compose_hot_context(_graph(), top_n=5)
    hubs = ctx["hubs_by_type"]
    assert "Person" not in hubs
    assert "Category" not in hubs
    assert hubs["Project"][0]["name"] == "ProjectOS"
    assert all("degree" in h for h in hubs["Project"])


def test_gaps_isolated_named_nodes_sorted():
    ctx = compose_hot_context(_graph(), top_n=5)
    names = [g["name"] for g in ctx["gaps"]]
    assert "Rust" in names
    assert names == sorted(names)
    # connected nodes never appear
    assert "Alice" not in names


def test_recent_activity_headers_only():
    log = [
        "# ProjectOS Log",
        "",
        "## 2026-06-01 graph build",
        "- Nodes: 5",
        "## 2026-06-05 graph delta",
        "- Nodes: 7",
    ]
    ctx = compose_hot_context(_graph(), recent_log=log, recent_n=5)
    assert ctx["recent_activity"] == [
        "## 2026-06-01 graph build",
        "## 2026-06-05 graph delta",
    ]


def test_recent_activity_respects_recent_n():
    log = [f"## 2026-06-0{i} graph build" for i in range(1, 6)]
    ctx = compose_hot_context(_graph(), recent_log=log, recent_n=2)
    assert ctx["recent_activity"] == [
        "## 2026-06-04 graph build",
        "## 2026-06-05 graph build",
    ]


def test_stats_excludes_category():
    ctx = compose_hot_context(_graph())
    stats = ctx["stats"]
    assert "Category" not in stats["by_type"]
    assert stats["by_type"]["Person"] == 2
    assert stats["by_type"]["Project"] == 2
    assert stats["total_nodes"] == 7  # 8 nodes minus 1 Category


def test_empty_graph():
    ctx = compose_hot_context(nx.DiGraph(), project_id="empty")
    assert ctx["persona"] == []
    assert ctx["hubs_by_type"] == {}
    assert ctx["gaps"] == []
    assert ctx["recent_activity"] == []
    assert ctx["stats"]["total_nodes"] == 0
