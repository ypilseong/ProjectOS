"""Deterministic citation validation for QueryAgent answers."""

from collections.abc import Iterable
import re


_BRACKET_RE = re.compile(r"\[[^\[\]\n]+\]")
_UNSUPPORTED_MARKER = "출처 불명"
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S+")
_LIST_MARKER_ONLY_RE = re.compile(r"^\s*(?:[-*+]|(?:\d+|[A-Za-z])[\.)])\s*$")
_LEADING_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+[\.)])\s+")
_HAS_WORD_RE = re.compile(r"[0-9A-Za-z가-힣]")


def validate_citations(
    answer: str,
    allowed_labels: Iterable[str],
    *,
    require_citation: bool = True,
) -> dict:
    """Validate that an answer cites only labels supplied in the prompt.

    The validator is intentionally read-only and deterministic. It treats exact
    bracket labels such as ``[cv.pdf]`` and ``[cv.pdf#id1 p.1 char:0]`` as
    citations, and treats any occurrence of ``출처 불명`` as an unsupported
    marker rather than an unknown citation.
    """

    allowed = {label.strip() for label in allowed_labels if label and label.strip()}
    citations = _extract_citation_labels(answer, allowed)
    unsupported_count = answer.count(_UNSUPPORTED_MARKER)

    used_labels = _unique_in_order(label for label in citations if label in allowed)
    unknown_labels = _unique_in_order(label for label in citations if label not in allowed)
    missing_sentences = (
        _missing_citation_sentences(answer, citations)
        if require_citation
        else []
    )
    valid = not unknown_labels and not missing_sentences

    return {
        "valid": valid,
        "used_labels": used_labels,
        "unknown_labels": unknown_labels,
        "missing_citation_sentences": missing_sentences,
        "unsupported_count": unsupported_count,
        "summary": {
            "allowed_label_count": len(allowed),
            "used_label_count": len(used_labels),
            "unknown_label_count": len(unknown_labels),
            "missing_citation_count": len(missing_sentences),
            "unsupported_count": unsupported_count,
        },
        "summary_text": _summary_text(
            valid,
            used_labels,
            unknown_labels,
            missing_sentences,
            unsupported_count,
        ),
    }


def _extract_citation_labels(answer: str, allowed: set[str]) -> list[str]:
    labels: list[str] = []
    for match in _BRACKET_RE.finditer(answer or ""):
        label = match.group(0).strip()
        inner = label[1:-1].strip()
        if inner == _UNSUPPORTED_MARKER:
            continue
        if label in allowed or _looks_like_source_label(inner):
            labels.append(label)
    return labels


def _looks_like_source_label(inner: str) -> bool:
    return any(token in inner for token in (".", "#", " p.", "char:"))


def _missing_citation_sentences(answer: str, citation_labels: list[str]) -> list[str]:
    citation_set = set(citation_labels)
    missing: list[str] = []
    for sentence in _candidate_sentences(answer):
        if _UNSUPPORTED_MARKER in sentence:
            continue
        if any(label in sentence for label in citation_set):
            continue
        missing.append(sentence)
    return missing


def _candidate_sentences(answer: str) -> list[str]:
    candidates: list[str] = []
    for part in _SENTENCE_SPLIT_RE.split(answer or ""):
        sentence = _normalize_sentence(part)
        if not sentence:
            continue
        if _should_skip_sentence(sentence):
            continue
        candidates.append(sentence)
    return candidates


def _normalize_sentence(sentence: str) -> str:
    sentence = sentence.strip()
    sentence = _LEADING_LIST_MARKER_RE.sub("", sentence)
    return sentence.strip()


def _should_skip_sentence(sentence: str) -> bool:
    if _HEADER_RE.match(sentence):
        return True
    if _LIST_MARKER_ONLY_RE.match(sentence):
        return True
    if sentence.endswith("?") or sentence.endswith("？"):
        return True
    return not _HAS_WORD_RE.search(sentence)


def _unique_in_order(labels: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for label in labels:
        if label in seen:
            continue
        seen.add(label)
        unique.append(label)
    return unique


def _summary_text(
    valid: bool,
    used_labels: list[str],
    unknown_labels: list[str],
    missing_sentences: list[str],
    unsupported_count: int,
) -> str:
    if valid:
        return (
            f"valid: used {len(used_labels)} allowed label(s), "
            f"{unsupported_count} unsupported marker(s)"
        )
    parts: list[str] = []
    if unknown_labels:
        parts.append(f"{len(unknown_labels)} unknown label(s)")
    if missing_sentences:
        parts.append(f"{len(missing_sentences)} sentence(s) missing citation")
    if unsupported_count:
        parts.append(f"{unsupported_count} unsupported marker(s)")
    return "invalid: " + ", ".join(parts)
