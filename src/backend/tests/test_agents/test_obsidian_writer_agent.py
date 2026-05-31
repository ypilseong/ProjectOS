import pytest
import networkx as nx
from pathlib import Path
from app.models.graph import CareerProfile


@pytest.fixture
def sample_graph():
    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong",
               description="ML 연구자", source_files=["cv.pdf"], attributes={})
    g.add_node("Skill:Python", type="Skill", name="Python",
               description="프로그래밍 언어", source_files=["cv.pdf"], attributes={})
    g.add_node("Project:ProjectOS", type="Project", name="ProjectOS",
               description="지식 그래프", source_files=["readme.md"], attributes={})
    g.add_edge("Person:Yang Pilseong", "Skill:Python", relation="USES_SKILL")
    g.add_edge("Person:Yang Pilseong", "Project:ProjectOS", relation="DEVELOPED")
    return g


@pytest.fixture
def sample_profile():
    return CareerProfile(
        name="Yang Pilseong",
        expertise=["ML"],
        skills=["Python"],
        projects=["ProjectOS"],
        organizations=[],
        publications=[],
        achievements=[],
        persona_summary="ML 연구자입니다.",
        timeline=[{"year": 2020, "event": "KAIST 입학"}],
    )


def test_writer_creates_node_files(tmp_path, sample_graph, sample_profile):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent
    writer = ObsidianWriterAgent()
    writer.run(sample_graph, [sample_profile], vault_path=str(tmp_path))

    assert (tmp_path / "Career" / "Yang Pilseong.md").exists()
    assert (tmp_path / "Skills" / "Python.md").exists()
    assert (tmp_path / "Projects" / "ProjectOS.md").exists()


def test_writer_build_payload_contains_vault_files(sample_graph, sample_profile):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent

    writer = ObsidianWriterAgent()
    payload = writer.build_payload(sample_graph, [sample_profile], project_id="proj1")

    assert len(payload.notes) == 3
    assert any(n.folder == "Career" and n.filename == "Yang Pilseong.md" for n in payload.notes)
    assert payload.canvas.filename == "_index.canvas"
    assert '"nodes"' in payload.canvas.content
    assert payload.index.filename == "_index.md"
    assert "## Skill" in payload.index.content
    assert "Project: proj1" in payload.log_entry


def test_writer_write_payload_creates_same_key_files(tmp_path, sample_graph, sample_profile):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent

    writer = ObsidianWriterAgent()
    payload = writer.build_payload(sample_graph, [sample_profile], project_id="proj1")
    writer.write_payload(payload, vault_path=str(tmp_path))

    assert (tmp_path / "Career" / "Yang Pilseong.md").exists()
    assert (tmp_path / "Skills" / "Python.md").exists()
    assert (tmp_path / "Projects" / "ProjectOS.md").exists()
    assert (tmp_path / "_index.canvas").exists()
    assert (tmp_path / "_index.md").exists()
    assert (tmp_path / "log.md").exists()


def test_writer_creates_obsidian_config(tmp_path, sample_graph, sample_profile):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent
    writer = ObsidianWriterAgent()
    writer.run(sample_graph, [sample_profile], vault_path=str(tmp_path))

    assert (tmp_path / ".obsidian").exists()
    assert (tmp_path / ".obsidian" / "app.json").exists()
    assert (tmp_path / ".obsidian" / "graph.json").exists()


def test_note_has_frontmatter(tmp_path, sample_graph, sample_profile):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent
    writer = ObsidianWriterAgent()
    writer.run(sample_graph, [sample_profile], vault_path=str(tmp_path))

    content = (tmp_path / "Career" / "Yang Pilseong.md").read_text()
    assert content.startswith("---")
    assert "type: Person" in content
    assert 'name: "Yang Pilseong"' in content


def test_note_has_source_provenance_section(tmp_path, sample_graph):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent

    sample_graph.nodes["Person:Yang Pilseong"]["source_chunk_ids"] = ["chunk-1"]
    writer = ObsidianWriterAgent()
    writer.run(sample_graph, vault_path=str(tmp_path))

    content = (tmp_path / "Career" / "Yang Pilseong.md").read_text()
    assert "## Sources" in content
    assert "cv.pdf" in content
    assert "chunk-1" in content


def test_note_has_wikilinks(tmp_path, sample_graph, sample_profile):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent
    writer = ObsidianWriterAgent()
    writer.run(sample_graph, [sample_profile], vault_path=str(tmp_path))

    content = (tmp_path / "Career" / "Yang Pilseong.md").read_text()
    assert "[[Python]]" in content or "[[ProjectOS]]" in content


