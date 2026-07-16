import json

import networkx as nx

from app.config import config


def _write_graph(project_id: str):
    from pathlib import Path

    graph = nx.DiGraph()
    graph.add_node(
        "Person:Yang Pilseong",
        type="Person",
        name="Yang Pilseong",
        description="Researcher",
        source_files=["cv.pdf"],
        source_chunk_ids=["c1"],
        attributes={},
    )
    project_dir = Path(config.PROJECTS_DIR) / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "graph.json").write_text(
        json.dumps(nx.node_link_data(graph), ensure_ascii=False),
        encoding="utf-8",
    )


def test_apply_project_graph_patch_adds_node_edge_and_rebuilds_vault():
    from app.services.project_store import project_store
    from app.utils.graph_patch import apply_project_graph_patch

    project = project_store.create(name="Patch", description="")
    _write_graph(project.project_id)

    result = apply_project_graph_patch(
        project.project_id,
        {
            "nodes_add": [
                {
                    "type": "Skill",
                    "name": "Graph RAG",
                    "description": "Graph retrieval augmented generation",
                }
            ],
            "edges_add": [
                {
                    "source_type": "Person",
                    "source_name": "Yang Pilseong",
                    "target_type": "Skill",
                    "target_name": "Graph RAG",
                    "relation": "USES_SKILL",
                    "confidence": 0.8,
                }
            ],
        },
    )

    assert result["changes"]["nodes_added"] == 1
    assert result["changes"]["edges_added"] == 1

    graph_data = json.loads((config_path("PROJECTS_DIR") / project.project_id / "graph.json").read_text())
    if "links" in graph_data and "edges" not in graph_data:
        graph_data["edges"] = graph_data.pop("links")
    graph = nx.node_link_graph(graph_data)
    assert "Skill:Graph RAG" in graph
    assert graph.has_edge("Person:Yang Pilseong", "Skill:Graph RAG")

    index = config_path("VAULT_DIR") / project.project_id / "_index.md"
    assert "Graph RAG" in index.read_text(encoding="utf-8")


def test_apply_project_graph_patch_accepts_source_target_aliases():
    from app.services.project_store import project_store
    from app.utils.graph_patch import apply_project_graph_patch

    project = project_store.create(name="Patch Aliases", description="")
    _write_graph(project.project_id)

    result = apply_project_graph_patch(
        project.project_id,
        {
            "nodes_add": [
                {"type": "Project", "name": "ProjectOS", "description": "System"}
            ],
            "edges_add": [
                {
                    "source": "Yang Pilseong",
                    "target": "ProjectOS",
                    "relation": "DEVELOPED",
                }
            ],
        },
    )

    assert result["changes"]["edges_added"] == 1
    graph_data = json.loads((config_path("PROJECTS_DIR") / project.project_id / "graph.json").read_text())
    if "links" in graph_data and "edges" not in graph_data:
        graph_data["edges"] = graph_data.pop("links")
    graph = nx.node_link_graph(graph_data)
    assert graph.has_edge("Person:Yang Pilseong", "Project:ProjectOS")


def test_apply_project_graph_patch_updates_and_deletes():
    from app.services.project_store import project_store
    from app.utils.graph_patch import apply_project_graph_patch

    project = project_store.create(name="Patch Update", description="")
    _write_graph(project.project_id)

    result = apply_project_graph_patch(
        project.project_id,
        {
            "nodes_update": [
                {
                    "type": "Person",
                    "name": "Yang Pilseong",
                    "set": {"description": "Reviewed researcher"},
                }
            ],
            "nodes_delete": [
                {"type": "Person", "name": "Yang Pilseong"}
            ],
        },
    )

    assert result["changes"]["nodes_updated"] == 1
    assert result["changes"]["nodes_deleted"] == 1
    graph_data = json.loads((config_path("PROJECTS_DIR") / project.project_id / "graph.json").read_text())
    if "links" in graph_data and "edges" not in graph_data:
        graph_data["edges"] = graph_data.pop("links")
    graph = nx.node_link_graph(graph_data)
    assert graph.number_of_nodes() == 0


def test_apply_project_graph_patch_rejects_invalid_node():
    import pytest
    from app.services.project_store import project_store
    from app.utils.graph_patch import apply_project_graph_patch

    project = project_store.create(name="Patch Invalid", description="")
    _write_graph(project.project_id)

    with pytest.raises(ValueError, match="Invalid entity"):
        apply_project_graph_patch(
            project.project_id,
            {"nodes_add": [{"type": "Person", "name": "저"}]},
        )


def config_path(name: str):
    from pathlib import Path

    return Path(getattr(config, name))
