import json
import re
from pathlib import Path

import networkx as nx

from app.agents.obsidian_writer_agent import TYPE_TO_FOLDER
from app.config import config
from app.utils.graph_patch import apply_project_graph_patch
from app.utils.graph_restructure import build_entity_details, demote_project_context_nodes
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm: dict = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        fm[key.strip()] = val.strip().strip('"')
    return fm


def _section_body(text: str, title: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(title)}\s*$", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return ""
    start = m.end()
    nxt = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + nxt.start() if nxt else len(text)
    return text[start:end].strip()


def parse_vault_page(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    ntype = fm.get("type")
    name = fm.get("name")
    if not ntype or not name:
        return None

    overview = _section_body(text, "Overview")
    if overview == "(설명 없음)":
        overview = ""

    connections: list[dict] = []
    for line in _section_body(text, "Connections").splitlines():
        line = line.strip()
        m_in = re.match(r"^-\s*←\s*(.*?):\s*\[\[([^\]]+)\]\]", line)
        if m_in:
            connections.append({"relation": m_in.group(1).strip(),
                                "direction": "in", "other": m_in.group(2).strip()})
            continue
        m_out = re.match(r"^-\s*(.*?):\s*\[\[([^\]]+)\]\]", line)
        if m_out:
            connections.append({"relation": m_out.group(1).strip(),
                                "direction": "out", "other": m_out.group(2).strip()})
    return {"type": ntype, "name": name, "description": overview,
            "connections": connections}
