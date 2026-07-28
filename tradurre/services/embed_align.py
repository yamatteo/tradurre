"""Embedding-based rescoring/refinement of anchor-aligned sentence pairs.

Requires the optional 'align' dependency group (sentence-transformers, torch) --
not installed by default, meant to run in a heavier environment (e.g. Colab).
Importing this module without those deps installed is safe; instantiating
EmbeddingScorer raises a clear RuntimeError.

Design constraint: this module only ever decides which existing sentences are
grouped together (via tradurre.services.aligner._boundary_optimize) or scores
an existing pairing's confidence. It never generates or alters sentence text.
"""

import logging
import time

logger = logging.getLogger("tradurre.embed_align")

DEFAULT_MODEL = "sentence-transformers/LaBSE"


def _load_sentence_transformers():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise RuntimeError(
            "Embedding-based alignment requires the 'align' optional dependency "
            "group (sentence-transformers, torch). Install with: "
            "uv sync --extra align"
        ) from e
    return SentenceTransformer


class EmbeddingScorer:
    """Caches multilingual sentence embeddings and scores unit-list pairs by
    cosine similarity of their mean-pooled embeddings."""

    def __init__(self, model_name: str = DEFAULT_MODEL, device: str | None = None):
        SentenceTransformer = _load_sentence_transformers()
        try:
            import torch
            resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        except ImportError:
            resolved_device = device or "cpu"

        logger.info("loading embedding model %r on device %r", model_name, resolved_device)
        t0 = time.monotonic()
        self.model = SentenceTransformer(model_name, device=resolved_device)
        logger.info("embedding model loaded in %.1fs", time.monotonic() - t0)

        self.model_name = model_name
        self.device = resolved_device
        self._cache: dict[str, object] = {}

    def warm_cache(self, texts: list[str], batch_size: int = 64) -> None:
        """Embed and cache any texts not already cached. Safe to call repeatedly."""
        missing = sorted({t for t in texts if t and t not in self._cache})
        if not missing:
            return
        logger.info("embedding %d new sentences (cache size before: %d)", len(missing), len(self._cache))
        t0 = time.monotonic()
        vectors = self.model.encode(
            missing,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        logger.info("embedded %d sentences in %.1fs", len(missing), time.monotonic() - t0)
        for text, vec in zip(missing, vectors):
            self._cache[text] = vec

    def _pooled(self, texts: list[str]):
        import numpy as np

        vecs = [self._cache[t] for t in texts if t in self._cache]
        if not vecs:
            return None
        return np.mean(vecs, axis=0)

    def similarity(self, source_texts: list[str], target_texts: list[str]) -> float:
        """Cosine similarity between mean-pooled embeddings of two text lists.

        Returns 0.0 if either side is empty or uncached -- no basis for comparison.
        """
        import numpy as np

        a = self._pooled(source_texts)
        b = self._pooled(target_texts)
        if a is None or b is None:
            return 0.0
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0.0:
            return 0.0
        return float(np.dot(a, b) / denom)

    def score_fn(self):
        """A (list[str], list[str]) -> float callable, for aligner._boundary_optimize."""
        return self.similarity


def refine_paragraph_alignment(
    source_sentences: list[str],
    target_sentences: list[str],
    scorer: EmbeddingScorer,
) -> list[tuple[str, str, float, str]]:
    """Re-check an anchor-based sentence alignment for one paragraph using
    embedding similarity to nudge sentence boundaries.

    Starts from the existing anchor alignment (tradurre.services.aligner),
    represents each aligned pair as a boundary_optimize "container" (0-or-1
    source unit, 0-or-1 target unit), and lets _boundary_optimize move units
    between adjacent containers when it improves embedding similarity. This
    only reassigns which original sentences are paired -- text is concatenated
    verbatim, never generated.

    Returns a list of (source_text, target_text, confidence, method) tuples.
    """
    from tradurre.services.aligner import _align_units, _boundary_optimize

    logger.debug(
        "refining paragraph: %d source sentences, %d target sentences",
        len(source_sentences), len(target_sentences),
    )

    scorer.warm_cache(source_sentences + target_sentences)

    anchor_pairs = _align_units(source_sentences, target_sentences)
    containers = [([s] if s else [], [t] if t else []) for s, t in anchor_pairs]
    optimized = _boundary_optimize(containers, score_fn=scorer.score_fn())

    result: list[tuple[str, str, float, str]] = []
    for src_list, tgt_list in optimized:
        src = " ".join(src_list)
        tgt = " ".join(tgt_list)
        if not src and not tgt:
            continue
        if src and tgt:
            confidence = scorer.similarity(src_list, tgt_list)
            method = "embedding"
        else:
            confidence = 0.0
            method = "fallback"
        result.append((src, tgt, confidence, method))

    return result
