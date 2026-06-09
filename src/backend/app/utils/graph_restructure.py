import networkx as nx

from app.utils.logger import get_logger
from app.utils.user_config import get_user_name_variants, load_user_config

logger = get_logger(__name__)


def is_meta_node(data: dict) -> bool:
    """True for provenance/meta nodes that must be excluded from career-graph logic."""
    return bool(data.get("meta")) or data.get("type") in {"Category", "Capture"}

# Maps individual node type → (hub node id, hub display name)
_HUB_CONFIG: dict[str, tuple[str, str]] = {
    "Achievement":  ("Category:Achievements",  "Achievements"),
    "Skill":        ("Category:Skills",        "Skills"),
    "Project":      ("Category:Projects",      "Projects"),
    "Role":         ("Category:Roles",         "Roles"),
    "Organization": ("Category:Organizations", "Organizations"),
    "Institution":  ("Category:Institutions",  "Institutions"),
    "Event":        ("Category:Events",        "Events"),
    "Publication":  ("Category:Publications",  "Publications"),
}

_PEOPLE_HUB_ID = "Category:People"
_PEOPLE_HUB_NAME = "People"

_CONTEXT_NODE_TYPES = {"Skill", "Project", "Achievement", "Event"}
_CONTEXT_NAME_PATTERNS = (
    "architecture",
    "backend architecture",
    "frontend implementation",
    "generation",
    "export",
    "implementation",
    "pipeline",
    "workflow",
    "visualization",
)
_KNOWN_SKILL_MENTIONS = (
    "FastAPI",
    "NetworkX",
    "Vue",
    "D3.js",
    "D3",
    "Python",
    "JavaScript",
    "TypeScript",
    "React",
    "Node.js",
    "Docker",
    "PostgreSQL",
    "SQLite",
    "FastAPI",
)


def _load_user_person_ids(graph: nx.DiGraph) -> set[str]:
    """Return node IDs that belong to the user (matched via user.json name variants)."""
    data = load_user_config()
    if not data:
        return set()

    variants = set(get_user_name_variants(data))
    return {
        n for n, d in graph.nodes(data=True)
        if d.get("type") == "Person" and d.get("name", "").strip().lower() in variants
    }


def _entity_name(graph: nx.DiGraph, node_id: str) -> str:
    return graph.nodes[node_id].get("name") or node_id


def _merge_list_attr(graph: nx.DiGraph, node_id: str, attr: str, values: list[str]) -> None:
    existing = set(graph.nodes[node_id].get(attr, []))
    existing.update(v for v in values if v)
    graph.nodes[node_id][attr] = sorted(existing)


def _node_sources(graph: nx.DiGraph, node_id: str) -> dict:
    data = graph.nodes[node_id]
    return {
        "source_files": list(data.get("source_files", [])),
        "source_chunk_ids": list(data.get("source_chunk_ids", [])),
    }


def _looks_like_project_context(name: str) -> bool:
    lowered = name.strip().lower()
    if not lowered:
        return False
    if any(pattern in lowered for pattern in _CONTEXT_NAME_PATTERNS):
        return True
    return False


def _skill_mentions(name: str) -> list[str]:
    lowered = name.lower()
    found: list[str] = []
    for skill in _KNOWN_SKILL_MENTIONS:
        if skill.lower() in lowered and skill not in found:
            found.append(skill)
    if "d3" in lowered and "D3.js" not in found and "D3" not in found:
        found.append("D3.js")
    return found


