import networkx as nx
import pytest

from app.agents.graph_builder_agent import GraphBuilderAgent
from app.models.graph import EdgeTypeDef, EntityTypeDef, Ontology, TextChunk


class _RecordingLLM:
    def __init__(self):
        self.prompts = []

    async def chat_json(self, messages, **kwargs):
        self.prompts.append(messages[0]["content"])
        return {"entities": [], "relations": []}


def _ontology():
    return Ontology(
        entity_types=[EntityTypeDef(name="Skill", description="")],
        edge_types=[EdgeTypeDef(name="USES_SKILL", description="")],
        analysis_summary="",
    )


def _chunk(source="clip.md"):
    return TextChunk(
        chunk_id="c1", text="NetworkX is used.", source_file=source,
        file_type="note", page_num=None, char_offset=0,
    )


@pytest.mark.asyncio
async def test_capture_context_injected_into_prompt():
    agent = GraphBuilderAgent()
    llm = _RecordingLLM()
    agent._llm = llm
    await agent.run(
        [_chunk("clip.md")],
        _ontology(),
        capture_context={"clip.md": {
            "capture_reason": "ref method",
            "current_focus": "thesis graph",
            "reflection_intent": "link methods",
        }},
    )
    assert any("Capture intent for this source" in p for p in llm.prompts)
    assert any("thesis graph" in p for p in llm.prompts)


@pytest.mark.asyncio
async def test_no_capture_context_leaves_prompt_clean():
    agent = GraphBuilderAgent()
    llm = _RecordingLLM()
    agent._llm = llm
    await agent.run([_chunk("clip.md")], _ontology())
    assert all("Capture intent for this source" not in p for p in llm.prompts)


def test_run_graph_capture_integration_contract(tmp_path, monkeypatch):
    # Simulate what _run_graph does: load captures, attach nodes to a built graph.
    from app.services.capture_context import (
        attach_capture_nodes,
        load_captures,
        save_capture,
    )
    pid = "rg-cap-1"
    save_capture(pid, "clip.md", {
        "capture_reason": "r", "current_focus": "focus", "reflection_intent": "i",
    })
    g = nx.DiGraph()
    g.add_node("s1", type="Skill", name="NetworkX", source_files=["clip.md"])
    captures = load_captures(pid)
    attach_capture_nodes(g, captures)
    assert g.nodes["capture::clip.md"]["type"] == "Capture"
    assert g.has_edge("capture::clip.md", "s1")
