import json
from pathlib import Path

_HASHES_FILE = "hashes.json"
_ONTOLOGY_KEY = "__ontology__"


class DocumentHashStore:
    """Tracks MD5 hashes of source files and ontology to support incremental graph builds."""

    def __init__(self, project_dir: Path):
        self._path = Path(project_dir) / _HASHES_FILE
        self._stored: dict[str, str] = {}
        self._pending: dict[str, str] = {}
        if self._path.exists():
            try:
                self._stored = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._stored = {}

    def update(self, filename: str, file_hash: str) -> None:
        self._pending[filename] = file_hash

    def update_ontology(self, ontology_hash: str) -> None:
        self._pending[_ONTOLOGY_KEY] = ontology_hash

    def save(self) -> None:
        merged = {**self._stored, **self._pending}
        self._path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        self._stored = merged

    def get_changed_files(self, filenames: list[str]) -> list[str]:
        """Return filenames whose hash differs from the stored hash.

        If the ontology hash changed, all files are considered changed.
        """
        stored_ont = self._stored.get(_ONTOLOGY_KEY)
        pending_ont = self._pending.get(_ONTOLOGY_KEY)
        ontology_changed = pending_ont is not None and pending_ont != stored_ont

        changed = []
        for fname in filenames:
            stored = self._stored.get(fname)
            pending = self._pending.get(fname)
            current = pending if pending is not None else stored
            if ontology_changed or stored is None or current != stored:
                changed.append(fname)
        return changed
