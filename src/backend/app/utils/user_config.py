import json
from pathlib import Path

from app.config import config


def load_user_config() -> dict:
    try:
        return json.loads(Path(config.USER_CONFIG_PATH).read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_user_name_values(data: dict | None = None) -> list[str]:
    data = data if data is not None else load_user_config()
    values: list[str] = []

    for key in ("name", "display_name"):
        value = data.get(key, "")
        if isinstance(value, str) and value.strip():
            values.append(value.strip())

    aliases = data.get("aliases", [])
    if isinstance(aliases, str):
        aliases = [aliases]
    if isinstance(aliases, list):
        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                values.append(alias.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        lowered = value.lower()
        if lowered not in seen:
            seen.add(lowered)
            deduped.append(value)
    return deduped


def get_user_name_variants(data: dict | None = None) -> dict[str, str]:
    return {value.lower(): value for value in get_user_name_values(data)}
