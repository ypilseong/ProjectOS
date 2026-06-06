from pathlib import Path
from app.services.vault_reconcile import parse_vault_page


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_parse_vault_page_extracts_type_name_description(tmp_path):
    page = tmp_path / "Skills" / "Python.md"
    _write(page, '---\ntype: Skill\nname: "Python"\ntags: [skill]\n---\n\n'
                 '# Python\n\n## Overview\n프로그래밍 언어\n\n## Sources\n- cv.pdf\n')
    parsed = parse_vault_page(page)
    assert parsed["type"] == "Skill"
    assert parsed["name"] == "Python"
    assert parsed["description"] == "프로그래밍 언어"


def test_parse_vault_page_treats_placeholder_as_empty(tmp_path):
    page = tmp_path / "Skills" / "X.md"
    _write(page, '---\ntype: Skill\nname: "X"\n---\n\n## Overview\n(설명 없음)\n')
    assert parse_vault_page(page)["description"] == ""


def test_parse_vault_page_parses_connections_both_directions(tmp_path):
    page = tmp_path / "Career" / "Yang.md"
    _write(page, '---\ntype: Person\nname: "Yang"\n---\n\n## Overview\nML\n\n'
                 '## Connections\n\n- USES_SKILL: [[Python]]\n- ← DEVELOPED: [[ProjectOS]]\n')
    conns = parse_vault_page(page)["connections"]
    assert {"relation": "USES_SKILL", "direction": "out", "other": "Python"} in conns
    assert {"relation": "DEVELOPED", "direction": "in", "other": "ProjectOS"} in conns


def test_parse_vault_page_returns_none_without_frontmatter(tmp_path):
    page = tmp_path / "Misc" / "junk.md"
    _write(page, "# no frontmatter here\n\njust text\n")
    assert parse_vault_page(page) is None
