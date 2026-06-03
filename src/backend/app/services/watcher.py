import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path

from app.config import config
from app.services.task_manager import task_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)


def compute_stable_changes(
    current: dict[str, str],
    last_built: dict[str, str],
    prev_poll: dict[str, str],
) -> set[str]:
    """변경(신규/수정)되었고 직전 폴링 대비 안정된 파일명 집합을 반환.

    - 변경: last_built에 해시가 없거나(신규) 다름(수정).
    - 안정: prev_poll의 해시가 current와 동일(쓰기/동기화 완료).
    """
    stable: set[str] = set()
    for fname, h in current.items():
        changed = last_built.get(fname) != h
        settled = prev_poll.get(fname) == h
        if changed and settled:
            stable.add(fname)
    return stable


def reparse_and_replace_chunks(project_id: str, changed_files: set[str]) -> None:
    """changed_files를 재파싱해 chunks.json에서 해당 source_file 청크를 교체한다."""
    from app.agents.parser_agent import ParserAgent

    proj_dir = Path(config.PROJECTS_DIR) / project_id
    files_dir = proj_dir / "files"
    chunks_path = proj_dir / "chunks.json"

    existing = json.loads(chunks_path.read_text(encoding="utf-8")) if chunks_path.exists() else []

    file_type_by_source = {c["source_file"]: c.get("file_type", "note") for c in existing}

    kept = [c for c in existing if c["source_file"] not in changed_files]

    agent = ParserAgent()
    new_chunks: list[dict] = []
    for fname in sorted(changed_files):
        fpath = files_dir / fname
        if not fpath.exists():
            continue
        file_type = file_type_by_source.get(fname, "note")
        parsed = agent.run([str(fpath)], file_type=file_type)
        new_chunks.extend(dataclasses.asdict(c) for c in parsed)

    combined = kept + new_chunks
    chunks_path.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8"
    )


class WatcherService:
    def __init__(self):
        self._prev_hashes: dict[str, dict[str, str]] = {}
        self._task: asyncio.Task | None = None
        self._stop = False

    def eligible_projects(self) -> list[str]:
        root = Path(config.PROJECTS_DIR)
        if not root.exists():
            return []
        result = []
        for proj in sorted(root.iterdir()):
            if not proj.is_dir():
                continue
            if (
                (proj / "chunks.json").exists()
                and (proj / "ontology.json").exists()
                and (proj / "graph.json").exists()
            ):
                result.append(proj.name)
        return result

    def _current_hashes(self, project_id: str) -> dict[str, str]:
        files_dir = Path(config.PROJECTS_DIR) / project_id / "files"
        if not files_dir.exists():
            return {}
        out: dict[str, str] = {}
        for f in files_dir.iterdir():
            if f.is_file():
                out[f.name] = hashlib.md5(f.read_bytes()).hexdigest()
        return out

    def _last_built_hashes(self, project_id: str) -> dict[str, str]:
        path = Path(config.PROJECTS_DIR) / project_id / "hashes.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return {k: v for k, v in data.items() if k != "__ontology__"}

    def detect_changes(self, project_id: str) -> set[str]:
        current = self._current_hashes(project_id)
        last_built = self._last_built_hashes(project_id)
        prev_poll = self._prev_hashes.get(project_id, {})
        stable = compute_stable_changes(current, last_built, prev_poll)
        self._prev_hashes[project_id] = current
        return stable

    async def run_auto_update(self, project_id: str, changed_files: set[str]) -> None:
        from app.api.graph import _run_graph

        reparse_and_replace_chunks(project_id, changed_files)
        task = task_manager.create(project_id, "graph_watcher")
        await _run_graph(task.task_id, project_id, incremental=True, trigger="watcher")

    async def poll_once(self) -> None:
        for project_id in self.eligible_projects():
            try:
                if task_manager.has_active_build(project_id):
                    self._prev_hashes[project_id] = self._current_hashes(project_id)
                    continue
                changed = self.detect_changes(project_id)
                if changed:
                    logger.info(f"Watcher: {project_id} 변경 감지 {sorted(changed)} → 자동 빌드")
                    await self.run_auto_update(project_id, changed)
            except Exception as e:
                logger.error(f"Watcher: {project_id} 처리 실패: {e}")

    async def _loop(self) -> None:
        while not self._stop:
            try:
                await self.poll_once()
            except Exception as e:
                logger.error(f"Watcher 폴링 사이클 실패: {e}")
            await asyncio.sleep(config.WATCHER_POLL_SECONDS)

    def start(self) -> None:
        if not config.WATCHER_ENABLED:
            return
        self._stop = False
        self._task = asyncio.create_task(self._loop())
        logger.info(f"Watcher 시작 (간격 {config.WATCHER_POLL_SECONDS}s)")

    async def stop(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
