# API — ProjectOS

FastAPI 라우터 4개. `app/main.py` 에서 등록.

## 라우터 목록

| 파일 | prefix | 주요 엔드포인트 |
|------|--------|----------------|
| projects.py | /projects | CRUD, 파일 업로드, vault 트리 |
| graph.py | /projects/{id} | 온톨로지 생성, 그래프 구축, 통계 |
| chat.py | /projects/{id} | SSE 채팅 스트리밍 |
| tasks.py | /tasks | 태스크 상태, SSE 진행 스트림 |

## SSE 패턴 (tasks)

GET 방식. EventSource로 구독. 1초 폴링:

```python
async def task_stream(task_id: str):
    async def generate():
        while True:
            task = task_manager.get(task_id)
            yield f"data: {task.model_dump_json()}\n\n"
            if task.status in ("completed", "failed"):
                break
            await asyncio.sleep(1)
    return StreamingResponse(generate(), media_type="text/event-stream")
```

## SSE 패턴 (chat)

POST 방식. fetch + ReadableStream 으로 구독:

```python
async def chat_stream(project_id: str, body: ChatRequest):
    async def generate():
        async for token in query_agent.stream(...):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

## 에이전트 지연 임포트 (순환 임포트 방지)

에이전트를 모듈 상단에서 임포트하지 말 것. 함수 내부에서 임포트:

```python
async def run_graph(project_id: str, background_tasks: BackgroundTasks):
    async def _run():
        from app.agents.graph_builder_agent import GraphBuilderAgent  # 여기서 임포트
        agent = GraphBuilderAgent()
        ...
    background_tasks.add_task(_run)
```

## 배경 태스크 패턴

`BackgroundTasks` 또는 `asyncio.create_task` 사용. 태스크 ID를 즉시 반환하고 진행 상태는 SSE로 스트리밍.
