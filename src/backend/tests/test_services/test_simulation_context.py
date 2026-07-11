import json
from pathlib import Path

import networkx as nx
import pytest

from app.config import config
from app.services.simulation_context import (
    adapt_simulation_event_log,
    adapt_simulation_graph_delta,
    adapt_simulation_report_section,
    adapt_simulation_summary,
    load_simulation_result,
    resolve_simulation_evidence,
    _resolve_ref,
)


def _v2_result() -> dict:
    return {
        "schema_version": "2.0",
        "project_id": "p1",
        "run_id": "sim_1",
        "query": "Improve CV",
        "status": "completed",
        "started_at": "2026-06-08T00:00:00+00:00",
        "completed_at": "2026-06-08T00:01:00+00:00",
        "summary": {
            "title": "Simulation Report",
            "answer": "ok",
            "graph_delta_count": 3,
            "report_section_count": 2,
            "low_confidence_count": 1,
        },
        "workflow_steps": [
            {"id": "load_context", "label": "Load Context", "status": "completed", "summary": "Loaded."},
            {"id": "debate", "label": "Debate", "status": "completed", "summary": "Debated."},
        ],
        "event_log": [
            {
                "event_id": "evt_001",
                "step_id": "debate",
                "type": "debate_turn",
                "timestamp": "2026-06-08T00:00:30+00:00",
                "summary": "Turn one.",
                "payload_ref": {"kind": "debate", "ids": ["turn_001"]},
            },
            {
                "event_id": "evt_002",
                "step_id": "graph_delta_draft",
                "type": "graph_delta_proposed",
                "timestamp": "2026-06-08T00:00:40+00:00",
                "summary": "Delta proposed.",
                "payload_ref": {"kind": "graph_delta", "ids": ["delta_edge_001"]},
            },
        ],
        "personas": [{"id": "agent_1"}],
        "debate": {"turns": [{"turn_id": "turn_001"}]},
        "graph_delta": {
            "nodes": [
                {
                    "delta_id": "delta_node_001",
                    "operation": "add",
                    "node_id": "Skill:Python",
                    "type": "Skill",
                    "name": "Python",
                    "confidence": 0.9,
                    "status": "applied",
                    "evidence_refs": ["chunk:cv.pdf#c1"],
                },
                {
                    "delta_id": "delta_node_002",
                    "operation": "add",
                    "node_id": "Skill:Rust",
                    "type": "Skill",
                    "name": "Rust",
                    "confidence": 0.4,
                    "status": "skipped",
                    "status_reason": "Weak evidence.",
                    "evidence_refs": [],
                },
            ],
            "edges": [
                {
                    "delta_id": "delta_edge_001",
                    "operation": "add",
                    "source": {"type": "Person", "name": "Yang", "node_id": "Person:Yang"},
                    "target": {"type": "Skill", "name": "Python", "node_id": "Skill:Python"},
                    "relation": "USES_SKILL",
                    "confidence": 0.7,
                    "status": "applied",
                    "evidence_refs": ["node:Skill:Python"],
                }
            ],
        },
        "report_sections": [
            {
                "section_id": "section_summary",
                "title": "Executive Summary",
                "kind": "executive_summary",
                "summary": "Short.",
                "body": "Long body.",
                "evidence_refs": ["chunk:cv.pdf#c1"],
                "related_delta_ids": ["delta_node_001"],
            },
            {
                "section_id": "section_graph_delta",
                "title": "Graph Delta",
                "kind": "graph_delta",
                "summary": "Deltas.",
                "body": "delta_node_001",
            },
        ],
    }


def test_adapt_simulation_summary_is_compact_and_counts_v2():
    payload = adapt_simulation_summary(_v2_result(), project_id="p1", max_steps=1)

    assert payload["kind"] == "simulation_summary"
    assert payload["read_only"] is True
    assert payload["schema_version"] == "2.0"
    assert payload["summary"]["title"] == "Simulation Report"
    assert payload["workflow_steps"] == [
        {"id": "load_context", "label": "Load Context", "status": "completed", "summary": "Loaded."}
    ]
    assert payload["counts"] == {
        "personas": 1,
        "debate_turns": 1,
        "report_sections": 2,
        "graph_delta_nodes": 2,
        "graph_delta_edges": 1,
        "events": 2,
    }


