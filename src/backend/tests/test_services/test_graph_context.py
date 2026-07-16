import copy

import networkx as nx
from networkx.readwrite import json_graph

from app.services.graph_context import (
    get_node_context,
    get_subgraph_context,
    summarize_graph_context,
)


def _graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("Project:ProjectOS", type="Project", name="ProjectOS", source_files=["project.md"])
    graph.add_node("Skill:Python", type="Skill", name="Python", source_files=["python.md"])
    graph.add_node("Skill:Graph", type="Skill", name="Graph", source_files=["graph.md", "project.md"])
    graph.add_node("Person:Alice", type="Person", name="Alice", source_files=["alice.md"])
    graph.add_node("Person:Alice-2", type="Person", name="Alice", source_files=["alice-alt.md"])
    graph.add_node("Org:OpenAI", type="Org", name="OpenAI", source_files=[])
    graph.add_edge("Project:ProjectOS", "Skill:Python", relation="USES_SKILL")
    graph.add_edge("Project:ProjectOS", "Skill:Graph", relation="USES_SKILL")
    graph.add_edge("Person:Alice", "Project:ProjectOS", relation="CONTRIBUTES_TO")
    graph.add_edge("Person:Alice-2", "Project:ProjectOS", relation="CONTRIBUTES_TO")
    graph.add_edge("Project:ProjectOS", "Org:OpenAI", relation="RELATED_TO")
    return graph


def test_summarize_graph_context_is_compact_read_only_and_deterministic():
    graph = _graph()
    before = copy.deepcopy(json_graph.node_link_data(graph))

    first = summarize_graph_context(graph, max_hubs=2)
    second = summarize_graph_context(graph, max_hubs=2)

    assert first == second
    assert json_graph.node_link_data(graph) == before
    assert first["read_only"] is True
    assert first["counts"]["nodes"] == 6
    assert first["counts"]["edges"] == 5
    assert first["counts"]["types"] == {"Org": 1, "Person": 2, "Project": 1, "Skill": 2}
    assert first["counts"]["relations"] == {
        "CONTRIBUTES_TO": 2,
        "RELATED_TO": 1,
        "USES_SKILL": 2,
    }
    assert first["limits"] == {"max_hubs": 2}
    assert [hub["id"] for hub in first["hubs"]] == ["Project:ProjectOS", "Person:Alice"]
    assert first["hubs"][0]["source_files"] == ["project.md"]


def test_get_node_context_matches_name_and_type_with_in_out_relations():
    payload = get_node_context(_graph(), "ProjectOS", node_type="Project", max_neighbors=3)

    assert payload["read_only"] is True
    assert payload["query"] == {"name": "ProjectOS", "type": "Project"}
    assert payload["match"] == {
        "count": 1,
        "selected_id": "Project:ProjectOS",
        "ambiguous": False,
        "ids": ["Project:ProjectOS"],
    }
    assert payload["counts"] == {"in_edges": 2, "out_edges": 3, "neighbors": 5}
    assert payload["node"]["source_files"] == ["project.md"]
    assert [edge["relation"] for edge in payload["edges"]["in"]] == ["CONTRIBUTES_TO", "CONTRIBUTES_TO"]
    assert [edge["from"] for edge in payload["edges"]["in"]] == ["Person:Alice", "Person:Alice-2"]
    assert [edge["relation"] for edge in payload["edges"]["out"]] == ["RELATED_TO"]
    assert payload["edges"]["out"][0]["to"] == "Org:OpenAI"


def test_get_node_context_reports_ambiguous_matches_and_selects_deterministically():
    payload = get_node_context(_graph(), "Alice")

    assert payload["match"]["count"] == 2
    assert payload["match"]["ambiguous"] is True
    assert payload["match"]["ids"] == ["Person:Alice", "Person:Alice-2"]
    assert payload["match"]["selected_id"] == "Person:Alice"
    assert payload["node"]["source_files"] == ["alice.md"]


def test_get_node_context_can_match_by_node_id_and_report_missing():
    by_id = get_node_context(_graph(), "Skill:Python")
    missing = get_node_context(_graph(), "Python", node_type="Project")

    assert by_id["match"]["selected_id"] == "Skill:Python"
    assert by_id["node"]["name"] == "Python"
    assert missing["match"]["count"] == 0
    assert missing["node"] is None
    assert missing["edges"] == {"in": [], "out": []}


def test_get_subgraph_context_limits_depth_and_nodes_with_directed_edges():
    payload = get_subgraph_context(_graph(), "ProjectOS", node_type="Project", depth=1, max_nodes=4)

    assert payload["read_only"] is True
    assert payload["limits"] == {"depth": 1, "max_nodes": 4}
    assert payload["counts"] == {"nodes": 4, "edges": 3, "reachable_nodes": 6}
    assert [node["id"] for node in payload["nodes"]] == [
        "Project:ProjectOS",
        "Org:OpenAI",
        "Person:Alice",
        "Person:Alice-2",
    ]
    assert payload["nodes"][0]["distance"] == 0
    assert payload["edges"] == [
        {
            "source": "Person:Alice",
            "target": "Project:ProjectOS",
            "relation": "CONTRIBUTES_TO",
        },
        {
            "source": "Person:Alice-2",
            "target": "Project:ProjectOS",
            "relation": "CONTRIBUTES_TO",
        },
        {
            "source": "Project:ProjectOS",
            "target": "Org:OpenAI",
            "relation": "RELATED_TO",
        },
    ]


def test_get_subgraph_context_depth_zero_returns_only_selected_node():
    payload = get_subgraph_context(_graph(), "ProjectOS", node_type="Project", depth=0)

    assert payload["counts"] == {"nodes": 1, "edges": 0, "reachable_nodes": 1}
    assert [node["id"] for node in payload["nodes"]] == ["Project:ProjectOS"]
    assert payload["edges"] == []


def test_get_node_context_includes_pre_fetched_evidence_when_provided():
    evidence = [
        {"label": "[cv.pdf#c1 p.1 char:0]", "text": "ProjectOS builds a graph."},
        {"label": "[readme.md#c2 p.1 char:0]", "text": "ProjectOS syncs to Obsidian."},
    ]
    payload = get_node_context(
        _graph(), "ProjectOS", node_type="Project", max_neighbors=3, evidence=evidence
    )
    assert payload["evidence"] == evidence
    # evidence must stay OUT of counts (strict-equality consumers depend on counts shape)
    assert "evidence" not in payload["counts"]


def test_get_node_context_omits_evidence_key_when_not_provided():
    payload = get_node_context(_graph(), "ProjectOS", node_type="Project", max_neighbors=3)
    assert "evidence" not in payload


def test_get_node_context_includes_empty_evidence_list_when_explicitly_empty():
    payload = get_node_context(
        _graph(), "ProjectOS", node_type="Project", max_neighbors=3, evidence=[]
    )
    assert payload["evidence"] == []
