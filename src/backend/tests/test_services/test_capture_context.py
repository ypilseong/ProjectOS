from app.services.capture_context import (
    is_complete_context,
    load_captures,
    save_capture,
)


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
