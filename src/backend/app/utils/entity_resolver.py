from difflib import SequenceMatcher

import networkx as nx
import numpy as np

from app.config import config
from app.utils.entity_normalization import are_acronym_variants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class EntityResolver:
    """Find existing graph nodes by name using fuzzy string match with optional
    embedding-based cosine similarity fallback (iText2KG-inspired pattern).

    Embedding similarity is used only when EMBEDDING_BASE_URL is configured and
    the embedding server is reachable. Falls back silently to string matching.
    """

    def __init__(self, fuzzy_threshold: float = 0.85, embed_threshold: float = 0.88):
        self._fuzzy_threshold = fuzzy_threshold
        self._embed_threshold = embed_threshold

    def find_existing_node(
        self, graph: nx.DiGraph, entity_type: str, name: str
    ) -> str | None:
        """Synchronous lookup: fuzzy string match only."""
        for node_id in graph.nodes:
            node = graph.nodes[node_id]
            if node.get("type") != entity_type:
                continue
            if self._fuzzy_match(node.get("name", ""), name):
                return node_id
        return None

    async def find_existing_node_async(
        self, graph: nx.DiGraph, entity_type: str, name: str
    ) -> str | None:
        """Async lookup: fuzzy string match first, then embedding cosine similarity."""
        sync_result = self.find_existing_node(graph, entity_type, name)
        if sync_result is not None:
            return sync_result

        if not config.EMBEDDING_BASE_URL:
            return None

        candidates = [
            (node_id, graph.nodes[node_id].get("name", ""))
            for node_id in graph.nodes
            if graph.nodes[node_id].get("type") == entity_type
        ]
        if not candidates:
            return None

        try:
            from app.utils.embedding_client import EmbeddingClient
            client = EmbeddingClient()
            all_names = [name] + [c[1] for c in candidates]
            embeddings = await client.embed(all_names)
            arr = np.array(embeddings, dtype=np.float32)
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            arr /= np.maximum(norms, 1e-9)
            query_vec = arr[0]
            cand_vecs = arr[1:]
            sims = cand_vecs @ query_vec
            best_idx = int(np.argmax(sims))
            if float(sims[best_idx]) >= self._embed_threshold:
                matched_id = candidates[best_idx][0]
                logger.info(
                    f"Embedding match: '{name}' -> '{candidates[best_idx][1]}' "
                    f"(sim={sims[best_idx]:.3f})"
                )
                return matched_id
        except Exception as e:
            logger.debug(f"Embedding lookup failed, staying with string match: {e}")

        return None

    def _fuzzy_match(self, a: str, b: str) -> bool:
        return (
            SequenceMatcher(None, a.lower(), b.lower()).ratio() >= self._fuzzy_threshold
            or are_acronym_variants(a, b)
        )
