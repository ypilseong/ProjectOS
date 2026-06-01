import networkx as nx
import pytest

from app.utils.graph_restructure import (
    add_category_hubs,
    build_entity_details,
    demote_project_context_nodes,
)


def _make_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("Person:양필성", type="Person", name="양필성", source_files=[])
    g.add_node("Skill:NLP",    type="Skill",   name="NLP",    source_files=[])
    g.add_node("Skill:Python", type="Skill",   name="Python", source_files=[])
    g.add_node("Project:화자인식", type="Project", name="화자인식", source_files=[])
    g.add_node("Achievement:GPA", type="Achievement", name="GPA", source_files=[])
    g.add_edge("Person:양필성", "Skill:NLP",     relation="USES_SKILL")
    g.add_edge("Person:양필성", "Skill:Python",  relation="USES_SKILL")
    g.add_edge("Person:양필성", "Project:화자인식", relation="PARTICIPATED_IN")
    g.add_edge("Person:양필성", "Achievement:GPA", relation="ACHIEVED")
    return g


def test_hub_nodes_created():
    g, hubs = add_category_hubs(_make_graph())
    assert hubs == 3  # Skills, Projects, Achievements
    assert "Category:Skills" in g
    assert "Category:Projects" in g
    assert "Category:Achievements" in g


def test_person_connects_to_hubs_not_individuals():
    g, _ = add_category_hubs(_make_graph())
    person_neighbors = list(g.successors("Person:양필성"))
    assert "Category:Skills" in person_neighbors
    assert "Category:Projects" in person_neighbors
    assert "Skill:NLP" not in person_neighbors
    assert "Skill:Python" not in person_neighbors
    assert "Project:화자인식" not in person_neighbors


def test_hubs_connect_to_individuals():
    g, _ = add_category_hubs(_make_graph())
    skill_hub_neighbors = list(g.successors("Category:Skills"))
    assert "Skill:NLP" in skill_hub_neighbors
    assert "Skill:Python" in skill_hub_neighbors
    assert list(g.successors("Category:Projects")) == ["Project:화자인식"]


def test_original_relation_preserved_on_hub_to_individual():
    g, _ = add_category_hubs(_make_graph())
    assert g.edges["Category:Skills", "Skill:NLP"]["relation"] == "USES_SKILL"
    assert g.edges["Category:Achievements", "Achievement:GPA"]["relation"] == "ACHIEVED"


def test_person_to_hub_relation_is_has():
    g, _ = add_category_hubs(_make_graph())
    assert g.edges["Person:양필성", "Category:Skills"]["relation"] == "HAS"


def test_cross_type_edges_preserved():
    g = _make_graph()
    g.add_edge("Skill:NLP", "Project:화자인식", relation="USED_IN")
    g, _ = add_category_hubs(g)
    assert g.has_edge("Skill:NLP", "Project:화자인식")


def test_other_persons_grouped_under_people_hub(tmp_path, monkeypatch):
    user_json = tmp_path / "user.json"
    user_json.write_text('{"name": "양필성", "display_name": "Pilseong Yang"}')
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    g = _make_graph()
    g.add_node("Person:인소영", type="Person", name="인소영", source_files=[])
    g.add_edge("Person:양필성", "Person:인소영", relation="COLLABORATED_WITH")
    g, hubs = add_category_hubs(g)

    assert "Category:People" in g
    assert g.has_edge("Person:양필성", "Category:People")
    assert g.has_edge("Category:People", "Person:인소영")
    assert not g.has_edge("Person:양필성", "Person:인소영")


def test_user_person_stays_as_center(tmp_path, monkeypatch):
    user_json = tmp_path / "user.json"
    user_json.write_text('{"name": "양필성", "display_name": "Pilseong Yang"}')
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    g = _make_graph()
    g, _ = add_category_hubs(g)
    # 양필성 노드는 허브로 묶이지 않고 그대로 존재
    assert "Person:양필성" in g


def test_alias_person_stays_as_center(tmp_path, monkeypatch):
    user_json = tmp_path / "user.json"
    user_json.write_text('{"name": "양필성", "display_name": "Pilseong Yang", "aliases": ["Phil"]}')
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    g = nx.DiGraph()
    g.add_node("Person:Phil", type="Person", name="Phil", source_files=[])
    g.add_node("Skill:NLP", type="Skill", name="NLP", source_files=[])
    g.add_edge("Person:Phil", "Skill:NLP", relation="USES_SKILL")
    g, _ = add_category_hubs(g)

    assert g.has_edge("Person:Phil", "Category:Skills")


def test_idempotent_hub_creation(tmp_path, monkeypatch):
    user_json = tmp_path / "user.json"
    user_json.write_text('{"name": "양필성", "display_name": "Pilseong Yang"}')
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    g = _make_graph()
    g, hubs1 = add_category_hubs(g)
    g, hubs2 = add_category_hubs(g)
    assert hubs2 == 0


