"""Build and validate the aligned-artifact interchange format.

An artifact is a plain JSON file carrying a fully section/paragraph/sentence-aligned
bitext, produced by tradurre.services.pipeline (typically run outside the main app,
e.g. on Colab) and consumed locally via POST /import/artifact. See
tradurre.models.AlignedArtifact for the schema.
"""

import logging
from datetime import datetime, timezone

from pydantic import ValidationError

from tradurre.models import (
    AlignedArtifact,
    ArtifactParagraph,
    ArtifactSection,
    ArtifactSentence,
)

logger = logging.getLogger("tradurre.artifact_io")

FORMAT_NAME = "tradurre-aligned-bitext"
FORMAT_VERSION = 1


def build_artifact(
    *,
    title: str,
    source_lang: str,
    target_lang: str,
    hierarchy: list[list[list[ArtifactSentence]]],
    generator: dict | None = None,
    warnings: list[str] | None = None,
    stats: dict | None = None,
) -> AlignedArtifact:
    """Assemble an AlignedArtifact from a sections[paragraphs[sentences]] structure.

    `hierarchy` elements are already-built ArtifactSentence objects (source_text,
    target_text, confidence, method, flags) -- this function only wraps them in the
    section/paragraph containers and the top-level envelope.
    """
    sections = [
        ArtifactSection(paragraphs=[ArtifactParagraph(sentences=para) for para in sec])
        for sec in hierarchy
    ]
    artifact = AlignedArtifact(
        format=FORMAT_NAME,
        version=FORMAT_VERSION,
        title=title,
        source_lang=source_lang,
        target_lang=target_lang,
        generated_at=datetime.now(timezone.utc).isoformat(),
        generator=generator or {},
        sections=sections,
        warnings=warnings or [],
        stats=stats or {},
    )
    logger.info(
        "built artifact: %d sections, %d sentences total",
        len(sections),
        sum(len(p.sentences) for s in sections for p in s.paragraphs),
    )
    return artifact


def serialize_artifact(artifact: AlignedArtifact) -> str:
    return artifact.model_dump_json(indent=2)


def parse_artifact(raw: bytes | str) -> AlignedArtifact:
    """Validate raw JSON bytes/str against the AlignedArtifact schema.

    Raises pydantic.ValidationError on malformed/incompatible input -- callers at
    the API boundary should catch this and turn it into a 422.
    """
    try:
        artifact = AlignedArtifact.model_validate_json(raw)
    except ValidationError:
        logger.exception("failed to parse aligned artifact")
        raise
    if artifact.format != FORMAT_NAME:
        raise ValueError(f"Unexpected artifact format: {artifact.format!r}")
    if artifact.version > FORMAT_VERSION:
        logger.warning(
            "artifact version %d is newer than this app supports (%d); "
            "proceeding best-effort",
            artifact.version,
            FORMAT_VERSION,
        )
    return artifact
