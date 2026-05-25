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
