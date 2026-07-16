import networkx as nx

from app.services.capture_context import (
    attach_capture_nodes,
    is_complete_context,
    load_captures,
    save_capture,
)
from app.utils import graph_health
from app.utils.graph_restructure import is_meta_node


def test_is_complete_context():
    full = {
        "capture_reason": "r",
        "current_focus": "f",
        "reflection_intent": "i",
    }
    assert is_complete_context(full) is True
    assert is_complete_context({**full, "current_focus": "  "}) is False
    assert is_complete_context({"capture_reason": "r"}) is False
    assert is_complete_context(None) is False


def test_save_and_load_round_trip():
    pid = "cap-proj-1"
    assert load_captures(pid) == {}
    save_capture(pid, "clip.md", {
        "capture_reason": "useful method",
        "current_focus": "thesis ch3",
        "reflection_intent": "link to graph methods",
    })
    loaded = load_captures(pid)
    assert "clip.md" in loaded
    entry = loaded["clip.md"]
    assert entry["capture_reason"] == "useful method"
    assert entry["current_focus"] == "thesis ch3"
    assert entry["reflection_intent"] == "link to graph methods"
    from datetime import datetime
    assert datetime.fromisoformat(entry["captured_at"])  # valid ISO-8601


def test_save_capture_merges_multiple_sources():
    pid = "cap-proj-2"
    save_capture(pid, "a.md", {"capture_reason": "a", "current_focus": "a", "reflection_intent": "a"})
    save_capture(pid, "b.md", {"capture_reason": "b", "current_focus": "b", "reflection_intent": "b"})
    loaded = load_captures(pid)
    assert set(loaded.keys()) == {"a.md", "b.md"}


def test_is_meta_node():
    assert is_meta_node({"meta": True}) is True
    assert is_meta_node({"type": "Capture"}) is True
    assert is_meta_node({"type": "Category"}) is True
    assert is_meta_node({"type": "Skill"}) is False
    assert is_meta_node({}) is False


def test_attach_capture_nodes_links_source_entities():
    g = nx.DiGraph()
    g.add_node("n1", type="Skill", name="NetworkX", source_files=["clip.md"])
    g.add_node("n2", type="Project", name="Other", source_files=["other.md"])
    added = attach_capture_nodes(g, {
        "clip.md": {
            "capture_reason": "r", "current_focus": "graph work",
            "reflection_intent": "i", "captured_at": "2026-06-09T00:00:00+00:00",
        }
    })
    assert added == 1
    cap_id = "capture::clip.md"
    assert g.nodes[cap_id]["type"] == "Capture"
    assert g.nodes[cap_id]["meta"] is True
    assert g.has_edge(cap_id, "n1")
    assert g.edges[cap_id, "n1"]["relation"] == "DERIVED_FROM"
    assert not g.has_edge(cap_id, "n2")  # different source


def _graph_with_capture():
    g = nx.DiGraph()
    g.add_node("s1", type="Skill", name="NetworkX", source_files=["clip.md"])
    g.add_node("capture::clip.md", type="Capture", meta=True,
               name="focus", source_files=["clip.md"])
    g.add_edge("capture::clip.md", "s1", relation="DERIVED_FROM", meta=True)
    return g


def test_health_isolated_excludes_capture():
    g = _graph_with_capture()
    g.add_node("lonely", type="Skill", name="Lonely")
    isolated = graph_health.check_isolated_nodes(g)
    ids = {item["node_id"] for item in isolated}
    assert "lonely" in ids
    assert "capture::clip.md" not in ids


def test_obsidian_writer_skips_capture_page():
    from app.agents.obsidian_writer_agent import ObsidianWriterAgent
    agent = ObsidianWriterAgent()
    index_md = agent._render_index(_graph_with_capture())
    assert "NetworkX" in index_md
    assert "focus" not in index_md  # Capture node not listed
