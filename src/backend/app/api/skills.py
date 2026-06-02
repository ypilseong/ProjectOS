from fastapi import APIRouter

from app.skills import catalog_as_dicts

router = APIRouter()


@router.get("")
async def list_skills():
    return {"skills": catalog_as_dicts()}
