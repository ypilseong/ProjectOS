import hashlib
import json
from pathlib import Path

import pytest

from app.services.document_hash_store import DocumentHashStore


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def test_new_store_reports_all_files_changed(tmp_path):
    store = DocumentHashStore(tmp_path)
    assert store.get_changed_files(["a.txt", "b.txt"]) == ["a.txt", "b.txt"]


def test_update_and_reload_shows_no_change(tmp_path):
    store = DocumentHashStore(tmp_path)
    store.update("a.txt", _md5("hello"))
    store.save()
    store2 = DocumentHashStore(tmp_path)
    store2.update("a.txt", _md5("hello"))
    assert store2.get_changed_files(["a.txt"]) == []


def test_changed_content_detected(tmp_path):
    store = DocumentHashStore(tmp_path)
    store.update("a.txt", _md5("v1"))
    store.save()
    store2 = DocumentHashStore(tmp_path)
    store2.update("a.txt", _md5("v2"))
    assert store2.get_changed_files(["a.txt"]) == ["a.txt"]


def test_ontology_change_returns_all_files_changed(tmp_path):
    store = DocumentHashStore(tmp_path)
    store.update("a.txt", _md5("x"))
    store.update_ontology(_md5("ont_v1"))
    store.save()
    store2 = DocumentHashStore(tmp_path)
    store2.update("a.txt", _md5("x"))
    store2.update_ontology(_md5("ont_v2"))
    assert store2.get_changed_files(["a.txt"]) == ["a.txt"]


def test_new_file_always_changed(tmp_path):
    store = DocumentHashStore(tmp_path)
    store.update("a.txt", _md5("x"))
    store.save()
    store2 = DocumentHashStore(tmp_path)
    store2.update("a.txt", _md5("x"))
    store2.update("b.txt", _md5("y"))
    assert store2.get_changed_files(["a.txt", "b.txt"]) == ["b.txt"]
