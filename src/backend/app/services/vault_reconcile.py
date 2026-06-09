import json
import re
from pathlib import Path

import networkx as nx

from app.agents.obsidian_writer_agent import TYPE_TO_FOLDER
from app.config import config
from app.utils.graph_patch import apply_project_graph_patch
from app.utils.graph_restructure import (
    build_entity_details,
    demote_project_context_nodes,
    is_meta_node,
)
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


def _load_graph(graph_path: Path) -> nx.DiGraph:
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    return nx.node_link_graph(data)


def _rendered_graph(graph: nx.DiGraph) -> nx.DiGraph:
    g = graph.copy()
    g, _ = demote_project_context_nodes(g)
    g, _ = build_entity_details(g)
    return g


def _read_vault_pages(vault: Path) -> dict[tuple[str, str], dict]:
    pages: dict[tuple[str, str], dict] = {}
    for folder in set(TYPE_TO_FOLDER.values()) | {"Misc"}:
        d = vault / folder
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            parsed = parse_vault_page(md)
            if parsed:
                pages[(parsed["type"], parsed["name"])] = parsed
    return pages


def _rendered_pages(rendered: nx.DiGraph) -> dict[tuple[str, str], dict]:
    pages: dict[tuple[str, str], dict] = {}
    for node_id, data in rendered.nodes(data=True):
        if is_meta_node(data):
            continue
        name = data.get("name")
        if not name:
            continue
        pages[(data.get("type"), name)] = {
            "id": node_id,
            "description": data.get("description", "") or "",
        }
    return pages


def _rendered_edges(rendered: nx.DiGraph) -> set[tuple[str, str, str]]:
    edges: set[tuple[str, str, str]] = set()
    for u, v, d in rendered.edges(data=True):
        un = rendered.nodes[u].get("name")
        vn = rendered.nodes[v].get("name")
        if not un or not vn:
            continue
        if is_meta_node(rendered.nodes[u]) or is_meta_node(rendered.nodes[v]):
            continue
        edges.add((un, vn, str(d.get("relation", "")).strip().upper()))
    return edges


def _vault_edges(pages: dict[tuple[str, str], dict]) -> set[tuple[str, str, str]]:
    edges: set[tuple[str, str, str]] = set()
    for (_t, pname), parsed in pages.items():
        for c in parsed["connections"]:
            rel = str(c["relation"]).strip().upper()
            if c["direction"] == "out":
                edges.add((pname, c["other"], rel))
            else:
                edges.add((c["other"], pname, rel))
    return edges


def _name_index(graph: nx.DiGraph) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for nid, data in graph.nodes(data=True):
        nm = data.get("name")
        if nm:
            idx.setdefault(nm, []).append(nid)
    return idx


def diff_vault_against_graph(project_id: str) -> dict:
    graph_path = Path(config.PROJECTS_DIR) / project_id / "graph.json"
    if not graph_path.exists():
        raise ValueError("Graph not built yet")
    vault = Path(config.VAULT_DIR) / project_id

    graph = _load_graph(graph_path)
    rendered = _rendered_graph(graph)

    expected = _rendered_pages(rendered)
    vault_pages = _read_vault_pages(vault) if vault.is_dir() else {}
    g_nodes = {
        (data.get("type"), data.get("name")): nid
        for nid, data in graph.nodes(data=True)
        if data.get("name")
    }
    name_idx = _name_index(graph)
    new_names = {nm for (_t, nm) in vault_pages if (_t, nm) not in g_nodes}

    patch: dict = {
        "nodes_add": [], "nodes_update": [], "nodes_delete": [],
        "edges_add": [], "edges_delete": [],
    }

    for key, parsed in vault_pages.items():
        if key in expected and key in g_nodes:
            current = graph.nodes[g_nodes[key]].get("description", "") or ""
            if parsed["description"] != current:
                patch["nodes_update"].append({
                    "type": key[0], "name": key[1],
                    "set": {"description": parsed["description"]},
                })
        elif key not in expected and key not in g_nodes:
            patch["nodes_add"].append({
                "type": key[0], "name": key[1],
                "description": parsed["description"],
            })

    for key in expected:
        if key not in vault_pages and key in g_nodes:
            patch["nodes_delete"].append({"type": key[0], "name": key[1]})

    rendered_e = _rendered_edges(rendered)
    vault_e = _vault_edges(vault_pages)

    def _unique(nm: str) -> bool:
        return len(name_idx.get(nm, [])) == 1

    def _resolvable(nm: str) -> bool:
        return _unique(nm) or nm in new_names

    for (sn, tn, rel) in (vault_e - rendered_e):
        if _resolvable(sn) and _resolvable(tn):
            patch["edges_add"].append({
                "source_name": sn, "target_name": tn,
                "relation": rel, "confidence": 1.0,
            })

    for (sn, tn, rel) in (rendered_e - vault_e):
        if _unique(sn) and _unique(tn):
            su, tv = name_idx[sn][0], name_idx[tn][0]
            if graph.has_edge(su, tv):
                existing = str(graph.edges[su, tv].get("relation", "")).strip().upper()
                if existing == rel:
                    patch["edges_delete"].append({
                        "source_name": sn, "target_name": tn, "relation": rel,
                    })

    return patch


def reconcile_vault(project_id: str, apply: bool = False) -> dict:
    patch = diff_vault_against_graph(project_id)
    summary = {key: len(patch[key]) for key in patch}
    if not apply:
        logger.info(f"reconcile_vault dry-run for {project_id}: {summary}")
        return {"project_id": project_id, "applied": False,
                "patch": patch, "summary": summary}
    result = apply_project_graph_patch(project_id, patch)
    logger.info(f"reconcile_vault applied for {project_id}: {result['changes']}")
    return {"project_id": project_id, "applied": True,
            "patch": patch, "summary": summary, "result": result}
