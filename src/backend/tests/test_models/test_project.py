import pytest


def test_project_creation():
    from app.models.project import Project, ProjectStatus
    project = Project(project_id="test123", name="My Career Graph")
    assert project.project_id == "test123"
    assert project.status == ProjectStatus.CREATED
    assert project.files == []


def test_task_creation():
    from app.models.project import Task, TaskStatus
    task = Task(task_id="task-1", project_id="proj-1", task_type="parse")
    assert task.status == TaskStatus.PENDING
    assert task.progress == 0


def test_project_status_enum():
    from app.models.project import ProjectStatus
    assert ProjectStatus.CREATED == "created"
    assert ProjectStatus.READY == "ready"
    assert ProjectStatus.FAILED == "failed"


def test_task_status_enum():
    from app.models.project import TaskStatus
    assert TaskStatus.PENDING == "pending"
    assert TaskStatus.COMPLETED == "completed"
