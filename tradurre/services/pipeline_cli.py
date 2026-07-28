"""Command-line entrypoint for running the heavy alignment pipeline standalone.

Meant to run in an environment with the `align` (and optionally `pdf`) extras
installed -- typically a Colab GPU session, not the local app. Wraps
tradurre.services.pipeline.build_aligned_artifact: reads two source files,
runs the full baseline/embedding/LLM-judge chain, and writes the resulting
AlignedArtifact as downloadable JSON.

Logs generously to both stdout and a sidecar .log file next to the output
artifact, since the person running this on Colab may only have the downloaded
files to debug from after the session ends.

Usage:
    uv run python -m tradurre.services.pipeline_cli \\
        --source source.docx --target target.docx \\
        --source-lang en --target-lang it \\
        --title "My Book" \\
        --out aligned_artifact.json
"""

import argparse
import logging
import sys
from pathlib import Path

from tradurre.services import artifact_io, pipeline


def _setup_logging(log_path: Path) -> None:
    root = logging.getLogger("tradurre")
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S"
    )

    stream = logging.StreamHandler(sys.stdout)
    stream.setLevel(logging.INFO)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", required=True, type=Path, help="Source-language file (.txt/.docx/.pdf)")
    parser.add_argument("--target", required=True, type=Path, help="Target-language file (.txt/.docx/.pdf)")
    parser.add_argument("--source-lang", required=True, help="Source language code, e.g. 'en'")
    parser.add_argument("--target-lang", required=True, help="Target language code, e.g. 'it'")
    parser.add_argument("--title", default="", help="Project title to embed in the artifact")
    parser.add_argument("--out", required=True, type=Path, help="Path to write the aligned artifact JSON")
    parser.add_argument("--no-embeddings", action="store_true", help="Skip the embedding-rescoring stage")
    parser.add_argument("--no-llm-judge", action="store_true", help="Skip the LLM-judge stage")
    parser.add_argument("--embedding-model", default=None, help="Override the sentence-embedding model")
    parser.add_argument("--llm-model", default=None, help="Override the LLM judge model")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    out_path: Path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = out_path.with_suffix(out_path.suffix + ".log")
    _setup_logging(log_path)

    logger = logging.getLogger("tradurre.pipeline_cli")
    logger.info("source=%s target=%s -> out=%s", args.source, args.target, out_path)

    if not args.source.exists():
        logger.error("source file not found: %s", args.source)
        return 1
    if not args.target.exists():
        logger.error("target file not found: %s", args.target)
        return 1

    source_bytes = args.source.read_bytes()
    target_bytes = args.target.read_bytes()

    try:
        artifact = pipeline.build_aligned_artifact(
            source_bytes,
            target_bytes,
            args.source.name,
            args.target.name,
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            title=args.title,
            use_embeddings=not args.no_embeddings,
            use_llm_judge=not args.no_llm_judge,
            embedding_model=args.embedding_model,
            llm_model=args.llm_model,
        )
    except Exception:
        logger.exception("pipeline failed")
        return 1

    out_path.write_text(artifact_io.serialize_artifact(artifact), encoding="utf-8")
    logger.info("wrote artifact to %s (log: %s)", out_path, log_path)
    logger.info("stats: %s", artifact.stats)
    if artifact.warnings:
        logger.warning("artifact has %d warning(s): %s", len(artifact.warnings), artifact.warnings)

    return 0


if __name__ == "__main__":
    sys.exit(main())
