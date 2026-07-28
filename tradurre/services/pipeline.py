"""Top-level orchestration: two files -> a fully aligned, downloadable artifact.

Chains, in increasing cost/quality order:
  1. baseline (free, local): doc_adapter + the existing anchor-based hierarchical
     aligner (tradurre.services.aligner) -- always runs.
  2. embedding rescoring (optional, needs 'align' extra): refines sentence
     boundaries within low-confidence paragraphs using multilingual sentence
     embeddings (tradurre.services.embed_align).
  3. LLM judge (optional, needs 'align' extra): for paragraphs still
     low-confidence after step 2, asks an LLM for a validated index-mapping
     (tradurre.services.llm_judge) -- never lets it generate replacement text.

Stages 2 and 3 are meant to run in a heavier environment (e.g. Colab); this
module degrades gracefully (skips the stage, records a warning) if their
dependencies aren't installed, so it's safe to import/call in the base app too.

Every stage logs generously (see module loggers in doc_adapter/aligner/
embed_align/llm_judge) and the run's timings/counts/warnings are embedded in the
returned artifact so a Colab run can be debugged after the fact from the
downloaded file alone, without a live session.
"""

import logging
import time

from tradurre.models import ArtifactSentence
from tradurre.services import aligner, artifact_io, doc_adapter

logger = logging.getLogger("tradurre.pipeline")

LOW_CONFIDENCE_THRESHOLD = 0.5


def build_aligned_artifact(
    source_bytes: bytes,
    target_bytes: bytes,
    source_filename: str,
    target_filename: str,
    *,
    source_lang: str,
    target_lang: str,
    title: str = "",
    use_embeddings: bool = True,
    use_llm_judge: bool = True,
    embedding_model: str | None = None,
    llm_model: str | None = None,
):
    t_start = time.monotonic()
    warnings: list[str] = []
    stats: dict = {"stage_seconds": {}}
    generator: dict = {
        "pipeline": "tradurre.services.pipeline.build_aligned_artifact",
        "stages": ["baseline"],
    }

    logger.info("loading source=%r target=%r", source_filename, target_filename)
    t0 = time.monotonic()
    source_text = doc_adapter.load_as_text(source_filename, source_bytes)
    target_text = doc_adapter.load_as_text(target_filename, target_bytes)
    stats["stage_seconds"]["load"] = round(time.monotonic() - t0, 2)

    t0 = time.monotonic()
    source_h = aligner.extract_hierarchy(source_text)
    target_h = aligner.extract_hierarchy(target_text)
    section_pairs = aligner.align_sections(source_h, target_h)
    stats["stage_seconds"]["section_align"] = round(time.monotonic() - t0, 2)
    logger.info("baseline: %d aligned sections", len(section_pairs))

    scorer = _maybe_load_embedding_scorer(
        use_embeddings, embedding_model, warnings, stats, generator
    )
    judge = _maybe_load_llm_judge(use_llm_judge, llm_model, warnings, stats, generator)

    hierarchy: list[list[list[ArtifactSentence]]] = []
    counts = {"anchor": 0, "fallback": 0, "embedding": 0, "llm": 0, "llm_rejected": 0}
    t0 = time.monotonic()

    for section_idx, (src_sec, tgt_sec) in enumerate(section_pairs):
        para_pairs_raw = aligner.align_paragraphs(src_sec, tgt_sec)
        para_pairs = aligner._boundary_optimize(list(para_pairs_raw))
        section_out: list[list[ArtifactSentence]] = []

        for para_idx, (src_para, tgt_para) in enumerate(para_pairs):
            sentence_pairs = _align_paragraph_sentences(src_para, tgt_para, scorer)
            sentence_pairs = _escalate_to_judge(
                sentence_pairs, src_para, tgt_para, judge, scorer,
                section_idx, para_idx, counts,
            )

            para_out: list[ArtifactSentence] = []
            for src, tgt, confidence, method in sentence_pairs:
                if not src and not tgt:
                    continue
                flags = ["low_confidence"] if confidence < LOW_CONFIDENCE_THRESHOLD else []
                para_out.append(ArtifactSentence(
                    source_text=src, target_text=tgt,
                    confidence=round(confidence, 4), method=method, flags=flags,
                ))
                if method in counts:
                    counts[method] += 1
            section_out.append(para_out)

        hierarchy.append(section_out)

    stats["stage_seconds"]["sentence_align"] = round(time.monotonic() - t0, 2)
    stats["counts"] = counts
    stats["total_seconds"] = round(time.monotonic() - t_start, 2)
    logger.info("pipeline finished in %.1fs: %s", stats["total_seconds"], counts)

    return artifact_io.build_artifact(
        title=title,
        source_lang=source_lang,
        target_lang=target_lang,
        hierarchy=hierarchy,
        generator=generator,
        warnings=warnings,
        stats=stats,
    )


