import networkx as nx

from app.utils.logger import get_logger
from app.utils.user_config import get_user_name_variants, load_user_config

logger = get_logger(__name__)

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
        # Group outgoing edges by target node type
        by_type: dict[str, list[tuple[str, str, dict]]] = {}
        for _, t, data in list(graph.out_edges(person_id, data=True)):
            ttype = graph.nodes[t].get("type", "")
            if ttype == "Person" and t not in center_ids:
                # Other Person nodes → People hub
                by_type.setdefault("__Person__", []).append((person_id, t, data))
            elif ttype in _HUB_CONFIG:
                by_type.setdefault(ttype, []).append((person_id, t, data))

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
                graph.remove_edge(person_id, t)

    if hubs_created:
        logger.info(f"Category hubs: added {hubs_created} hub node(s)")
    return graph, hubs_created
