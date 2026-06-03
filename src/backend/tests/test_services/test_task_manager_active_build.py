from app.services.task_manager import TaskManager
from app.models.project import TaskStatus


def test_has_active_build_true_when_graph_task_running(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.task_manager.config.PROJECTS_DIR", str(tmp_path))
    tm = TaskManager()
    task = tm.create("p1", "graph")
    tm.update(task.task_id, status=TaskStatus.RUNNING)
    assert tm.has_active_build("p1") is True


def test_has_active_build_false_when_completed(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.task_manager.config.PROJECTS_DIR", str(tmp_path))
    tm = TaskManager()
    task = tm.create("p1", "graph_incremental")
    tm.update(task.task_id, status=TaskStatus.COMPLETED)
    assert tm.has_active_build("p1") is False


def test_has_active_build_ignores_other_projects_and_types(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.task_manager.config.PROJECTS_DIR", str(tmp_path))
    tm = TaskManager()
    t1 = tm.create("p2", "graph")
    tm.update(t1.task_id, status=TaskStatus.RUNNING)
    t2 = tm.create("p1", "parse")
    tm.update(t2.task_id, status=TaskStatus.RUNNING)
    assert tm.has_active_build("p1") is False
