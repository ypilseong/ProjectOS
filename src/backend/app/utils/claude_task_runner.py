from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from app.config import config
from app.utils.llm_client import _extract_json, _record_claude_usage
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ClaudeTaskError(RuntimeError):
    pass


class ClaudeTaskRunner:
    """Run isolated Claude Code tasks outside the ProjectOS repo.

    Task-specific instructions are written to a task-local CLAUDE.md and passed
    as --system-prompt. The process cwd is the task workspace, so repo-level
    CLAUDE.md files are not discovered or merged into the task.
    """

    def __init__(
        self,
        tasks_dir: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ):
        self.tasks_dir = Path(tasks_dir or config.CLAUDE_TASKS_DIR)
        self.model = model if model is not None else config.CLAUDE_CODE_MODEL
        self.timeout = timeout if timeout is not None else config.CLAUDE_TASK_TIMEOUT

    async def run_task(
        self,
        task_name: str,
        instructions: str,
        input_data: dict[str, Any],
        output_schema: dict[str, Any],
        allowed_paths: list[str | Path] | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        task_id = f"{task_name}-{uuid.uuid4().hex[:12]}"
        workspace = self.tasks_dir / task_id
        workspace.mkdir(parents=True, exist_ok=True)

        (workspace / "CLAUDE.md").write_text(instructions, encoding="utf-8")
        (workspace / "input.json").write_text(
            json.dumps(input_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (workspace / "schema.json").write_text(
            json.dumps(output_schema, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        cmd = ["claude", "-p", "--no-session-persistence", "--output-format", "json"]
        if config.CLAUDE_TASK_BARE:
            cmd.append("--bare")
        if self.model:
            cmd.extend(["--model", self.model])

        allow_dirs = self._allow_dirs(allowed_paths or [])
        if allow_dirs:
            cmd.extend(["--add-dir", *allow_dirs])

        cmd.extend([
            "--system-prompt",
            instructions,
            prompt or (
                "You are running an isolated ProjectOS task. "
                "Read ./input.json and ./schema.json from the current task workspace. "
                "Return JSON only, matching schema.json."
            ),
        ])

        logger.info(f"Claude task {task_id}: running in {workspace}")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise ClaudeTaskError(f"Claude task timed out after {self.timeout}s: {task_id}") from exc

        stdout_text = stdout.decode()
        stderr_text = stderr.decode()
        if proc.returncode != 0:
            raise ClaudeTaskError(
                f"Claude task failed rc={proc.returncode}: {stderr_text.strip() or stdout_text.strip()}"
            )

        wrapper = json.loads(stdout_text)
        _record_claude_usage(wrapper)
        if wrapper.get("is_error"):
            raise ClaudeTaskError(wrapper.get("result") or "Claude task returned an error")

        result = _extract_json(wrapper.get("result", ""))
        self._validate_required_keys(result, output_schema)
        (workspace / "output.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result

    @staticmethod
    def _allow_dirs(paths: list[str | Path]) -> list[str]:
        dirs = []
        seen = set()
        for raw in paths:
            path = Path(raw).resolve()
            directory = path if path.is_dir() else path.parent
            key = str(directory)
            if key not in seen:
                dirs.append(key)
                seen.add(key)
        return dirs

    @staticmethod
    def _validate_required_keys(result: dict[str, Any], schema: dict[str, Any]) -> None:
        required = schema.get("required", [])
        missing = [key for key in required if key not in result]
        if missing:
            raise ClaudeTaskError(f"Claude task output missing required keys: {', '.join(missing)}")
