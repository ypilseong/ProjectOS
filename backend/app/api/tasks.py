import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services.task_manager import task_manager

router = APIRouter()


@router.get("/{task_id}")
async def get_task(task_id: str):
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task.model_dump()


@router.get("/{task_id}/stream")
async def stream_task(task_id: str):
    async def generate():
        while True:
            task = task_manager.get(task_id)
            if not task:
                yield f"data: {json.dumps({'error': 'task not found'})}\n\n"
                break
            payload = {
                "status": task.status,
                "progress": task.progress,
                "message": task.message,
                "error": task.error,
            }
            yield f"data: {json.dumps(payload)}\n\n"
            if task.status in ("completed", "failed"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
