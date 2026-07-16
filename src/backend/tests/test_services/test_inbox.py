import pytest


class FakeLLM:
    def __init__(self, backend=None):
        self.backend = backend

    async def chat_json(self, messages, **kwargs):
        prompt = messages[0]["content"]
        if "Abstract" in prompt and "References" in prompt:
            return {"file_type": "paper", "confidence": 0.91, "reason": "abstract and references"}
        return {"file_type": "memo", "confidence": 0.64, "reason": "informal notes"}


@pytest.mark.asyncio
async def test_classify_inbox_file_uses_local_llm_preview(monkeypatch):
    from app.services import inbox

    monkeypatch.setattr(inbox, "LLMClient", FakeLLM)
    path = inbox.inbox_root() / "draft.txt"
    path.write_text("Abstract\nThis paper studies graphs.\nReferences\n[1] Test", encoding="utf-8")

    result = await inbox.classify_inbox_file("draft.txt")

    assert result["suggested_file_type"] == "paper"
    assert result["confidence"] == 0.91
    assert result["text_preview"].startswith("Abstract")


@pytest.mark.asyncio
async def test_list_inbox_classifies_files_and_keeps_directories(monkeypatch):
    from app.services import inbox

    monkeypatch.setattr(inbox, "LLMClient", FakeLLM)
    (inbox.inbox_root() / "docs").mkdir()
    (inbox.inbox_root() / "memo.md").write_text("Meeting notes\n- follow up", encoding="utf-8")

    result = await inbox.list_inbox()

    entries = {entry["name"]: entry for entry in result["entries"]}
    assert entries["docs"]["kind"] == "directory"
    assert entries["memo.md"]["kind"] == "file"
    assert entries["memo.md"]["suggested_file_type"] == "memo"


def test_resolve_inbox_path_rejects_escape():
    from app.services.inbox import resolve_inbox_path

    with pytest.raises(ValueError, match="escapes INBOX_DIR"):
        resolve_inbox_path("../secret.txt")
