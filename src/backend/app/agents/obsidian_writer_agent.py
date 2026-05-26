import json
import re
from datetime import date
from pathlib import Path

import networkx as nx

from app.config import config
from app.models.graph import CareerProfile
from app.utils.logger import get_logger

logger = get_logger(__name__)

TYPE_TO_FOLDER = {
    "Person": "Career",
    "Project": "Projects",
    "Skill": "Skills",
    "Organization": "Organizations",
    "Publication": "Publications",
    "Technology": "Technologies",
    "Role": "Roles",
    "Achievement": "Achievements",
    "Event": "Events",
    "Institution": "Institutions",
}


class ObsidianWriterAgent:
    def run(
        self,
        graph: nx.DiGraph,
        profiles: list[CareerProfile],
        vault_path: str | None = None,
        delta: bool = False,
    ):
        vault = Path(vault_path or config.VAULT_DIR)
        self._setup_vault(vault)
        profile_map = {p.name: p for p in profiles}

        for node_id, data in graph.nodes(data=True):
            ntype = data.get("type", "Unknown")
            folder = TYPE_TO_FOLDER.get(ntype, "Misc")
            folder_path = vault / folder
            folder_path.mkdir(parents=True, exist_ok=True)

            name = data.get("name", node_id)
            note_path = folder_path / f"{name}.md"

            successors = [
                (graph.nodes[s].get("name", s), graph.edges[node_id, s].get("relation", ""))
                for s in graph.successors(node_id)
                if graph.nodes[s].get("name")
            ]
            predecessors = [
                (graph.nodes[p].get("name", p), graph.edges[p, node_id].get("relation", ""))
                for p in graph.predecessors(node_id)
                if graph.nodes[p].get("name")
            ]

            profile = profile_map.get(name)
            new_content = self._render_note(data, successors, predecessors, profile)

            if delta and note_path.exists():
                existing = note_path.read_text(encoding="utf-8")
                final_content = self._merge_note(existing, new_content)
            else:
                final_content = new_content

            note_path.write_text(final_content, encoding="utf-8")
            logger.info(f"Written: {note_path}")

        self._write_canvas(vault, graph)

    def _setup_vault(self, vault: Path):
        vault.mkdir(parents=True, exist_ok=True)
        obsidian_dir = vault / ".obsidian"
        obsidian_dir.mkdir(exist_ok=True)
        (obsidian_dir / "app.json").write_text(
            json.dumps({"defaultViewMode": "source", "livePreview": True}, indent=2),
            encoding="utf-8",
        )
        graph_config = {
            "colorGroups": [
                {"query": f"tag:#{t.lower()}", "color": {"a": 1, "rgb": c}}
                for t, c in [
                    ("person", 4756697),
                    ("project", 6008155),
                    ("skill", 15246392),
                    ("organization", 10180278),
                ]
            ]
        }
        (obsidian_dir / "graph.json").write_text(
            json.dumps(graph_config, indent=2), encoding="utf-8"
        )

    def _render_note(
        self,
        data: dict,
        successors: list,
        predecessors: list,
        profile: CareerProfile | None,
    ) -> str:
        name = data.get("name", "Unknown")
        ntype = data.get("type", "Unknown")
        desc = data.get("description", "")
        sources = data.get("source_files", [])
        today = date.today().isoformat()

        lines = [
            "---",
            f"type: {ntype}",
            f'name: "{name}"',
            f"tags: [{ntype.lower()}]",
            f"created: {today}",
            f"sources: [{', '.join(sources)}]",
            "---",
            "",
            f"# {name}",
            "",
            "## Overview",
            desc or "(설명 없음)",
            "",
        ]

        if profile:
            lines += [
                "## Career Summary",
                profile.persona_summary,
                "",
                "## Skills",
            ]
            lines += [f"- [[{s}]]" for s in profile.skills]
            lines += [
                "",
                "## Timeline",
            ]
            lines += [f"- **{t['year']}**: {t['event']}" for t in profile.timeline]
            lines.append("")

        if successors or predecessors:
            lines.append("## Connections")
            lines.append("")
            for target_name, relation in successors:
                lines.append(f"- {relation}: [[{target_name}]]")
            for source_name, relation in predecessors:
                lines.append(f"- ← {relation}: [[{source_name}]]")
            lines.append("")

        return "\n".join(lines)

    def _merge_note(self, existing: str, new_content: str) -> str:
        new_wikilinks = set(re.findall(r'\[\[([^\]]+)\]\]', new_content))
        existing_wikilinks = set(re.findall(r'\[\[([^\]]+)\]\]', existing))
        missing = new_wikilinks - existing_wikilinks
        if missing:
            additions = "\n".join(f"- [[{link}]]" for link in sorted(missing))
            return existing.rstrip() + f"\n\n## New Connections\n{additions}\n"
        return existing

    def _write_canvas(self, vault: Path, graph: nx.DiGraph):
        nodes_canvas = []
        edges_canvas = []

        for i, node_id in enumerate(graph.nodes):
            x = float((i % 10) * 250)
            y = float((i // 10) * 200)
            nodes_canvas.append({
                "id": re.sub(r'[^a-zA-Z0-9_-]', '_', node_id),
                "type": "text",
                "text": graph.nodes[node_id].get("name", node_id),
                "x": x,
                "y": y,
                "width": 200,
                "height": 60,
            })

        for u, v, data in graph.edges(data=True):
            edges_canvas.append({
                "id": re.sub(r'[^a-zA-Z0-9_-]', '_', f"{u}_{v}"),
                "fromNode": re.sub(r'[^a-zA-Z0-9_-]', '_', u),
                "fromSide": "right",
                "toNode": re.sub(r'[^a-zA-Z0-9_-]', '_', v),
                "toSide": "left",
                "label": data.get("relation", ""),
            })

        canvas = {"nodes": nodes_canvas, "edges": edges_canvas}
        (vault / "_index.canvas").write_text(
            json.dumps(canvas, indent=2, ensure_ascii=False), encoding="utf-8"
        )