def test_adapt_simulation_summary_legacy_fallback():
    legacy = {
        "generated_at": "2026-06-08T00:00:00+00:00",
        "query": "q",
        "personas": [{"agent_id": "a1"}],
        "timeline": [{"observation": "obs"}],
        "graph_enhancements": {"nodes": [{"type": "Skill", "name": "Python"}], "edges": []},
        "report": {"title": "Legacy Report", "answer": "ok"},
    }

    payload = adapt_simulation_summary(legacy, project_id="p1")

    assert payload["schema_version"] == "legacy"
    assert payload["workflow_steps"][0]["id"] == "legacy_result_loaded"
    assert payload["summary"]["graph_delta_count"] == 1
    assert payload["counts"]["debate_turns"] == 1


def test_adapt_simulation_graph_delta_filters_and_sorts():
    payload = adapt_simulation_graph_delta(
        _v2_result(),
        project_id="p1",
        status="applied",
        item_type="all",
        max_items=1,
        sort="confidence_asc",
    )

    assert payload["summary"] == {
        "total": 3,
        "returned": 1,
        "proposed": 0,
        "applied": 1,
        "skipped": 0,
        "rejected": 0,
        "low_confidence": 0,
    }
    assert payload["items"][0]["delta_id"] == "delta_edge_001"
    assert payload["items"][0]["label"] == "Yang -USES_SKILL-> Python"
    assert payload["truncated"] is True


def test_adapt_simulation_report_section_selects_kind_and_can_omit_body():
    payload = adapt_simulation_report_section(
        _v2_result(),
        project_id="p1",
        kind="executive_summary",
        include_body=False,
    )

    assert payload["selected"]["section_id"] == "section_summary"
    assert "body" not in payload["selected"]
    assert [section["section_id"] for section in payload["available_sections"]] == [
        "section_summary",
        "section_graph_delta",
    ]


def test_adapt_simulation_event_log_filters_and_legacy_synthesizes():
    filtered = adapt_simulation_event_log(_v2_result(), project_id="p1", step_id="debate")
    legacy = adapt_simulation_event_log(
        {"timeline": [{"observation": "legacy turn"}], "generated_at": "now"},
        project_id="p1",
    )

    assert [event["event_id"] for event in filtered["events"]] == ["evt_001"]
    assert legacy["schema_version"] == "legacy"
    assert legacy["events"][0]["event_id"] == "legacy_turn_001"
    assert legacy["events"][0]["type"] == "debate_turn"


def test_resolve_simulation_evidence_handles_chunk_node_report_and_unresolved():
    project_dir = Path(config.PROJECTS_DIR) / "p1"
    project_dir.mkdir(parents=True)
    (project_dir / "chunks.json").write_text(
        json.dumps([
            {
                "chunk_id": "c1",
                "text": "Python evidence text.",
                "source_file": "cv.pdf",
                "file_type": "cv",
                "page_num": 1,
                "char_offset": 0,
            }
        ]),
        encoding="utf-8",
    )
    graph = nx.DiGraph()
    graph.add_node("Skill:Python", type="Skill", name="Python", source_files=["cv.pdf"])
    (project_dir / "graph.json").write_text(json.dumps(nx.node_link_data(graph)), encoding="utf-8")

    payload = resolve_simulation_evidence(
        "p1",
        _v2_result(),
        ["chunk:cv.pdf#c1", "node:Skill:Python", "report:section_summary", "chunk:nope#missing"],
        max_chars_per_ref=10,
    )

    assert payload["refs"][0]["resolved"] is True
    assert payload["refs"][0]["text"] == "Python evi"
    assert payload["refs"][0]["truncated"] is True
    assert payload["refs"][1]["name"] == "Python"
    assert payload["refs"][2]["section"]["body"] == "Long body."
    assert payload["unresolved_refs"] == ["chunk:nope#missing"]


