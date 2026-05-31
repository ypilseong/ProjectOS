import os
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    LLM_BACKEND: str = "local"  # "local" | "claude_code"
    GRAPH_EXTRACTION_BACKEND: str = "local"  # "local" | "claude_code"
    GRAPH_BUILD_MODE: str = "chunk"  # "chunk" | "claude_task"
    CLAUDE_CODE_MODEL: str = ""
    CLAUDE_TASKS_DIR: str = "/tmp/projectos-claude-tasks"
    CLAUDE_TASK_BARE: bool = False
    CLAUDE_TASK_TIMEOUT: float = 600.0
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o"
    LLM_REQUEST_TIMEOUT: float = 120.0
    LLM_TEMPERATURE: float = 1.0
    LLM_TOP_P: float = 0.95
    LLM_TOP_K: int = 20
    LLM_MIN_P: float = 0.0
    LLM_PRESENCE_PENALTY: float = 1.5
    LLM_REPETITION_PENALTY: float = 1.0
    LLM_THINKING_MODE: bool = True
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    FUZZY_MATCH_THRESHOLD: float = 0.85
    MAX_ONTOLOGY_SAMPLE_CHARS: int = 50000
    PROJECTS_DIR: str = "./projects"
    VAULT_DIR: str = "./vault"
    LOG_DIR: str = "../../logs"
    USER_CONFIG_PATH: str = "./user.json"
    SETTINGS_PATH: str = "./settings.json"
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    SEMANTIC_DEDUP_THRESHOLD: float = 0.88

    model_config = {"env_file": ".env", "extra": "ignore"}


config = Config()
