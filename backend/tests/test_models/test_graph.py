from dataclasses import asdict
import pytest


def test_text_chunk_creation():
    from app.models.graph import TextChunk
    chunk = TextChunk(
        chunk_id="abc-123", text="sample text", source_file="cv.pdf",
        file_type="cv", page_num=1, char_offset=0
    )
    assert chunk.chunk_id == "abc-123"
    assert chunk.file_type == "cv"
    assert chunk.page_num == 1


def test_text_chunk_optional_page_num():
    from app.models.graph import TextChunk
    chunk = TextChunk(
        chunk_id="abc-456", text="sample", source_file="readme.md",
        file_type="note", page_num=None, char_offset=100
    )
    assert chunk.page_num is None


def test_ontology_creation():
    from app.models.graph import Ontology, EntityTypeDef, EdgeTypeDef
    ontology = Ontology(
        entity_types=[EntityTypeDef("Person", "사람", ["양필성"])],
        edge_types=[EdgeTypeDef("USES_SKILL", "기술 사용", ["Person"], ["Skill"])],
        analysis_summary="커리어 온톨로지"
    )
    assert len(ontology.entity_types) == 1
    assert ontology.entity_types[0].name == "Person"
    assert ontology.edge_types[0].source_types == ["Person"]


def test_career_profile_creation():
    from app.models.graph import CareerProfile
    profile = CareerProfile(
        name="Yang Pilseong",
        expertise=["ML", "NLP"],
        skills=["Python", "PyTorch"],
        projects=["ProjectOS"],
        organizations=["KAIST"],
        publications=[],
        achievements=["우수 논문상"],
        persona_summary="ML 전문 연구자",
        timeline=[{"year": 2020, "event": "KAIST 입학"}]
    )
    assert profile.name == "Yang Pilseong"
    assert profile.timeline[0]["year"] == 2020
    assert "Python" in profile.skills


def test_graph_stats_creation():
    from app.models.graph import GraphStats
    stats = GraphStats(
        total_nodes=42,
        total_edges=87,
        nodes_by_type={"Person": 1, "Skill": 15, "Project": 8},
        edges_by_type={"USES_SKILL": 30, "DEVELOPED": 8}
    )
    assert stats.total_nodes == 42
    assert stats.nodes_by_type["Skill"] == 15


def test_models_are_dataclasses():
    from app.models.graph import TextChunk, CareerProfile, GraphStats
    import dataclasses
    assert dataclasses.is_dataclass(TextChunk)
    assert dataclasses.is_dataclass(CareerProfile)
    assert dataclasses.is_dataclass(GraphStats)