def test_resolve_simulation_evidence_surfaces_node_and_edge_anchors():
    project_dir = Path(config.PROJECTS_DIR) / "p1"
    project_dir.mkdir(parents=True)
    node_anchor = {
        "source_file": "cv.pdf",
        "chunk_id": "c1",
        "page_num": 2,
        "char_offset": 10,
        "quote": "used Python",
        "confidence": 0.9,
        "method": "llm_extraction",
        "directness": "direct",
    }
    edge_anchor = {
        "source_file": "cv.pdf",
        "chunk_id": "c2",
        "page_num": 3,
        "char_offset": 42,
        "quote": "Yang developed ProjectOS",
        "confidence": 0.8,
        "method": "llm_extraction",
        "directness": "inferred",
    }
    graph = nx.DiGraph()
    graph.add_node("Skill:Python", type="Skill", name="Python", evidence=[node_anchor])
    graph.add_node("Person:Yang", type="Person", name="Yang")
    graph.add_edge(
        "Person:Yang",
        "Skill:Python",
        relation="USES_SKILL",
        confidence=0.8,
        evidence=edge_anchor,
    )
    (project_dir / "graph.json").write_text(json.dumps(nx.node_link_data(graph)), encoding="utf-8")

    payload = resolve_simulation_evidence(
        "p1",
        _v2_result(),
        ["node:Skill:Python", "edge:Person:Yang->Skill:Python:USES_SKILL"],
    )

    node_ref = payload["refs"][0]
    assert node_ref["resolved"] is True
    assert node_ref["evidence"] == [node_anchor]

    edge_ref = payload["refs"][1]
    assert edge_ref["resolved"] is True
    assert edge_ref["evidence"] == edge_anchor


def test_load_simulation_result_supports_latest_and_archived_run():
    project_dir = Path(config.PROJECTS_DIR) / "p1"
    archive_dir = project_dir / "simulations"
    archive_dir.mkdir(parents=True)
    latest = {"run_id": "latest"}
    archived = {"run_id": "archived"}
    (project_dir / "simulation.json").write_text(json.dumps(latest), encoding="utf-8")
    (archive_dir / "archived.json").write_text(json.dumps(archived), encoding="utf-8")

    assert load_simulation_result("p1") == latest
    assert load_simulation_result("p1", "archived") == archived


def test_load_simulation_result_rejects_path_like_run_id():
    project_dir = Path(config.PROJECTS_DIR) / "p1"
    project_dir.mkdir(parents=True)
    (project_dir / "simulation.json").write_text(json.dumps({"run_id": "latest"}), encoding="utf-8")

    with pytest.raises(ValueError, match="Simulation run not found"):
        load_simulation_result("p1", "../latest")


def _graph_with_kaist():
    graph = nx.DiGraph()
    graph.add_node(
        "Institution:KAIST", type="Institution", name="KAIST",
        description="대학", source_files=["resume.pdf"], evidence=[],
    )
    graph.add_node(
        "Skill:Python", type="Skill", name="Python",
        description="언어", source_files=["resume.pdf"], evidence=[],
    )
    return graph


def test_resolve_ref_accepts_bare_node_id():
    item = _resolve_ref(
        "Skill:Python",
        chunks=[], graph=_graph_with_kaist(), events={}, sections={}, max_chars=500,
    )
    assert item["resolved"] is True
    assert item["kind"] == "node"
    assert item["node_id"] == "Skill:Python"


def test_resolve_ref_recovers_wrong_type_prefix_by_unique_name():
    item = _resolve_ref(
        "Organization:KAIST",
        chunks=[], graph=_graph_with_kaist(), events={}, sections={}, max_chars=500,
    )
    assert item["resolved"] is True
    assert item["node_id"] == "Institution:KAIST"


def test_resolve_ref_ambiguous_name_stays_unresolved():
    graph = _graph_with_kaist()
    graph.add_node("Organization:Python", type="Organization", name="Python")
    item = _resolve_ref(
        "Publication:Python",
        chunks=[], graph=graph, events={}, sections={}, max_chars=500,
    )
    assert item["resolved"] is False


def test_resolve_ref_free_text_stays_unresolved():
    item = _resolve_ref(
        "agent_3, agent_1의 뉴로-심볼릭 아키텍처 제안",
        chunks=[], graph=_graph_with_kaist(), events={}, sections={}, max_chars=500,
    )
    assert item["resolved"] is False
    assert item["kind"] == "unknown"
