from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.config import config
from app.services.digest import generate_digest

router = APIRouter()


def _digests_dir(project_id: str) -> Path:
    return Path(config.VAULT_DIR) / project_id / "Digests"


@router.post("/{project_id}/digest")
async def create_digest(project_id: str):
    result = generate_digest(project_id, trigger="manual")
    if result is None:
        raise HTTPException(404, "graph not found for project")
    return result


@router.get("/{project_id}/digests")
async def list_digests(project_id: str):
    d = _digests_dir(project_id)
    if not d.exists():
        return {"dates": []}
    dates = sorted(
        (p.stem for p in d.glob("*.md") if p.is_file()), reverse=True
    )
    return {"dates": dates}


@router.get("/{project_id}/digests/{digest_date}")
async def get_digest(project_id: str, digest_date: str):
    path = _digests_dir(project_id) / f"{digest_date}.md"
    if not path.exists():
        raise HTTPException(404, "digest not found")
    return {"date": digest_date, "markdown": path.read_text(encoding="utf-8")}
