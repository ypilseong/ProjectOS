import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import config


def _trace_path(project_id: str) -> Path:
    return Path(config.PROJECTS_DIR) / project_id / "traces.jsonl"


def record_trace(project_id: str, operation: str, **fields) -> dict:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "operation": operation,
        **fields,
    }
    path = _trace_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_traces(project_id: str) -> list[dict]:
    path = _trace_path(project_id)
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out