def test_semantic_project_skill_is_promoted_under_skill_hub(tmp_path, monkeypatch):
    user_json = tmp_path / "user.json"
    user_json.write_text('{"name": "양필성", "display_name": "Pilseong Yang"}')
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    g = nx.DiGraph()
    g.add_node("Person:양필성", type="Person", name="양필성", source_files=[])
    g.add_node("Project:ProjectOS", type="Project", name="ProjectOS", source_files=[])
    g.add_node("Skill:FastAPI", type="Skill", name="FastAPI", source_files=[])
    g.add_edge("Person:양필성", "Project:ProjectOS", relation="DEVELOPED")
    g.add_edge("Project:ProjectOS", "Skill:FastAPI", relation="USES_SKILL")

    g, _ = add_category_hubs(g)

    assert g.has_edge("Person:양필성", "Category:Projects")
    assert g.has_edge("Category:Projects", "Project:ProjectOS")
    assert g.has_edge("Person:양필성", "Category:Skills")
    assert g.has_edge("Category:Skills", "Skill:FastAPI")
    assert g.has_edge("Project:ProjectOS", "Skill:FastAPI")


def test_project_context_leaf_is_demoted_to_project_detail():
    g = nx.DiGraph()
    g.add_node("Project:ProjectOS", type="Project", name="ProjectOS", source_files=["readme.md"])
    g.add_node(
        "Skill:graph JSON generation",
        type="Skill",
        name="graph JSON generation",
        source_files=["readme.md"],
        source_chunk_ids=["c1"],
    )
    g.add_edge("Project:ProjectOS", "Skill:graph JSON generation", relation="USES_SKILL")

    g, demoted = demote_project_context_nodes(g)
    g, _ = build_entity_details(g)

    assert demoted == 1
    assert "Skill:graph JSON generation" not in g
    detail = g.nodes["Project:ProjectOS"]["details"]
    features = next(s for s in detail["sections"] if s["title"] == "주요 기능")
    assert "graph JSON generation" in features["items"]


def test_project_context_phrase_promotes_embedded_skill():
    g = nx.DiGraph()
    g.add_node("Project:ProjectOS", type="Project", name="ProjectOS", source_files=["readme.md"])
    g.add_node(
        "Skill:FastAPI backend architecture",
        type="Skill",
        name="FastAPI backend architecture",
        source_files=["readme.md"],
        source_chunk_ids=["c1"],
    )
    g.add_edge("Project:ProjectOS", "Skill:FastAPI backend architecture", relation="USES_SKILL")

    g, demoted = demote_project_context_nodes(g)

    assert demoted == 1
    assert "Skill:FastAPI backend architecture" not in g
    assert "Skill:FastAPI" in g
    assert g.has_edge("Project:ProjectOS", "Skill:FastAPI")


def test_build_entity_details_uses_type_specific_sections(tmp_path, monkeypatch):
    user_json = tmp_path / "user.json"
    user_json.write_text('{"name": "양필성", "display_name": "Pilseong Yang"}')
    monkeypatch.setattr("app.config.config.USER_CONFIG_PATH", str(user_json))

    g = nx.DiGraph()
    g.add_node("Person:양필성", type="Person", name="양필성", source_files=["cv.pdf"])
    g.add_node("Project:ProjectOS", type="Project", name="ProjectOS", source_files=["readme.md"])
    g.add_node("Skill:FastAPI", type="Skill", name="FastAPI", source_files=["readme.md"])
    g.add_edge("Person:양필성", "Project:ProjectOS", relation="DEVELOPED")
    g.add_edge("Project:ProjectOS", "Skill:FastAPI", relation="USES_SKILL")

    g, _ = add_category_hubs(g)
    g, changed = build_entity_details(g)

    assert changed == 3
    project_sections = {
        section["title"]: section["items"]
        for section in g.nodes["Project:ProjectOS"]["details"]["sections"]
    }
    person_sections = {
        section["title"]: section["items"]
        for section in g.nodes["Person:양필성"]["details"]["sections"]
    }
    assert any("FastAPI" in item for item in project_sections["사용 기술"])
    assert any("ProjectOS" in item for item in person_sections["관련 프로젝트"])


def test_build_entity_details_source_section_uses_file_names_only():
    g = nx.DiGraph()
    g.add_node(
        "Project:ProjectOS",
        type="Project",
        name="ProjectOS",
        source_files=["readme.md"],
        source_chunk_ids=["chunk-1"],
        context_items=[
            {
                "name": "graph JSON generation",
                "source_files": ["readme.md"],
                "source_chunk_ids": ["chunk-2"],
            }
        ],
    )

    g, _ = build_entity_details(g)

    sections = {
        section["title"]: section["items"]
        for section in g.nodes["Project:ProjectOS"]["details"]["sections"]
    }
    rendered_sources = "\n".join(sections["근거 source"])
    assert "readme.md" in rendered_sources
    assert "chunk-1" not in rendered_sources
    assert "chunk-2" not in rendered_sources
    assert "Chunks:" not in rendered_sources
    assert "Files:" not in rendered_sources
