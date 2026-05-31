import json
from pathlib import Path

import pytest

from app.utils.claude_task_runner import ClaudeTaskError, ClaudeTaskRunner


@pytest.mark.asyncio
async def test_claude_task_runner_uses_isolated_workspace_and_system_prompt(tmp_path, monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "CLAUDE_TASKS_DIR", str(tmp_path / "tasks"))
    monkeypatch.setattr(config, "CLAUDE_CODE_MODEL", "claude-haiku-4-5")
    monkeypatch.setattr(config, "CLAUDE_TASK_BARE", False)
    calls = []

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return (
                json.dumps({
                    "type": "result",
                    "result": '{"entities":[],"relations":[]}',
                    "usage": {},
                    "modelUsage": {},
                }).encode(),
                b"",
            )

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProc()

    monkeypatch.setattr(
        "app.utils.claude_task_runner.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    runner = ClaudeTaskRunner()
    result = await runner.run_task(
        "graph",
        "# Task-only instructions",
        {"files": []},
        {"type": "object", "required": ["entities", "relations"]},
        allowed_paths=[tmp_path / "source.txt"],
    )

    args, kwargs = calls[0]
    cwd = Path(kwargs["cwd"])
    assert result == {"entities": [], "relations": []}
    assert cwd.parent == tmp_path / "tasks"
    assert (cwd / "CLAUDE.md").read_text() == "# Task-only instructions"
    assert (cwd / "input.json").exists()
    assert (cwd / "schema.json").exists()
    assert "--system-prompt" in args
    assert "# Task-only instructions" in args
    assert "--model" in args
    assert "claude-haiku-4-5" in args
    assert "--bare" not in args
    assert "--add-dir" in args


@pytest.mark.asyncio
async def test_claude_task_runner_can_enable_bare_mode(tmp_path, monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "CLAUDE_TASKS_DIR", str(tmp_path / "tasks"))
    monkeypatch.setattr(config, "CLAUDE_TASK_BARE", True)
    calls = []

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return (
                b'{"type":"result","result":"{\\"ok\\":true}","usage":{},"modelUsage":{}}',
                b"",
            )

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append(args)
        return FakeProc()

    monkeypatch.setattr(
        "app.utils.claude_task_runner.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    await ClaudeTaskRunner().run_task(
        "task",
        "instructions",
        {},
        {"type": "object", "required": ["ok"]},
    )

    assert "--bare" in calls[0]


@pytest.mark.asyncio
async def test_claude_task_runner_validates_required_keys(tmp_path, monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "CLAUDE_TASKS_DIR", str(tmp_path / "tasks"))

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return (
                b'{"type":"result","result":"{\\"entities\\":[]}","usage":{},"modelUsage":{}}',
                b"",
            )

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(
        "app.utils.claude_task_runner.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    with pytest.raises(ClaudeTaskError, match="missing required keys"):
        await ClaudeTaskRunner().run_task(
            "task",
            "instructions",
            {},
            {"type": "object", "required": ["entities", "relations"]},
        )
