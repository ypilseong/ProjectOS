import uuid
from pathlib import Path
from typing import Callable
from app.models.graph import TextChunk
from app.utils.file_parser import extract_text
from app.config import config
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ParserAgent:
    def __init__(self):
        self.chunk_size = config.CHUNK_SIZE
        self.overlap = config.CHUNK_OVERLAP

    def run(
        self,
        file_paths: list[str],
        file_type: str = "note",
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[TextChunk]:
        chunks = []
        total = len(file_paths)
        for i, path in enumerate(file_paths, start=1):
            logger.info(f"Parsing {path}")
            try:
                pages = extract_text(path)
                source_file = Path(path).name
                for text, page_num in pages:
                    chunks.extend(self._chunk_text(text, source_file, file_type, page_num))
            except Exception as e:
                logger.error(f"Failed to parse {path}: {e}")
            if progress_callback:
                progress_callback(i, total, Path(path).name)
        return chunks

    def _chunk_text(
        self, text: str, source_file: str, file_type: str, page_num
    ) -> list[TextChunk]:
        chunks = []
        offset = 0
        while offset < len(text):
            end = min(offset + self.chunk_size, len(text))
            chunk_text = text[offset:end].strip()
            if chunk_text:
                chunks.append(TextChunk(
                    chunk_id=str(uuid.uuid4()),
                    text=chunk_text,
                    source_file=source_file,
                    file_type=file_type,
                    page_num=page_num,
                    char_offset=offset,
                ))
            offset += self.chunk_size - self.overlap
        return chunks
