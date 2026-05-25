import json
import uuid
from pathlib import Path
from datetime import datetime
from app.config import config
from app.models.project import Project


class ProjectStore:
    def _project_dir(self, project_id: str) -> Path:
        return Path(config.PROJECTS_DIR) / project_id

    def _meta_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "meta.json"

    def create(self, name: str, description: str = "") -> Project:
        project_id = str(uuid.uuid4())[:8]
        d = self._project_dir(project_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "files").mkdir(exist_ok=True)
        project = Project(project_id=project_id, name=name, description=description)
        self._save(project)
        return project

    def get(self, project_id: str) -> Project | None:
        p = self._meta_path(project_id)
        if not p.exists():
            return None
        return Project.model_validate_json(p.read_text())

    def list_all(self) -> list[Project]:
        base = Path(config.PROJECTS_DIR)
        if not base.exists():
            return []
        projects = []
        for d in base.iterdir():
            if not d.is_dir():
                continue
            meta = d / "meta.json"
            if meta.exists():
                try:
                    projects.append(Project.model_validate_json(meta.read_text()))
                except Exception:
                    continue
        return sorted(projects, key=lambda p: p.created_at, reverse=True)

    def save(self, project: Project):
        self._save(project)

    def _save(self, project: Project):
        self._meta_path(project.project_id).write_text(
            project.model_dump_json(indent=2)
        )


project_store = ProjectStore()
