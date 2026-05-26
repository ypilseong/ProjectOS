import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.config import config

router = APIRouter()


@router.get("")
async def get_user():
    path = Path(config.USER_CONFIG_PATH)
    if not path.exists():
        raise HTTPException(status_code=404, detail="User config not set")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="User config is corrupted")


@router.post("")
async def set_user(body: dict):
    data = {
        "name": body.get("name", ""),
        "display_name": body.get("display_name") or body.get("name", ""),
    }
    path = Path(config.USER_CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data