def test_canvas_file_created(tmp_path, sample_graph, sample_profile):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent
    writer = ObsidianWriterAgent()
    writer.run(sample_graph, [sample_profile], vault_path=str(tmp_path))

    canvas_path = tmp_path / "_index.canvas"
    assert canvas_path.exists()
    import json
    canvas = json.loads(canvas_path.read_text())
    assert "nodes" in canvas
    assert "edges" in canvas
    assert len(canvas["nodes"]) == 3


def test_delta_mode_preserves_existing(tmp_path, sample_graph, sample_profile):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent
    writer = ObsidianWriterAgent()
    writer.run(sample_graph, [sample_profile], vault_path=str(tmp_path))

    # Add custom content to existing note
    note_path = tmp_path / "Career" / "Yang Pilseong.md"
    original = note_path.read_text()
    note_path.write_text(original + "\n## Custom Notes\nMy custom content")

    # Re-run in delta mode — should not overwrite custom content
    writer.run(sample_graph, [sample_profile], vault_path=str(tmp_path), delta=True)
    updated = note_path.read_text()
    assert "My custom content" in updated


def test_full_build_removes_stale_generated_notes(tmp_path, sample_graph):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent

    writer = ObsidianWriterAgent()
    writer.run(sample_graph, vault_path=str(tmp_path))

    stale = tmp_path / "Skills" / "Old Skill.md"
    stale.write_text("# Old Skill", encoding="utf-8")

    writer.run(sample_graph, vault_path=str(tmp_path), delta=False)

    assert not stale.exists()
    assert (tmp_path / "Skills" / "Python.md").exists()


def test_delta_build_keeps_stale_generated_notes(tmp_path, sample_graph):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent

    writer = ObsidianWriterAgent()
    writer.run(sample_graph, vault_path=str(tmp_path))

    stale = tmp_path / "Skills" / "Old Skill.md"
    stale.write_text("# Old Skill", encoding="utf-8")

    writer.run(sample_graph, vault_path=str(tmp_path), delta=True)

    assert stale.exists()


def test_writer_skips_category_notes(tmp_path, sample_graph):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent
    sample_graph.add_node("Category:Skills", type="Category", name="Skills", source_files=[])
    sample_graph.add_edge("Person:Yang Pilseong", "Category:Skills", relation="HAS")

    writer = ObsidianWriterAgent()
    writer.run(sample_graph, vault_path=str(tmp_path))

    assert not (tmp_path / "Misc" / "Skills.md").exists()


def test_person_note_expands_category_hub_links_for_obsidian_graph(tmp_path):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent

    g = nx.DiGraph()
    g.add_node("Person:Yang Pilseong", type="Person", name="Yang Pilseong")
    g.add_node("Category:Skills", type="Category", name="Skills")
    g.add_node("Skill:Python", type="Skill", name="Python")
    g.add_edge("Person:Yang Pilseong", "Category:Skills", relation="HAS")
    g.add_edge("Category:Skills", "Skill:Python", relation="INCLUDES")

    writer = ObsidianWriterAgent()
    writer.run(g, vault_path=str(tmp_path))

    content = (tmp_path / "Career" / "Yang Pilseong.md").read_text(encoding="utf-8")
    assert "HAS: [[Skills]]" in content
    assert "Skills: [[Python]]" in content


def test_canvas_makes_person_nodes_larger(tmp_path, sample_graph):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent

    writer = ObsidianWriterAgent()
    writer.run(sample_graph, vault_path=str(tmp_path))

    import json

    canvas = json.loads((tmp_path / "_index.canvas").read_text(encoding="utf-8"))
    person = next(node for node in canvas["nodes"] if node["text"] == "Yang Pilseong")
    skill = next(node for node in canvas["nodes"] if node["text"] == "Python")

    assert person["width"] > skill["width"]
    assert person["height"] > skill["height"]


def test_writer_appends_log_file(tmp_path, sample_graph):
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent

    writer = ObsidianWriterAgent()
    writer.run(sample_graph, vault_path=str(tmp_path), project_id="proj1")
    first = (tmp_path / "log.md").read_text(encoding="utf-8")
    writer.run(sample_graph, vault_path=str(tmp_path), delta=True)
    second = (tmp_path / "log.md").read_text(encoding="utf-8")

    assert first.startswith("# ProjectOS Log")
    assert "graph build" in first
    assert "Project: proj1" in first
    assert "Nodes: 3" in first
    assert "Edges: 2" in first
    assert "cv.pdf" in first
    assert "graph delta" in second
    assert len(second) > len(first)
