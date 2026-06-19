from __future__ import annotations

import json
from pathlib import Path

from app.config import config


def _denylist_path(project_id: str) -> Path:
    return Path(config.PROJECTS_DIR) / project_id / "merge_denylist.json"


def load_denylist(project_id: str) -> set[frozenset]:
    """Load the set of rejected merge pairs for a project.

    Each pair is a frozenset of two node ids. Missing or unreadable files
    yield an empty set so callers can treat "no denylist" as "no exclusions".
    """
    path = _denylist_path(project_id)
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    pairs: set[frozenset] = set()
    for entry in raw:
        if isinstance(entry, list) and len(entry) == 2:
            pairs.add(frozenset(entry))
    return pairs


def add_denied_pair(project_id: str, id_a: str, id_b: str) -> None:
    """Persist a rejected merge pair so it is never re-suggested."""
    denylist = load_denylist(project_id)
    denylist.add(frozenset({id_a, id_b}))

    serialized = sorted(sorted(pair) for pair in denylist)

    path = _denylist_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(serialized, indent=2, ensure_ascii=False), encoding="utf-8"
    )
