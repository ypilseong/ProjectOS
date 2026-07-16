"""Source-backed provenance anchors for graph nodes and edges.

An evidence anchor records *where* a node or relation came from so that graph
cleanup and simulation review can be audited instead of relying on bare names.
"""

from app.models.graph import TextChunk

_DIRECTNESS = {"direct", "inferred"}


def make_evidence_anchor(
    chunk: TextChunk,
    *,
    quote: str = "",
    confidence: float = 1.0,
    method: str = "llm_extraction",
    directness: str = "direct",
) -> dict:
    """Build a provenance record anchoring an entity/relation to its source.

    directness: "direct" (explicitly stated in the text) or "inferred"
    (reconstructed from combined context). Unknown values normalize to
    "inferred" — the conservative choice for auditing.
    """
    return {
        "source_file": chunk.source_file,
        "chunk_id": chunk.chunk_id,
        "page_num": chunk.page_num,
        "char_offset": chunk.char_offset,
        "quote": quote or "",
        "confidence": confidence,
        "method": method,
        "directness": directness if directness in _DIRECTNESS else "inferred",
    }
