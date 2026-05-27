import logging
from pathlib import Path

from app.config import config


LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"


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
