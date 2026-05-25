from pathlib import Path
from typing import Optional


def extract_text_from_pdf(path: str) -> list[tuple[str, int]]:
    import fitz  # PyMuPDF
    doc = fitz.open(path)
    return [(page.get_text(), i + 1) for i, page in enumerate(doc)]


def extract_text_from_docx(path: str) -> str:
    from docx import Document
    doc = Document(path)
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())


def extract_text_from_txt(path: str) -> str:
    from charset_normalizer import from_path
    result = from_path(path).best()
    return str(result) if result else Path(path).read_text(encoding="utf-8", errors="replace")


def extract_text(path: str) -> list[tuple[str, Optional[int]]]:
    """Extract text from a file. Returns list of (text, page_num) tuples."""
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    elif suffix == ".docx":
        return [(extract_text_from_docx(path), None)]
    else:
        return [(extract_text_from_txt(path), None)]
