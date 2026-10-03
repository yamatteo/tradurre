import sys
from importlib.metadata import version

import pytest

from tradurre.__main__ import _stale_build, main


def test_version_flag(monkeypatch, capsys):
    # start-tradurre.bat parses the second token of this line to decide whether to upgrade.
    monkeypatch.setattr(sys, "argv", ["tradurre", "--version"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert capsys.readouterr().out.split() == ["tradurre", version("tradurre")]


def _tree(tmp_path, source_mtime, built_mtime):
    """A frontend/ checkout and a static/ build with the given modification times."""
    import os

    frontend, static = tmp_path / "frontend", tmp_path / "static"
    (frontend / "src" / "views").mkdir(parents=True)
    static.mkdir()
    for path in (frontend / "src" / "views" / "BookView.vue", frontend / "index.html", frontend / "package.json"):
        path.write_text("x")
        os.utime(path, (source_mtime, source_mtime))
    (static / "index.html").write_text("x")
    os.utime(static / "index.html", (built_mtime, built_mtime))
    return frontend, static


def test_newer_source_means_a_stale_build(tmp_path):
    assert _stale_build(*_tree(tmp_path, source_mtime=2_000, built_mtime=1_000))


def test_older_source_is_not_stale(tmp_path):
    assert not _stale_build(*_tree(tmp_path, source_mtime=1_000, built_mtime=2_000))


def test_no_frontend_checkout_is_not_stale(tmp_path):
    frontend, static = _tree(tmp_path, source_mtime=2_000, built_mtime=1_000)
    assert not _stale_build(tmp_path / "missing", static)


def test_no_build_is_not_stale(tmp_path):
    frontend, static = _tree(tmp_path, source_mtime=2_000, built_mtime=1_000)
    (static / "index.html").unlink()
    assert not _stale_build(frontend, static)
