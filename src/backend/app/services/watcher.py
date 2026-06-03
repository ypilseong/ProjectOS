import dataclasses
import json
from pathlib import Path

from app.config import config


def compute_stable_changes(
    current: dict[str, str],
    last_built: dict[str, str],
    prev_poll: dict[str, str],
) -> set[str]:
    """변경(신규/수정)되었고 직전 폴링 대비 안정된 파일명 집합을 반환.

    - 변경: last_built에 해시가 없거나(신규) 다름(수정).
    - 안정: prev_poll의 해시가 current와 동일(쓰기/동기화 완료).
    """
    stable: set[str] = set()
    for fname, h in current.items():
        changed = last_built.get(fname) != h
        settled = prev_poll.get(fname) == h
        if changed and settled:
            stable.add(fname)
    return stable


def reparse_and_replace_chunks(project_id: str, changed_files: set[str]) -> None:
    """changed_files를 재파싱해 chunks.json에서 해당 source_file 청크를 교체한다."""
    from app.agents.parser_agent import ParserAgent

    proj_dir = Path(config.PROJECTS_DIR) / project_id
    files_dir = proj_dir / "files"
    chunks_path = proj_dir / "chunks.json"

    existing = json.loads(chunks_path.read_text(encoding="utf-8")) if chunks_path.exists() else []

    file_type_by_source = {c["source_file"]: c.get("file_type", "note") for c in existing}

    kept = [c for c in existing if c["source_file"] not in changed_files]

    agent = ParserAgent()
    new_chunks: list[dict] = []
    for fname in sorted(changed_files):
        fpath = files_dir / fname
        if not fpath.exists():
            continue
        file_type = file_type_by_source.get(fname, "note")
        parsed = agent.run([str(fpath)], file_type=file_type)
        new_chunks.extend(dataclasses.asdict(c) for c in parsed)

    combined = kept + new_chunks
    chunks_path.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8"
    )
