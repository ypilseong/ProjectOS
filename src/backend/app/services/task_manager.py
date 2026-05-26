import uuid
from datetime import datetime
from app.models.project import Task, TaskStatus


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def create(self, project_id: str, task_type: str) -> Task:
        task = Task(
            task_id=str(uuid.uuid4()),
            project_id=project_id,
            task_type=task_type,
        )
        self._tasks[task.task_id] = task
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


task_manager = TaskManager()