def _maybe_load_embedding_scorer(enabled, model_name, warnings, stats, generator):
    if not enabled:
        return None
    try:
        from tradurre.services.embed_align import EmbeddingScorer
        t0 = time.monotonic()
        scorer = EmbeddingScorer(model_name=model_name) if model_name else EmbeddingScorer()
        stats["stage_seconds"]["embedding_model_load"] = round(time.monotonic() - t0, 2)
        generator["stages"].append("embedding")
        generator["embedding_model"] = scorer.model_name
        generator["embedding_device"] = scorer.device
        return scorer
    except Exception as e:
        # Broad on purpose: a heavy-model load can fail in ways that aren't
        # ImportError/RuntimeError (HF download errors, version mismatches
        # inside transformers/torchvision, etc.). This run can't be debugged
        # live, so a single stage failing must degrade to "skip the stage"
        # rather than abort the whole pipeline with no output artifact.
        logger.exception("embedding stage unavailable")
        warnings.append(f"embedding stage skipped: {e}")
        return None


def _maybe_load_llm_judge(enabled, model_name, warnings, stats, generator):
    if not enabled:
        return None
    try:
        from tradurre.services.llm_judge import LLMJudge
        t0 = time.monotonic()
        judge = LLMJudge(model_name=model_name) if model_name else LLMJudge()
        stats["stage_seconds"]["llm_model_load"] = round(time.monotonic() - t0, 2)
        generator["stages"].append("llm_judge")
        generator["llm_model"] = judge.model_name
        return judge
    except Exception as e:
        # See comment in _maybe_load_embedding_scorer: catch broadly so a
        # broken heavy-model load degrades this one stage instead of
        # aborting the whole run.
        logger.exception("LLM judge stage unavailable")
        warnings.append(f"LLM judge stage skipped: {e}")
        return None


def _align_paragraph_sentences(src_para, tgt_para, scorer):
    """Returns a list of (source_text, target_text, confidence, method)."""
    if scorer is not None and src_para and tgt_para:
        from tradurre.services.embed_align import refine_paragraph_alignment
        return refine_paragraph_alignment(src_para, tgt_para, scorer)

    anchor_pairs = aligner.align_sentences(src_para, tgt_para)
    return [
        (s, t, 1.0 if s and t else 0.0, "anchor" if s and t else "fallback")
        for s, t in anchor_pairs
    ]


def _escalate_to_judge(sentence_pairs, src_para, tgt_para, judge, scorer, section_idx, para_idx, counts):
    if judge is None or not src_para or not tgt_para:
        return sentence_pairs

    if all(c >= LOW_CONFIDENCE_THRESHOLD for _, _, c, _ in sentence_pairs):
        return sentence_pairs

    logger.info(
        "escalating section %d paragraph %d to LLM judge (%d source / %d target sentences)",
        section_idx, para_idx, len(src_para), len(tgt_para),
    )
    try:
        groups = judge.judge_paragraph(src_para, tgt_para)
    except Exception:
        logger.exception(
            "LLM judge crashed on section %d paragraph %d; keeping prior alignment",
            section_idx, para_idx,
        )
        groups = None

    if groups is None:
        counts["llm_rejected"] += 1
        return sentence_pairs

    from tradurre.services.llm_judge import apply_mapping
    mapped = apply_mapping(groups, src_para, tgt_para)

    if scorer is not None:
        # apply_mapping may have concatenated multiple original sentences into
        # a new string (merges/splits) -- that joined string was never
        # embedded, so it must be warmed before scoring or similarity()
        # silently falls back to a cache-miss 0.0 for every such pair.
        scorer.warm_cache([s for s, t in mapped if s] + [t for s, t in mapped if t])

    result = []
    for src, tgt in mapped:
        if scorer is not None and src and tgt:
            confidence = scorer.similarity([src], [tgt])
        else:
            confidence = 0.8 if src and tgt else 0.0
        result.append((src, tgt, confidence, "llm"))
    return result
