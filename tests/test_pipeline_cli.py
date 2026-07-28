"""Tests for the pipeline_cli entrypoint, run with heavy stages disabled
(no 'align' extra installed in this environment) -- exercises argument
parsing, file I/O, and artifact writing against the baseline anchor aligner.
"""

import json

from tradurre.services.pipeline_cli import main


def test_writes_artifact_and_log(tmp_path):
    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    source.write_text("Marie went home. She was tired.")
    target.write_text("Marie e' andata a casa. Era stanca.")
    out = tmp_path / "out" / "artifact.json"

    rc = main([
        "--source", str(source),
        "--target", str(target),
        "--source-lang", "en",
        "--target-lang", "it",
        "--title", "Test Book",
        "--out", str(out),
        "--no-embeddings",
        "--no-llm-judge",
    ])

    assert rc == 0
    assert out.exists()
    log_path = out.with_suffix(out.suffix + ".log")
    assert log_path.exists()
    assert "pipeline_cli" in log_path.read_text()

    artifact = json.loads(out.read_text())
    assert artifact["format"] == "tradurre-aligned-bitext"
    assert artifact["title"] == "Test Book"
    assert artifact["source_lang"] == "en"
    assert artifact["target_lang"] == "it"
    assert len(artifact["sections"]) > 0


def test_missing_source_file_returns_error(tmp_path):
    rc = main([
        "--source", str(tmp_path / "missing.txt"),
        "--target", str(tmp_path / "also_missing.txt"),
        "--source-lang", "en",
        "--target-lang", "it",
        "--out", str(tmp_path / "out.json"),
    ])
    assert rc == 1
