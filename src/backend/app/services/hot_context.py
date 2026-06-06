import networkx as nx

from app.utils.graph_health import check_isolated_nodes


def _degree(graph: nx.DiGraph, node_id: str) -> int:
    return graph.degree(node_id)


def compose_hot_context(
    graph: nx.DiGraph,
    project_id: str | None = None,
    recent_log: list[str] | None = None,
    top_n: int = 5,
    recent_n: int = 5,
) -> dict:
    """Assemble a compact, deterministic session-entry context from a rendered graph.

    Input graph is assumed already rendered (demote + build_entity_details applied).
    """
    persons: list[tuple[int, str, str, str]] = []
    hubs_raw: dict[str, list[tuple[int, str]]] = {}
    by_type: dict[str, int] = {}
    page_nodes = 0

    for node_id, data in graph.nodes(data=True):
        ntype = data.get("type", "")
        name = data.get("name", "")
        if ntype == "Category" or not name:
            continue
        page_nodes += 1
        by_type[ntype] = by_type.get(ntype, 0) + 1
        deg = _degree(graph, node_id)
        if ntype == "Person":
            persons.append((deg, name, data.get("description", "") or "", ntype))
        else:
            hubs_raw.setdefault(ntype, []).append((deg, name))

    persons.sort(key=lambda x: (-x[0], x[1]))
    persona = [
        {"name": n, "type": t, "degree": d, "description": desc[:80]}
        for (d, n, desc, t) in persons[:top_n]
    ]

    hubs_by_type: dict[str, list[dict]] = {}
    for ntype, items in hubs_raw.items():
        items.sort(key=lambda x: (-x[0], x[1]))
        hubs_by_type[ntype] = [
            {"name": n, "degree": d} for (d, n) in items[:top_n]
        ]

    recent_activity: list[str] = []
    if recent_log:
        headers = [ln for ln in recent_log if ln.startswith("## ")]
        recent_activity = headers[-recent_n:]

    gaps = sorted(
        (
            {"name": iso["name"], "type": iso["type"]}
            for iso in check_isolated_nodes(graph)
            if iso.get("name")
        ),
        key=lambda x: x["name"],
    )[: top_n * 2]

    # total_edges among page (non-Category, named) nodes
    page_node_ids = {
        n for n, d in graph.nodes(data=True)
        if d.get("type") != "Category" and d.get("name")
    }
    total_edges = sum(
        1 for u, v in graph.edges()
        if u in page_node_ids and v in page_node_ids
    )

    return {
        "project_id": project_id,
        "persona": persona,
        "hubs_by_type": hubs_by_type,
        "recent_activity": recent_activity,
        "gaps": gaps,
        "stats": {
            "total_nodes": page_nodes,
            "total_edges": total_edges,
            "by_type": by_type,
        },
    }


def render_hot_markdown(ctx: dict) -> str:
    pid = ctx.get("project_id") or "(unknown)"
    lines = [
        f"# Hot Context — {pid}",
        "",
        "_Auto-generated session primer. Do not edit manually._",
        "",
        "## 주요 인물",
    ]
    if ctx["persona"]:
        for p in ctx["persona"]:
            desc = f" — {p['description']}" if p["description"] else ""
            lines.append(f"- [[{p['name']}]] (deg {p['degree']}){desc}")
    else:
        lines.append("- (없음)")

    lines += ["", "## 핵심 엔티티"]
    if ctx["hubs_by_type"]:
        for ntype in sorted(ctx["hubs_by_type"]):
            lines.append(f"### {ntype}")
            for h in ctx["hubs_by_type"][ntype]:
                lines.append(f"- [[{h['name']}]] (deg {h['degree']})")
    else:
        lines.append("- (없음)")

    lines += ["", "## 최근 활동"]
    if ctx["recent_activity"]:
        for entry in ctx["recent_activity"]:
            lines.append(f"- {entry.lstrip('# ').strip()}")
    else:
        lines.append("- (없음)")

    lines += ["", "## 공백 (연결 보강 후보)"]
    if ctx["gaps"]:
        for g in ctx["gaps"]:
            lines.append(f"- [[{g['name']}]] ({g['type']})")
    else:
        lines.append("- (없음)")

    stats = ctx["stats"]
    by_type = ", ".join(
        f"{t}: {c}" for t, c in sorted(stats["by_type"].items())
    ) or "(없음)"
    lines += [
        "",
        "## 요약",
        f"- Nodes: {stats['total_nodes']}, Edges: {stats['total_edges']}",
        f"- {by_type}",
        "",
    ]
    return "\n".join(lines)