def demote_project_context_nodes(graph: nx.DiGraph) -> tuple[nx.DiGraph, int]:
    """Move project implementation/detail leaves out of the graph node set.

    The graph should show independent primary entities. Leaf nodes that look like
    project features, outputs, or implementation notes are kept as structured
    project detail evidence instead of being rendered as extra hops.
    """
    demoted = 0
    for node_id, data in list(graph.nodes(data=True)):
        if data.get("type") not in _CONTEXT_NODE_TYPES:
            continue
        name = data.get("name", "")
        if not _looks_like_project_context(name):
            continue

        neighbors = set(graph.predecessors(node_id)) | set(graph.successors(node_id))
        project_neighbors = [
            neighbor
            for neighbor in neighbors
            if graph.nodes[neighbor].get("type") == "Project"
        ]
        non_category_neighbors = [
            neighbor
            for neighbor in neighbors
            if graph.nodes[neighbor].get("type") != "Category"
        ]
        if len(project_neighbors) != 1 or len(non_category_neighbors) > 1:
            continue

        project_id = project_neighbors[0]
        relation = ""
        if graph.has_edge(project_id, node_id):
            relation = graph.edges[project_id, node_id].get("relation", "")
        elif graph.has_edge(node_id, project_id):
            relation = graph.edges[node_id, project_id].get("relation", "")

        context_items = list(graph.nodes[project_id].get("context_items", []))
        context_items.append({
            "name": name,
            "type": data.get("type", "Unknown"),
            "relation": relation,
            **_node_sources(graph, node_id),
        })
        graph.nodes[project_id]["context_items"] = context_items

        for skill_name in _skill_mentions(name):
            skill_id = f"Skill:{skill_name}"
            if skill_id not in graph:
                graph.add_node(
                    skill_id,
                    type="Skill",
                    name=skill_name,
                    description=f"Skill mentioned in {name}",
                    source_files=list(data.get("source_files", [])),
                    source_chunk_ids=list(data.get("source_chunk_ids", [])),
                    attributes={},
                )
            else:
                _merge_list_attr(graph, skill_id, "source_files", data.get("source_files", []))
                _merge_list_attr(graph, skill_id, "source_chunk_ids", data.get("source_chunk_ids", []))
            if not graph.has_edge(project_id, skill_id):
                graph.add_edge(project_id, skill_id, relation="USES_SKILL", confidence=1.0)

        graph.remove_node(node_id)
        demoted += 1

    if demoted:
        logger.info(f"Project context demotion: removed {demoted} context node(s)")
    return graph, demoted


def _append_unique(sections: dict[str, list[str]], title: str, item: str) -> None:
    if item and item not in sections.setdefault(title, []):
        sections[title].append(item)


def _connected_by_type(graph: nx.DiGraph, node_id: str) -> list[tuple[str, str, str, str]]:
    connected: list[tuple[str, str, str, str]] = []
    for target_id in graph.successors(node_id):
        target = graph.nodes[target_id]
        if target.get("type") == "Category":
            for primary_id in graph.successors(target_id):
                primary = graph.nodes[primary_id]
                if primary.get("type") == "Category":
                    continue
                relation = graph.edges[target_id, primary_id].get("relation", "")
                connected.append((
                    primary.get("type", "Unknown"),
                    _entity_name(graph, primary_id),
                    relation,
                    "out",
                ))
            continue
        relation = graph.edges[node_id, target_id].get("relation", "")
        connected.append((target.get("type", "Unknown"), _entity_name(graph, target_id), relation, "out"))
    for source_id in graph.predecessors(node_id):
        source = graph.nodes[source_id]
        if source.get("type") == "Category":
            continue
        relation = graph.edges[source_id, node_id].get("relation", "")
        connected.append((source.get("type", "Unknown"), _entity_name(graph, source_id), relation, "in"))
    return connected


def build_entity_details(graph: nx.DiGraph) -> tuple[nx.DiGraph, int]:
    """Attach type-specific structured detail summaries to every primary entity."""
    changed = 0
    for node_id, data in graph.nodes(data=True):
        ntype = data.get("type", "Unknown")
        if ntype == "Category":
            continue

        sections: dict[str, list[str]] = {}
        for section in (data.get("details") or {}).get("sections", []):
            title = section.get("title", "")
            for item in section.get("items", []):
                _append_unique(sections, title, item)
        for target_type, name, relation, _direction in _connected_by_type(graph, node_id):
            label = f"{name} ({relation})" if relation else name
            if ntype == "Person":
                if target_type == "Project":
                    _append_unique(sections, "관련 프로젝트", label)
                elif target_type in {"Organization", "Institution"}:
                    _append_unique(sections, "소속 조직", label)
                elif target_type == "Role":
                    _append_unique(sections, "역할", label)
                elif target_type == "Skill":
                    _append_unique(sections, "보유 기술", label)
                elif target_type == "Achievement":
                    _append_unique(sections, "주요 성과", label)
            elif ntype == "Project":
                if target_type == "Skill":
                    _append_unique(sections, "사용 기술", label)
                elif target_type == "Person":
                    _append_unique(sections, "관련 인물", label)
                elif target_type in {"Organization", "Institution"}:
                    _append_unique(sections, "관련 조직", label)
                elif target_type == "Achievement":
                    _append_unique(sections, "산출물", label)
            elif ntype == "Skill":
                if target_type == "Project":
                    _append_unique(sections, "사용된 프로젝트", label)
                elif target_type == "Role":
                    _append_unique(sections, "관련 역할", label)
                elif target_type == "Achievement":
                    _append_unique(sections, "관련 성과", label)
            elif ntype in {"Organization", "Institution"}:
                if target_type == "Person":
                    _append_unique(sections, "관련 인물", label)
                elif target_type == "Project":
                    _append_unique(sections, "관련 프로젝트", label)
                elif target_type == "Role":
                    _append_unique(sections, "역할 또는 소속 관계", label)
            elif ntype == "Publication":
                if target_type == "Person":
                    _append_unique(sections, "저자", label)
                elif target_type in {"Organization", "Institution"}:
                    _append_unique(sections, "관련 기관", label)
                elif target_type == "Project":
                    _append_unique(sections, "관련 프로젝트", label)
                elif target_type == "Skill":
                    _append_unique(sections, "주제", label)
            elif ntype == "Achievement":
                if target_type == "Person":
                    _append_unique(sections, "관련 인물", label)
                elif target_type == "Project":
                    _append_unique(sections, "관련 프로젝트", label)
                elif target_type == "Skill":
                    _append_unique(sections, "의미", label)

        if ntype == "Project":
            for item in data.get("context_items", []):
                title = "주요 기능"
                relation = str(item.get("relation") or "").upper()
                if any(token in relation for token in ("OUTPUT", "PRODUCED", "PUBLISHED")):
                    title = "산출물"
                _append_unique(sections, title, item.get("name", ""))

        desc = data.get("description")
        if desc:
            _append_unique(sections, "특이사항", desc)

        sources = []
        source_files = data.get("source_files", [])
        if source_files:
            sources.append(", ".join(source_files))
        for item in data.get("context_items", []):
            if item.get("source_files"):
                sources.append(f"{item.get('name')}: {', '.join(item['source_files'])}")
        for source in sources:
            _append_unique(sections, "근거 source", source)

        detail = {
            "type": ntype,
            "sections": [
                {"title": title, "items": items}
                for title, items in sections.items()
                if items
            ],
        }
        if data.get("details") != detail:
            data["details"] = detail
            changed += 1

    return graph, changed


