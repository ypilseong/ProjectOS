from pathlib import Path

from app.config import config
from app.utils.file_parser import extract_text
from app.utils.llm_client import LLMClient

SUPPORTED_FILE_TYPES = ["cv", "paper", "report", "memo", "email", "note"]


def inbox_root() -> Path:
    root = Path(config.INBOX_DIR).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_inbox_path(relative_path: str = "") -> Path:
    root = inbox_root()
    rel = Path(str(relative_path or "."))
    if rel.is_absolute():
        raise ValueError("relative_path must be relative")
    resolved = (root / rel).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("relative_path escapes INBOX_DIR")
    return resolved


def inbox_relative(path: Path) -> str:
    return path.resolve().relative_to(inbox_root()).as_posix()


def preview_inbox_file(relative_path: str, max_chars: int | None = None) -> dict:
    path = resolve_inbox_path(relative_path)
    if not path.exists():
        raise ValueError("Inbox file not found")
    if not path.is_file():
        raise ValueError("Inbox path is not a file")

    limit = max(200, int(max_chars or config.INBOX_PREVIEW_CHARS))
    text = ""
    page_count = None
    try:
        pages = extract_text(str(path))
        page_count = len(pages)
        text = "\n\n".join(page_text for page_text, _ in pages)
    except Exception as exc:
        text = f"[preview unavailable: {exc}]"

    stat = path.stat()
    preview = text[:limit]
    return {
        "relative_path": inbox_relative(path),
        "filename": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "modified_time": stat.st_mtime,
        "page_count": page_count,
        "preview_chars": len(preview),
        "text_preview": preview,
    }


def _classification_prompt(preview: dict) -> str:
    return f"""You classify documents for ProjectOS graph extraction.

Choose exactly one file_type from this list:
- cv: resumes, CVs, career profiles, academic/professional biographies.
- paper: research papers, publications, preprints, manuscripts, theses, articles with abstracts/references.
- report: structured business, project, technical, research, status, or analysis reports.
- memo: informal notes, meeting notes, todos, drafts, personal memos, short planning documents.
- email: email messages or exported message threads.
- note: fallback for documents that do not fit the other categories.

Use the text preview and metadata. Do not rely on the filename alone.
If the preview is too short or unavailable, choose the safest fallback and lower confidence.
Return only valid JSON with this exact shape:
{{
  "file_type": "cv|paper|report|memo|email|note",
  "confidence": 0.0,
  "reason": "brief reason"
}}

Metadata:
filename: {preview["filename"]}
extension: {preview["extension"]}
size_bytes: {preview["size_bytes"]}
page_count: {preview.get("page_count")}

Text preview:
{preview["text_preview"]}
"""


async def classify_inbox_file(relative_path: str, max_chars: int | None = None) -> dict:
    preview = preview_inbox_file(relative_path, max_chars=max_chars)
    llm = LLMClient(backend="local")
    result = await llm.chat_json(
        [{"role": "user", "content": _classification_prompt(preview)}],
        request_timeout=45,
    )
    file_type = str(result.get("file_type") or "note").strip().lower()
    if file_type not in SUPPORTED_FILE_TYPES:
        file_type = "note"
    try:
        confidence = float(result.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))
    return {
        **preview,
        "suggested_file_type": file_type,
        "confidence": confidence,
        "classification_reason": str(result.get("reason") or ""),
    }


async def list_inbox(
    relative_path: str = "",
    *,
    recursive: bool = False,
    max_items: int = 50,
    classify_files: bool = True,
) -> dict:
    base = resolve_inbox_path(relative_path)
    if not base.exists():
        raise ValueError("Inbox path not found")
    if not base.is_dir():
        raise ValueError("Inbox path is not a directory")

    pattern = "**/*" if recursive else "*"
    candidates = sorted(base.glob(pattern), key=lambda p: (not p.is_dir(), p.name.lower()))
    entries = []
    for path in candidates[: max(1, max_items)]:
        stat = path.stat()
        entry = {
            "relative_path": inbox_relative(path),
            "name": path.name,
            "kind": "directory" if path.is_dir() else "file",
            "size_bytes": stat.st_size,
            "modified_time": stat.st_mtime,
        }
        if path.is_file():
            entry["extension"] = path.suffix.lower()
            if classify_files:
                try:
                    classified = await classify_inbox_file(inbox_relative(path))
                    entry.update({
                        "suggested_file_type": classified["suggested_file_type"],
                        "confidence": classified["confidence"],
                        "classification_reason": classified["classification_reason"],
                        "preview_chars": classified["preview_chars"],
                    })
                except Exception as exc:
                    entry.update({
                        "suggested_file_type": "note",
                        "confidence": 0.0,
                        "classification_reason": f"classification failed: {exc}",
                    })
        entries.append(entry)

    return {
        "inbox_dir": str(inbox_root()),
        "relative_path": inbox_relative(base) if base != inbox_root() else "",
        "recursive": recursive,
        "entries": entries,
        "truncated": len(candidates) > len(entries),
    }


async def read_inbox_file_for_ingest(relative_path: str, file_type: str | None = None) -> dict:
    path = resolve_inbox_path(relative_path)
    if not path.exists():
        raise ValueError("Inbox file not found")
    if not path.is_file():
        raise ValueError("Inbox path is not a file")

    selected_type = str(file_type or "auto").strip().lower()
    classification = None
    if selected_type in {"", "auto"}:
        classification = await classify_inbox_file(inbox_relative(path))
        selected_type = classification["suggested_file_type"]
    if selected_type not in SUPPORTED_FILE_TYPES:
        raise ValueError(f"file_type must be one of: {', '.join(SUPPORTED_FILE_TYPES)}")

    return {
        "filename": path.name,
        "relative_path": inbox_relative(path),
        "content": path.read_bytes(),
        "file_type": selected_type,
        "classification": classification,
    }
