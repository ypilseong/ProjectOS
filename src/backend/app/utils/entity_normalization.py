from __future__ import annotations

import re


def clean_entity_name(name: str) -> str:
    """Collapse whitespace without applying domain-specific aliases."""
    return " ".join((name or "").split()).strip()


def acronym_for(name: str) -> str:
    """Return an acronym for multi-word Latin labels, e.g. Natural Language Processing -> NLP."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9]+", name)
    if len(words) < 2:
        return ""
    return "".join(word[0] for word in words).upper()


def are_acronym_variants(a: str, b: str) -> bool:
    """Generic acronym equivalence without a hard-coded alias table."""
    a_clean = clean_entity_name(a)
    b_clean = clean_entity_name(b)
    if not a_clean or not b_clean:
        return False
    a_upper = re.sub(r"[^A-Za-z0-9]", "", a_clean).upper()
    b_upper = re.sub(r"[^A-Za-z0-9]", "", b_clean).upper()
    return bool(
        len(a_upper) >= 2
        and len(b_upper) >= 2
        and (a_upper == acronym_for(b_clean) or b_upper == acronym_for(a_clean))
    )
