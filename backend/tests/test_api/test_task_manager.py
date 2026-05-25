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


def test_task_manager_get_missing():
    from app.services.task_manager import TaskManager
    tm = TaskManager()
    assert tm.get("nonexistent") is None