def add_category_hubs(graph: nx.DiGraph) -> tuple[nx.DiGraph, int]:
    """Insert category hub nodes between Person nodes and their 1-hop neighbors.

    Before:  Person:양필성 → Skill:NLP
                           → Skill:Python
                           → Person:인소영

    After:   Person:양필성 → Category:Skills → Skill:NLP
                                             → Skill:Python
                           → Category:People → Person:인소영

    - User person nodes (matched via user.json) are treated as center nodes.
    - Other Person nodes reachable from the user are grouped under Category:People.
    - All cross-type edges between non-Person nodes (e.g. Skill → Project) are preserved.

    Returns the modified graph and the number of hub nodes created.
    """
    user_ids = _load_user_person_ids(graph)
    # Fall back to all Person nodes if user.json is unavailable
    center_ids = user_ids if user_ids else {
        n for n, d in graph.nodes(data=True) if d.get("type") == "Person"
    }
    hubs_created = 0

    for person_id in list(center_ids):
        # Every independent primary entity should be visible as User -> Category -> Entity.
        # Direct Person -> Entity edges keep their relation on the Category -> Entity edge;
        # semantic edges between primary entities are preserved separately.
        by_type: dict[str, list[tuple[str, str, dict]]] = {}
        for node_id, data in list(graph.nodes(data=True)):
            if node_id == person_id or data.get("type") == "Category":
                continue
            ttype = data.get("type", "")
            direct_edge_data = (
                dict(graph.edges[person_id, node_id])
                if graph.has_edge(person_id, node_id)
                else {"relation": "INCLUDES"}
            )
            if ttype == "Person" and node_id not in center_ids:
                by_type.setdefault("__Person__", []).append((person_id, node_id, direct_edge_data))
            elif ttype in _HUB_CONFIG:
                by_type.setdefault(ttype, []).append((person_id, node_id, direct_edge_data))

        for ttype, edges in by_type.items():
            if ttype == "__Person__":
                hub_id, hub_name = _PEOPLE_HUB_ID, _PEOPLE_HUB_NAME
            else:
                hub_id, hub_name = _HUB_CONFIG[ttype]

            if hub_id not in graph:
                graph.add_node(hub_id, type="Category", name=hub_name, source_files=[])
                hubs_created += 1
                logger.info(f"Category hub created: {hub_id}")

            if not graph.has_edge(person_id, hub_id):
                graph.add_edge(person_id, hub_id, relation="HAS")

            for _, t, data in edges:
                if not graph.has_edge(hub_id, t):
                    graph.add_edge(hub_id, t, relation=data.get("relation", "INCLUDES"))
                if graph.has_edge(person_id, t):
                    graph.remove_edge(person_id, t)

    if hubs_created:
        logger.info(f"Category hubs: added {hubs_created} hub node(s)")
    return graph, hubs_created
