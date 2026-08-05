"""Section-level alignment via the Bertalign two-pass DP aligner.

Requires the optional 'align' dependency group's 'bertalign' package -- not
installed by default, meant to run in a heavier environment (e.g. Colab).
Importing this module without it installed is safe; instantiating
BertalignSectionAligner raises a clear RuntimeError.

Bertalign embeds every sentence (LaBSE by default) and runs a monotonic
dynamic-programming search over the whole flat sentence sequence, natively
producing 1-1, 1-many, many-1, and many-many groups ("beads") in one pass --
this replaces the anchor-scaffold-then-locally-nudge approach in
tradurre.services.aligner (align/_align_gap/_boundary_optimize) for both the
paragraph and sentence granularity at once, since bertalign isn't bounded by
paragraph containers to begin with.

Design constraint (same as embed_align/llm_judge): only ever regroups
existing sentences; never generates or alters text.
"""

import logging

logger = logging.getLogger("tradurre.bertalign_align")

DEFAULT_MODEL = "LaBSE"


def _load_bertalign():
    try:
        from bertalign import Bertalign
        from bertalign.encoder import get_encoder
    except ImportError as e:
        raise RuntimeError(
            "Bertalign-based alignment requires the 'bertalign' package "
            "(optional 'align' dependency group). Install with: "
            "uv sync --extra align"
        ) from e
    return Bertalign, get_encoder


class BertalignScorer:
    """Adapts bertalign's shared Encoder to the same (warm_cache/similarity/
    score_fn) interface as embed_align.EmbeddingScorer, so pipeline stages
    that only need embedding similarity (LLM-judge output rescoring, low-
    confidence flagging) can reuse bertalign's already-loaded model instead
    of loading a second copy of LaBSE.
    """

    def __init__(self, encoder):
        self.encoder = encoder
        self.model_name = encoder.model_name
        self.device = str(encoder.model.device)
        self._cache: dict[str, object] = {}

    def warm_cache(self, texts: list[str], batch_size: int = 64) -> None:
        missing = sorted({t for t in texts if t and t not in self._cache})
        if not missing:
            return
        logger.info("embedding %d new sentences (cache size before: %d)", len(missing), len(self._cache))
        vectors = self.encoder.model.encode(
            missing, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False,
        )
        for text, vec in zip(missing, vectors):
            self._cache[text] = vec

    def _pooled(self, texts: list[str]):
        import numpy as np

        vecs = [self._cache[t] for t in texts if t in self._cache]
        if not vecs:
            return None
        return np.mean(vecs, axis=0)

    def similarity(self, source_texts: list[str], target_texts: list[str]) -> float:
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
        return self.similarity


class BertalignSectionAligner:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        Bertalign, get_encoder = _load_bertalign()
        self._Bertalign = Bertalign
        # get_encoder is process-cached by bertalign itself, so repeated
        # BertalignSectionAligner() calls (one per section) share one loaded
        # model rather than reloading it.
        self.encoder = get_encoder(model_name)
        self.model_name = model_name
        self.scorer = BertalignScorer(self.encoder)

    def align_section(
        self,
        src_paragraphs: list[list[str]],
        tgt_paragraphs: list[list[str]],
    ) -> list[tuple[list[str], list[str], list[tuple[str, str, float, str]]]]:
        """Align one section's sentences with bertalign, then regroup the
        result back under the section's original *source*-side paragraph
        boundaries (source and target editions don't reliably share
        paragraph breaks -- publishers/translators re-paragraph freely --
        and bertalign only ever produces one flat, whole-section grouping).

        Returns one (src_para_sentences, tgt_para_sentences, sentence_pairs)
        tuple per source paragraph, where sentence_pairs has the same shape
        as tradurre.services.embed_align.refine_paragraph_alignment's return
        value: a list of (source_text, target_text, confidence, method).
        """
        flat_src: list[str] = []
        src_para_of: list[int] = []
        for p_idx, para in enumerate(src_paragraphs):
            for s in para:
                if not s:
                    continue
                flat_src.append(s)
                src_para_of.append(p_idx)

        flat_tgt: list[str] = [s for para in tgt_paragraphs for s in para if s]

        if not flat_src or not flat_tgt:
            # Nothing to align on at least one side -- keep the source
            # paragraph structure with everything unmatched, same shape the
            # anchor-based fallback path produces.
            return [
                (para, [], [(s, "", 0.0, "fallback") for s in para])
                for para in src_paragraphs
            ]

        logger.info(
            "aligning section: %d source / %d target sentences", len(flat_src), len(flat_tgt),
        )
        aligner = self._Bertalign(
            "\n".join(flat_src), "\n".join(flat_tgt), is_split=True, model=self.encoder,
        )
        aligner.align_sents()

        self.scorer.warm_cache(flat_src + flat_tgt)

        grouped: list[list[tuple[list[int], list[int]]]] = [[] for _ in src_paragraphs]
        current_para = 0
        for src_idx, tgt_idx in aligner.result:
            if src_idx:
                current_para = src_para_of[src_idx[0]]
            grouped[current_para].append((src_idx, tgt_idx))

        output = []
        for p_idx, para in enumerate(src_paragraphs):
            tgt_para_sentences = [flat_tgt[j] for _, tgt_idx in grouped[p_idx] for j in tgt_idx]
            sentence_pairs = []
            for src_idx, tgt_idx in grouped[p_idx]:
                src_sents = [flat_src[i] for i in src_idx]
                tgt_sents = [flat_tgt[j] for j in tgt_idx]
                src_text = " ".join(src_sents)
                tgt_text = " ".join(tgt_sents)
                if src_text and tgt_text:
                    confidence = self.scorer.similarity(src_sents, tgt_sents)
                    method = "bertalign"
                else:
                    confidence = 0.0
                    method = "fallback"
                sentence_pairs.append((src_text, tgt_text, confidence, method))
            output.append((para, tgt_para_sentences, sentence_pairs))

        return output
