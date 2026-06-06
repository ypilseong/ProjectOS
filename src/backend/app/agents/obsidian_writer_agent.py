import json
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Callable

import networkx as nx

from app.config import config
from app.models.graph import CareerProfile
from app.models.vault import VaultFile, VaultNote, VaultPayload
from app.utils.logger import get_logger

logger = get_logger(__name__)

TYPE_TO_FOLDER = {
    "Person": "Career",
    "Project": "Projects",
    "Skill": "Skills",
    "Organization": "Organizations",
    "Publication": "Publications",
    "Role": "Roles",
    "Achievement": "Achievements",
    "Event": "Events",
    "Institution": "Institutions",
}

TYPE_COLORS = {
    "Person": {"canvas": "#4895ef", "graph": 0x4895EF},
    "Project": {"canvas": "#2a9d8f", "graph": 0x2A9D8F},
    "Skill": {"canvas": "#f4a261", "graph": 0xF4A261},
    "Organization": {"canvas": "#9b5de5", "graph": 0x9B5DE5},
    "Publication": {"canvas": "#e76f51", "graph": 0xE76F51},
    "Role": {"canvas": "#00b4d8", "graph": 0x00B4D8},
    "Achievement": {"canvas": "#f9c74f", "graph": 0xF9C74F},
    "Event": {"canvas": "#90be6d", "graph": 0x90BE6D},
    "Institution": {"canvas": "#f72585", "graph": 0xF72585},
    "Category": {"canvas": "#8d99ae", "graph": 0x8D99AE},
    "Unknown": {"canvas": "#adb5bd", "graph": 0xADB5BD},
}


