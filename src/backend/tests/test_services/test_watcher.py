import json
from pathlib import Path

from app.models.graph import TextChunk
from app.services.watcher import compute_stable_changes, reparse_and_replace_chunks


def test_new_file_stable_after_two_identical_polls():
    current = {"a.txt": "h1"}
    last_built = {}
    prev_poll = {"a.txt": "h1"}
    assert compute_stable_changes(current, last_built, prev_poll) == {"a.txt"}


def test_modified_file_included_when_stable():
    current = {"a.txt": "h2"}
    last_built = {"a.txt": "h1"}
    prev_poll = {"a.txt": "h2"}
    assert compute_stable_changes(current, last_built, prev_poll) == {"a.txt"}


def test_unchanged_file_excluded():
    current = {"a.txt": "h1"}
    last_built = {"a.txt": "h1"}
    prev_poll = {"a.txt": "h1"}
    assert compute_stable_changes(current, last_built, prev_poll) == set()


def test_unstable_file_excluded_until_settled():
    current = {"a.txt": "h2"}
    last_built = {"a.txt": "h1"}
    prev_poll = {"a.txt": "h1_partial"}
    assert compute_stable_changes(current, last_built, prev_poll) == set()


def test_new_file_excluded_on_first_sighting():
    current = {"a.txt": "h1"}
    last_built = {}
    prev_poll = {}
    assert compute_stable_changes(current, last_built, prev_poll) == set()


def _write_chunks(proj_dir: Path, chunks: list[dict]) -> None:
    (proj_dir / "chunks.json").write_text(
        json.dumps(chunks, ensure_ascii=False), encoding="utf-8"
    )


def test_replace_chunks_no_duplicates_for_modified_file(monkeypatch, tmp_path):
    proj_dir = tmp_path / "p1"
    (proj_dir / "files").mkdir(parents=True)
    _write_chunks(proj_dir, [
        {"chunk_id": "old", "text": "old", "source_file": "a.txt",
         "file_type": "resume", "page_num": 1, "char_offset": 0},
        {"chunk_id": "keep", "text": "keep", "source_file": "b.txt",
         "file_type": "note", "page_num": 1, "char_offset": 0},
    ])
    monkeypatch.setattr("app.services.watcher.config.PROJECTS_DIR", str(tmp_path))

    def fake_run(self, file_paths, file_type="note", progress_callback=None):
        return [TextChunk(chunk_id="new", text="new", source_file="a.txt",
                          file_type=file_type, page_num=1, char_offset=0)]
    monkeypatch.setattr("app.agents.parser_agent.ParserAgent.run", fake_run)

    (proj_dir / "files" / "a.txt").write_text("new content", encoding="utf-8")

    reparse_and_replace_chunks("p1", {"a.txt"})

    result = json.loads((proj_dir / "chunks.json").read_text(encoding="utf-8"))
    a_chunks = [c for c in result if c["source_file"] == "a.txt"]
    b_chunks = [c for c in result if c["source_file"] == "b.txt"]
    assert len(a_chunks) == 1
    assert a_chunks[0]["text"] == "new"
    assert a_chunks[0]["file_type"] == "resume"
    assert len(b_chunks) == 1
    assert b_chunks[0]["chunk_id"] == "keep"


import asyncio
import hashlib

import pytest

from app.services.watcher import WatcherService


def _make_project(tmp_path, pid, files: dict[str, str], built_hashes: dict[str, str]):
    proj_dir = tmp_path / pid
    files_dir = proj_dir / "files"
    files_dir.mkdir(parents=True)
    for name, content in files.items():
        (files_dir / name).write_text(content, encoding="utf-8")
    (proj_dir / "chunks.json").write_text("[]", encoding="utf-8")
    (proj_dir / "ontology.json").write_text("{}", encoding="utf-8")
    (proj_dir / "graph.json").write_text("{}", encoding="utf-8")
    (proj_dir / "hashes.json").write_text(
        json.dumps(built_hashes), encoding="utf-8"
    )
    return proj_dir


def test_eligible_projects_only_built(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.watcher.config.PROJECTS_DIR", str(tmp_path))
    _make_project(tmp_path, "built", {"a.txt": "x"}, {})
    unbuilt = tmp_path / "unbuilt" / "files"
    unbuilt.mkdir(parents=True)
    (tmp_path / "unbuilt" / "chunks.json").write_text("[]", encoding="utf-8")

    svc = WatcherService()
    assert svc.eligible_projects() == ["built"]


def test_poll_once_triggers_update_for_stable_change(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.watcher.config.PROJECTS_DIR", str(tmp_path))
    content = "hello"
    h = hashlib.md5(content.encode()).hexdigest()
    _make_project(tmp_path, "p1", {"a.txt": content}, {})

    svc = WatcherService()
    svc._prev_hashes["p1"] = {"a.txt": h}

    calls = []

    async def fake_update(project_id, files):
        calls.append((project_id, set(files)))

    monkeypatch.setattr(svc, "run_auto_update", fake_update)
    monkeypatch.setattr(
        "app.services.watcher.task_manager.has_active_build", lambda pid: False
    )

    asyncio.run(svc.poll_once())
    assert calls == [("p1", {"a.txt"})]


def test_poll_once_skips_when_build_active(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.watcher.config.PROJECTS_DIR", str(tmp_path))
    content = "hello"
    h = hashlib.md5(content.encode()).hexdigest()
    _make_project(tmp_path, "p1", {"a.txt": content}, {})

    svc = WatcherService()
    svc._prev_hashes["p1"] = {"a.txt": h}

    calls = []

    async def fake_update(project_id, files):
        calls.append(project_id)

    monkeypatch.setattr(svc, "run_auto_update", fake_update)
    monkeypatch.setattr(
        "app.services.watcher.task_manager.has_active_build", lambda pid: True
    )

    asyncio.run(svc.poll_once())
    assert calls == []


def test_start_noop_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.watcher.config.WATCHER_ENABLED", False)
    svc = WatcherService()
    svc.start()
    assert svc._task is None


def test_app_has_lifespan_and_watcher_imported():
    import app.main as main_mod

    assert main_mod.app.router.lifespan_context is not None
    assert hasattr(main_mod, "WatcherService") or "WatcherService" in dir(main_mod)
