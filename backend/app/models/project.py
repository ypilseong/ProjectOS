from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class ProjectStatus(str, Enum):
    CREATED = "created"
    PARSING = "parsing"
    ONTOLOGY = "ontology"
    BUILDING = "building"
    WRITING = "writing"
    READY = "ready"
    FAILED = "failed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Project(BaseModel):
    project_id: str
    name: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.CREATED
    created_at: datetime = Field(default_factory=datetime.utcnow)
    files: list = Field(default_factory=list)
    stats: Optional[dict] = None


class Task(BaseModel):
    task_id: str
    project_id: str
    task_type: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    message: str = ""
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
