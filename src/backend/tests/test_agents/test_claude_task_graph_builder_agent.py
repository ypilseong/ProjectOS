from unittest.mock import AsyncMock

import pytest

from app.models.graph import EdgeTypeDef, EntityTypeDef, Ontology, TextChunk


@pytest.mark.asyncio
async def test_claude_task_graph_builder_extracts_graph_from_runner(tmp_path):
    from app.agents.claude_task_graph_builder_agent import ClaudeTaskGraphBuilderAgent

    runner = AsyncMock()
    runner.run_task = AsyncMock(return_value={
        "entities": [
            {"type": "Person", "name": "Yang Pilseong", "description": "researcher"},
            {"type": "Project", "name": "ProjectOS", "description": "knowledge graph system"},
            {"type": "Skill", "name": "Python", "description": "programming language"},
        ],
        "relations": [
            {
                "source": "Yang Pilseong",
                "source_type": "Person",
                "target": "ProjectOS",
                "target_type": "Project",
                "relation": "DEVELOPED",
                "confidence": 0.95,
            },
            {
                "source": "ProjectOS",
                "source_type": "Project",
                "target": "Python",
                "target_type": "Skill",
                "relation": "USES_SKILL",
                "confidence": 0.9,
            },
        ],
    })
    ontology = Ontology(
        entity_types=[
            EntityTypeDef("Person", ""),
            EntityTypeDef("Project", ""),
            EntityTypeDef("Skill", ""),
        ],
        edge_types=[
            EdgeTypeDef("DEVELOPED", ""),
            EdgeTypeDef("USES_SKILL", ""),
        ],
        analysis_summary="",
    )
    chunks = [TextChunk("c1", "ProjectOS uses Python", "profile.txt", "note", None, 0)]
    source = tmp_path / "profile.txt"
    source.write_text("ProjectOS uses Python", encoding="utf-8")

    agent = ClaudeTaskGraphBuilderAgent(runner=runner)
    graph = await agent.run(chunks, ontology, file_paths=[source])

    assert "Person:Yang Pilseong" in graph
    assert "Project:ProjectOS" in graph
    assert graph.has_edge("Person:Yang Pilseong", "Project:ProjectOS")
    assert graph.has_edge("Project:ProjectOS", "Skill:Python")

    task_input = runner.run_task.call_args.args[2]
    assert task_input["source_files"] == [str(source.resolve())]
    assert task_input["allowed_entity_types"] == ["Person", "Project", "Skill"]
