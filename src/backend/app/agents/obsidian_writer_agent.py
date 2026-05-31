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

        # Obsidian's native Graph View sizes nodes from markdown wikilinks, not
        # NetworkX edge metadata. Category hubs are useful in the app graph, but
        # they make the user node look under-connected in Obsidian. Expand
        # Person -> Category -> Entity into direct note links while preserving
        # the category graph structure itself.
        if graph.nodes[node_id].get("type") == "Person":
            seen = {name for name, _ in successors}
            for category_id in graph.successors(node_id):
                if graph.nodes[category_id].get("type") != "Category":
                    continue
                category_name = graph.nodes[category_id].get("name", "Category")
                for target_id in graph.successors(category_id):
                    target = graph.nodes[target_id]
                    target_name = target.get("name")
                    if not target_name or target_name in seen or target.get("type") == "Category":
                        continue
                    successors.append((target_name, f"{category_name}"))
                    seen.add(target_name)

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
        source_chunk_ids = data.get("source_chunk_ids", [])
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
            "## Sources",
            f"- Files: {', '.join(sources) if sources else '(none)'}",
            f"- Chunks: {', '.join(source_chunk_ids) if source_chunk_ids else '(none)'}",
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
            x = float((i % 10) * 250)
            y = float((i // 10) * 200)
            nodes_canvas.append({
                "id": re.sub(r'[^a-zA-Z0-9_-]', '_', node_id),
                "type": "text",
                "text": graph.nodes[node_id].get("name", node_id),
                "x": x,
                "y": y,
                "width": 320 if graph.nodes[node_id].get("type") == "Person" else 200,
                "height": 120 if graph.nodes[node_id].get("type") == "Person" else 60,
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
