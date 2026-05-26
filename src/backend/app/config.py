import os
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o"
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    FUZZY_MATCH_THRESHOLD: float = 0.85
    MAX_ONTOLOGY_SAMPLE_CHARS: int = 50000
    PROJECTS_DIR: str = "./projects"
    VAULT_DIR: str = "./vault"
    LOG_DIR: str = "../../logs"
    USER_CONFIG_PATH: str = "./user.json"

    model_config = {"env_file": ".env", "extra": "ignore"}


config = Config()
