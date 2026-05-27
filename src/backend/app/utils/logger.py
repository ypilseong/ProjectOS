import logging
import re
from contextvars import ContextVar
from pathlib import Path

from app.config import config


LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
_PROJECT_ID: ContextVar[str | None] = ContextVar("project_id", default=None)


def _safe_project_id(project_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", project_id) or "unknown"


def set_log_project(project_id: str):
    return _PROJECT_ID.set(project_id)


def reset_log_project(token):
    _PROJECT_ID.reset(token)


def project_log_dir(project_id: str) -> Path:
    return Path(config.LOG_DIR) / "projects" / _safe_project_id(project_id)


class ProjectFileHandler(logging.Handler):
    """Route records emitted inside a project context to that project's log file."""

    def __init__(self):
        super().__init__(logging.INFO)
        self._handlers: dict[str, logging.FileHandler] = {}

    def emit(self, record: logging.LogRecord):
        project_id = getattr(record, "project_id", None) or _PROJECT_ID.get()
        if not project_id:
            return

        log_dir = project_log_dir(str(project_id))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = (log_dir / "projectos.log").resolve()
        key = str(log_path)
        handler = self._handlers.get(key)
        if handler is None:
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter(LOG_FORMAT))
            self._handlers[key] = handler
        handler.emit(record)


def configure_logging():
    log_dir = Path(config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "projectos.log"

    def has_file_handler(logger: logging.Logger) -> bool:
        return any(
            isinstance(handler, logging.FileHandler)
            and Path(handler.baseFilename) == log_path.resolve()
            for handler in logger.handlers
        )

    def attach_file_handler(logger: logging.Logger):
        logger.setLevel(logging.INFO)
        if not has_file_handler(logger):
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
            logger.addHandler(file_handler)
        if not any(isinstance(handler, ProjectFileHandler) for handler in logger.handlers):
            logger.addHandler(ProjectFileHandler())

    attach_file_handler(logging.getLogger())
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        attach_file_handler(logger)
        logger.propagate = False

    for logger_name in ("httpx", "watchfiles", "watchfiles.main"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