def _safe_filename(name: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()
    safe = re.sub(r"\s+", " ", safe)
    safe = safe.rstrip(".")
    return safe or "Untitled"


class ObsidianWriterAgent:
    def build_payload(
        self,
        graph: nx.DiGraph,
        profiles: list[CareerProfile] | None = None,
        project_id: str | None = None,
        delta: bool = False,
    ) -> VaultPayload:
        from app.utils.graph_restructure import build_entity_details, demote_project_context_nodes

        graph, _ = demote_project_context_nodes(graph)
        graph, _ = build_entity_details(graph)

        profile_map = {p.name: p for p in (profiles or [])}
        notes: list[VaultNote] = []
        changed_pages: list[str] = []

        nodes = [
            (node_id, data)
            for node_id, data in graph.nodes(data=True)
            if data.get("type") != "Category"
        ]
        for node_id, data in nodes:
            ntype = data.get("type", "Unknown")
            folder = TYPE_TO_FOLDER.get(ntype, "Misc")
            name = data.get("name", node_id)
            filename = f"{_safe_filename(name)}.md"

            successors, predecessors = self._note_connections(graph, node_id)

            profile = profile_map.get(name)
            notes.append(
                VaultNote(
                    folder=folder,
                    filename=filename,
                    content=self._render_note(data, successors, predecessors, profile),
                )
            )
            changed_pages.append(str(Path(folder) / filename))

        return VaultPayload(
            notes=notes,
            canvas=VaultFile(filename="_index.canvas", content=self._render_canvas(graph)),
            index=VaultFile(filename="_index.md", content=self._render_index(graph)),
            log_entry=self._render_log_entry(graph, changed_pages, delta, project_id),
        )

    def write_payload(
        self,
        payload: VaultPayload,
        vault_path: str | None = None,
        delta: bool = False,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> None:
        vault = Path(vault_path or config.VAULT_DIR)
        if not delta:
            self._clear_generated_notes(vault)
        self._setup_vault(vault)

        total = len(payload.notes)
        for i, note in enumerate(payload.notes, start=1):
            folder_path = vault / note.folder
            folder_path.mkdir(parents=True, exist_ok=True)
            note_path = folder_path / note.filename

            if delta and note_path.exists():
                existing = note_path.read_text(encoding="utf-8")
                final_content = self._merge_note(existing, note.content)
            else:
                final_content = note.content

            note_path.write_text(final_content, encoding="utf-8")
            logger.info(f"Written: {note_path}")
            if progress_callback:
                progress_callback(i, total, Path(note.filename).stem)

        (vault / payload.canvas.filename).write_text(payload.canvas.content, encoding="utf-8")
        (vault / payload.index.filename).write_text(payload.index.content, encoding="utf-8")
        self._append_log(vault, payload.log_entry)

    def run(
        self,
        graph: nx.DiGraph,
        profiles: list[CareerProfile] | None = None,
        vault_path: str | None = None,
        delta: bool = False,
        project_id: str | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ):
        payload = self.build_payload(graph, profiles, project_id=project_id, delta=delta)
        self.write_payload(
            payload,
            vault_path=vault_path,
            delta=delta,
            progress_callback=progress_callback,
        )
        self._write_hot(Path(vault_path or config.VAULT_DIR), graph, project_id)

    def _write_hot(
        self,
        vault: Path,
        graph: nx.DiGraph,
        project_id: str | None,
    ) -> None:
        """Write hot.md: compact session-entry context. Best-effort; never fails the build."""
        try:
            from app.services.hot_context import compose_hot_context, render_hot_markdown
            from app.utils.graph_restructure import (
                build_entity_details,
                demote_project_context_nodes,
            )

            rendered, _ = demote_project_context_nodes(graph.copy())
            rendered, _ = build_entity_details(rendered)

            log_path = vault / "log.md"
            recent_log = (
                log_path.read_text(encoding="utf-8").splitlines()
                if log_path.exists()
                else None
            )
            ctx = compose_hot_context(rendered, project_id, recent_log=recent_log)
            (vault / "hot.md").write_text(render_hot_markdown(ctx), encoding="utf-8")
            logger.info(f"Written: {vault / 'hot.md'}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"hot.md generation failed: {exc}")

    def _clear_generated_notes(self, vault: Path) -> None:
        """Remove generated entity folders before a full rebuild."""
        if not vault.exists():
            return
        for folder in set(TYPE_TO_FOLDER.values()) | {"Misc"}:
            path = vault / folder
            if path.exists():
                shutil.rmtree(path)

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
                {
                    "query": f"tag:#{entity_type.lower()}",
                    "color": {"a": 1, "rgb": colors["graph"]},
                }
                for entity_type, colors in TYPE_COLORS.items()
                if entity_type != "Unknown"
            ]
        }
        (obsidian_dir / "graph.json").write_text(
            json.dumps(graph_config, indent=2), encoding="utf-8"
        )

    def _note_connections(self, graph: nx.DiGraph, node_id: str) -> tuple[list, list]:
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

        return successors, predecessors

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

        detail_sections = (data.get("details") or {}).get("sections", [])
        if detail_sections:
            lines.append("## Details")
            lines.append("")
            for section in detail_sections:
                title = section.get("title", "")
                items = section.get("items", [])
                if not title or not items:
                    continue
                lines.append(f"### {title}")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")

        lines += [
            "## Sources",
            f"- {', '.join(sources) if sources else '(none)'}",
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

    def _render_canvas(self, graph: nx.DiGraph) -> str:
        nodes_canvas = []
        edges_canvas = []

        for i, node_id in enumerate(graph.nodes):
            node_type = graph.nodes[node_id].get("type", "Unknown")
            x = float((i % 10) * 250)
            y = float((i // 10) * 200)
            nodes_canvas.append({
                "id": re.sub(r'[^a-zA-Z0-9_-]', '_', node_id),
                "type": "text",
                "text": graph.nodes[node_id].get("name", node_id),
                "color": TYPE_COLORS.get(node_type, TYPE_COLORS["Unknown"])["canvas"],
                "x": x,
                "y": y,
                "width": 320 if node_type == "Person" else 200,
                "height": 120 if node_type == "Person" else 60,
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
        return json.dumps(canvas, indent=2, ensure_ascii=False)

    def _write_canvas(self, vault: Path, graph: nx.DiGraph):
        (vault / "_index.canvas").write_text(self._render_canvas(graph), encoding="utf-8")

    def _render_index(self, graph: nx.DiGraph) -> str:
        lines = ["# Graph Index\n", "_Auto-generated. Do not edit manually._\n"]
        by_type: dict[str, list[tuple[str, str]]] = {}
        for node_id, data in graph.nodes(data=True):
            ntype = data.get("type", "")
            if ntype == "Category":
                continue
            name = data.get("name", "")
            if not name:
                continue
            by_type.setdefault(ntype, []).append((name, data.get("description", "") or ""))

        for ntype in sorted(by_type):
            lines.append(f"\n## {ntype}\n")
            for name, desc in sorted(by_type[ntype], key=lambda x: x[0]):
                desc_part = f" — {desc[:60]}" if desc else ""
                lines.append(f"- {name}{desc_part}\n")

        return "".join(lines)

    def _write_index(self, vault: Path, graph: nx.DiGraph) -> None:
        """Write _index.md: entity names grouped by type for query resolution."""
        (vault / "_index.md").write_text(self._render_index(graph), encoding="utf-8")

    def _render_log_entry(
        self,
        graph: nx.DiGraph,
        changed_pages: list[str],
        delta: bool,
        project_id: str | None,
    ) -> str:
        today = date.today().isoformat()
        source_files = sorted({
            source
            for _, data in graph.nodes(data=True)
            for source in data.get("source_files", [])
            if source
        })
        lines = [
            f"## {today} graph {'delta' if delta else 'build'}",
            "",
            f"- Project: {project_id or '(unknown)'}",
            f"- Nodes: {graph.number_of_nodes()}",
            f"- Edges: {graph.number_of_edges()}",
            f"- Source files: {', '.join(source_files) if source_files else '(none)'}",
            f"- Changed pages: {len(changed_pages)}",
        ]
        for page in changed_pages[:20]:
            lines.append(f"  - [[{Path(page).stem}]] ({page})")
        if len(changed_pages) > 20:
            lines.append(f"  - ... and {len(changed_pages) - 20} more")
        lines.append("")
        return "\n".join(lines)

    def _append_log(self, vault: Path, log_entry: str) -> None:
        log_path = vault / "log.md"
        prefix = "" if log_path.exists() else "# ProjectOS Log\n\n"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(prefix + log_entry.rstrip() + "\n")

    def _write_log(
        self,
        vault: Path,
        graph: nx.DiGraph,
        changed_pages: list[str],
        delta: bool,
        project_id: str | None,
    ) -> None:
        """Append a human-readable build event for wiki-style memory."""
        self._append_log(
            vault,
            self._render_log_entry(graph, changed_pages, delta, project_id),
        )
