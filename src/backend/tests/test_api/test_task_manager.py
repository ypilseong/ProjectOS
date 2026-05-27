def test_task_manager_create_and_get():
    from app.services.task_manager import TaskManager
    tm = TaskManager()
    task = tm.create("proj-1", "parse")
    assert task.task_id
    assert task.status == "pending"
    retrieved = tm.get(task.task_id)
    assert retrieved.task_id == task.task_id


def test_task_manager_update():
    from app.services.task_manager import TaskManager
    from app.models.project import TaskStatus
    tm = TaskManager()
    task = tm.create("proj-1", "graph")
    tm.update(task.task_id, status=TaskStatus.RUNNING, progress=50, message="halfway")
    updated = tm.get(task.task_id)
    assert updated.status == TaskStatus.RUNNING
    assert updated.progress == 50
    assert updated.message == "halfway"


def test_task_manager_writes_project_task_log():
    import json
    from pathlib import Path

    from app.config import config
    from app.models.project import TaskStatus
    from app.services.task_manager import TaskManager

    tm = TaskManager()
    task = tm.create("proj-1", "graph")
    tm.update(task.task_id, status=TaskStatus.RUNNING, progress=50, message="halfway")

    log_path = Path(config.LOG_DIR) / "projects" / "proj-1" / "tasks.log"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    created = json.loads(lines[0])
    updated = json.loads(lines[1])
    assert created["event"] == "created"
    assert updated["event"] == "updated"
    assert updated["task_id"] == task.task_id
    assert updated["progress"] == 50
    assert updated["message"] == "halfway"


def test_task_manager_get_missing():
    from app.services.task_manager import TaskManager
    tm = TaskManager()
    assert tm.get("nonexistent") is None
