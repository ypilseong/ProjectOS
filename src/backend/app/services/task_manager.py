import json
import uuid
from pathlib import Path

from app.config import config
from app.models.project import Task, TaskStatus


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._load()

    def _tasks_path(self) -> Path:
        return Path(config.PROJECTS_DIR) / ".tasks.json"

    def _load(self):
        path = self._tasks_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._tasks = {
                item["task_id"]: Task.model_validate(item)
                for item in data
                if "task_id" in item
            }
        except Exception:
            self._tasks = {}

    def _save(self):
        path = self._tasks_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [task.model_dump(mode="json") for task in self._tasks.values()]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def create(self, project_id: str, task_type: str) -> Task:
        task = Task(
            task_id=str(uuid.uuid4()),
            project_id=project_id,
            task_type=task_type,
        )
        self._tasks[task.task_id] = task
        self._save()
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def update(self, task_id: str, *, status=None, progress=None, message=None, error=None):
        task = self._tasks.get(task_id)
        if not task:
            return
        if status is not None:
            task.status = status
        if progress is not None:
            task.progress = progress
        if message is not None:
            task.message = message
        if error is not None:
            task.error = error
        self._save()


task_manager = TaskManager()
