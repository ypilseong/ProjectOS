import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import config
from app.models.graph import TextChunk
from app.models.project import Project


QUESTION_TEMPLATE = [
    {
        "field": "primary_goal",
        "question": "이 파일 묶음으로 만들고 싶은 지식 그래프의 주 목적은 무엇인가요?",
        "placeholder": "예: 커리어 포트폴리오, 대학원 지원 준비, 프로젝트 회고, 연구 경력 정리",
    },
    {
        "field": "priority_focus",
        "question": "그래프에서 가장 중요하게 드러나야 하는 대상은 무엇인가요?",
        "placeholder": "예: 프로젝트와 기술 스택, 연구 성과, 지원 동기, 협업 경험, 성장 과정",
    },
    {
        "field": "interpretation_policy",
        "question": "애매한 정보가 있을 때 어떤 방향으로 해석하면 좋을까요?",
        "placeholder": "예: 이력서 중심으로 보수적으로, 면접 답변에 쓸 수 있게 풍부하게, 연구/논문 중심으로",
    },
]

ANSWER_FIELDS = tuple(item["field"] for item in QUESTION_TEMPLATE)


def context_path(project_id: str) -> Path:
    return Path(config.PROJECTS_DIR) / project_id / "ontology_context.json"


def load_context(project_id: str) -> dict[str, Any]:
    path = context_path(project_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_context(project: Project, answers: dict[str, Any]) -> dict[str, Any]:
    cleaned = {
        field: str(answers.get(field) or "").strip()
        for field in ANSWER_FIELDS
    }
    if not all(cleaned.values()):
        missing = [field for field, value in cleaned.items() if not value]
        raise ValueError(f"missing ontology context fields: {', '.join(missing)}")

    payload = {
        "project": _project_payload(project),
        "document_overview": build_document_overview(project.project_id),
        "questions": QUESTION_TEMPLATE,
        "answers": cleaned,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = context_path(project.project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def build_context_payload(project: Project) -> dict[str, Any]:
    saved = load_context(project.project_id)
    answers = saved.get("answers") if isinstance(saved.get("answers"), dict) else {}
    return {
        "project": _project_payload(project),
        "document_overview": build_document_overview(project.project_id),
        "questions": QUESTION_TEMPLATE,
        "answers": {
            field: str(answers.get(field) or "")
            for field in ANSWER_FIELDS
        },
        "is_complete": all(str(answers.get(field) or "").strip() for field in ANSWER_FIELDS),
        "updated_at": saved.get("updated_at"),
    }


def build_prompt_context(project: Project, saved_context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = saved_context if saved_context else load_context(project.project_id)
    answers = context.get("answers") if isinstance(context.get("answers"), dict) else {}
    return {
        "project": _project_payload(project),
        "document_overview": build_document_overview(project.project_id),
        "answers": {
            field: str(answers.get(field) or "").strip()
            for field in ANSWER_FIELDS
        },
    }


def format_prompt_context(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    project = context.get("project") or {}
    overview = context.get("document_overview") or {}
    answers = context.get("answers") or {}
    answer_lines = [
        f"- Primary goal: {answers.get('primary_goal', '')}",
        f"- Priority focus: {answers.get('priority_focus', '')}",
        f"- Interpretation policy: {answers.get('interpretation_policy', '')}",
    ]
    file_lines = []
    for item in overview.get("files", [])[:12]:
        file_lines.append(
            "- "
            f"{item.get('source_file', '')} "
            f"({item.get('file_type', 'unknown')}, {item.get('chunk_count', 0)} chunks): "
            f"{item.get('preview', '')}"
        )
    return "\n".join(
        [
            "Project and ontology intent context:",
            f"- Project name: {project.get('name', '')}",
            f"- Project description: {project.get('description', '')}",
            f"- Document set: {overview.get('summary', '')}",
            "User intent:",
            *answer_lines,
            "File overview:",
            *(file_lines or ["- No parsed files available."]),
        ]
    ).strip()


def build_document_overview(project_id: str) -> dict[str, Any]:
    chunks_path = Path(config.PROJECTS_DIR) / project_id / "chunks.json"
    if not chunks_path.exists():
        return {
            "file_count": 0,
            "total_chunks": 0,
            "file_types": {},
            "summary": "No parsed files are available yet.",
            "files": [],
        }

    try:
        raw_chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        chunks = [TextChunk(**item) for item in raw_chunks]
    except Exception:
        chunks = []

    by_file: dict[str, list[TextChunk]] = defaultdict(list)
    file_types = Counter()
    for chunk in chunks:
        by_file[chunk.source_file].append(chunk)
        file_types[chunk.file_type or "unknown"] += 1

    files = []
    for source_file, file_chunks in sorted(by_file.items()):
        type_counts = Counter(chunk.file_type or "unknown" for chunk in file_chunks)
        file_type = type_counts.most_common(1)[0][0] if type_counts else "unknown"
        preview = " ".join(chunk.text.strip().replace("\n", " ") for chunk in file_chunks[:2])
        files.append(
            {
                "source_file": source_file,
                "file_type": file_type,
                "chunk_count": len(file_chunks),
                "preview": preview[:500],
            }
        )

    type_summary = ", ".join(
        f"{name} {count}" for name, count in sorted(file_types.items())
    )
    summary = (
        f"{len(files)} parsed file(s), {len(chunks)} chunk(s)"
        + (f"; document types: {type_summary}" if type_summary else "")
    )
    return {
        "file_count": len(files),
        "total_chunks": len(chunks),
        "file_types": dict(sorted(file_types.items())),
        "summary": summary,
        "files": files,
    }


def _project_payload(project: Project) -> dict[str, str]:
    return {
        "project_id": project.project_id,
        "name": project.name,
        "description": project.description or "",
    }
