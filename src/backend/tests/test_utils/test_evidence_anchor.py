from app.models.graph import TextChunk
from app.utils.evidence_anchor import make_evidence_anchor


def _chunk(page=3, offset=120):
    return TextChunk(
        chunk_id="c1",
        text="Yang Pilseong used Python in ProjectOS.",
        source_file="cv.pdf",
        file_type="cv",
        page_num=page,
        char_offset=offset,
    )


def test_anchor_carries_full_provenance():
    anchor = make_evidence_anchor(
        _chunk(),
        quote="used Python",
        confidence=0.9,
        method="llm_extraction",
        directness="direct",
    )
    assert anchor["source_file"] == "cv.pdf"
    assert anchor["chunk_id"] == "c1"
    assert anchor["page_num"] == 3
    assert anchor["char_offset"] == 120
    assert anchor["quote"] == "used Python"
    assert anchor["confidence"] == 0.9
    assert anchor["method"] == "llm_extraction"
    assert anchor["directness"] == "direct"


def test_anchor_defaults():
    anchor = make_evidence_anchor(_chunk(page=None, offset=0))
    assert anchor["quote"] == ""
    assert anchor["confidence"] == 1.0
    assert anchor["method"] == "llm_extraction"
    assert anchor["directness"] == "direct"
    assert anchor["page_num"] is None
    assert anchor["char_offset"] == 0


def test_anchor_normalizes_unknown_directness_to_inferred():
    anchor = make_evidence_anchor(_chunk(), directness="maybe")
    assert anchor["directness"] == "inferred"
