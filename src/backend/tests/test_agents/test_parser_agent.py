import pytest
from pathlib import Path


@pytest.fixture
def tmp_txt(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("A" * 600, encoding="utf-8")
    return str(f)


@pytest.fixture
def tmp_md(tmp_path):
    f = tmp_path / "readme.md"
    f.write_text("# Project\n\n" + "Content " * 100, encoding="utf-8")
    return str(f)


def test_parser_creates_chunks_from_txt(tmp_txt):
    from app.agents.parser_agent import ParserAgent
    agent = ParserAgent()
    chunks = agent.run([tmp_txt], file_type="note")
    assert len(chunks) > 1
    assert all(c.source_file == "test.txt" for c in chunks)
    assert all(c.file_type == "note" for c in chunks)
    assert all(c.chunk_id for c in chunks)


def test_chunk_overlap(tmp_txt):
    from app.agents.parser_agent import ParserAgent
    agent = ParserAgent()
    chunks = agent.run([tmp_txt], file_type="note")
    assert len(chunks) >= 2
    c1_end = chunks[0].char_offset + len(chunks[0].text)
    # With overlap, second chunk starts before first chunk ends
    assert c1_end > chunks[1].char_offset


def test_chunk_size_limit(tmp_txt):
    from app.agents.parser_agent import ParserAgent
    agent = ParserAgent()
    chunks = agent.run([tmp_txt], file_type="note")
    # Each chunk should not exceed CHUNK_SIZE
    for c in chunks:
        assert len(c.text) <= 550  # Some tolerance for whitespace


def test_parser_preserves_source_file(tmp_md):
    from app.agents.parser_agent import ParserAgent
    agent = ParserAgent()
    chunks = agent.run([tmp_md], file_type="project")
    assert all(c.source_file == "readme.md" for c in chunks)
    assert all(c.file_type == "project" for c in chunks)


def test_parser_multiple_files(tmp_path):
    from app.agents.parser_agent import ParserAgent
    f1 = tmp_path / "cv.txt"
    f2 = tmp_path / "project.txt"
    f1.write_text("Career content " * 50, encoding="utf-8")
    f2.write_text("Project content " * 50, encoding="utf-8")
    agent = ParserAgent()
    chunks = agent.run([str(f1), str(f2)], file_type="cv")
    sources = {c.source_file for c in chunks}
    assert "cv.txt" in sources
    assert "project.txt" in sources


def test_chunk_ids_are_unique(tmp_txt):
    from app.agents.parser_agent import ParserAgent
    agent = ParserAgent()
    chunks = agent.run([tmp_txt], file_type="note")
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
