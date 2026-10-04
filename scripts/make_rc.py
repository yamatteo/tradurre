"""Put together the release candidate folder for the Windows checklist (PLAN.md, "Release candidate wheel").

    npm --prefix frontend run build
    uv build --wheel
    uv run python scripts/make_rc.py

Rebuilds `dist/tradurre-rc/` from the built wheel: the wheel, the launcher filled in with this version and the wheel's
`file:///C:/tradurre-rc/` URL, the browser smoke test, the checklist and its fixtures; then zips it as
`dist/tradurre-rc.zip`. Unzipped into `C:\\`, it is the `C:\\tradurre-rc\\` that `packaging/WINDOWS-CHECKLIST.md`
expects. Nothing is published: the candidate travels by hand.
"""

import shutil
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
NAME = "tradurre-rc"
FIXTURES = ["easy.source.docx", "easy.target.pdf", "easy.source.txt", "easy.target.txt"]


def main() -> int:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    wheel = DIST / f"tradurre-{version}-py3-none-any.whl"
    if not wheel.is_file():
        print(f"{wheel.relative_to(ROOT)} not found: run `npm --prefix frontend run build` and `uv build --wheel`")
        return 1
    with zipfile.ZipFile(wheel) as zf:
        if "tradurre/static/index.html" not in zf.namelist():
            print(f"{wheel.name} has no tradurre/static/index.html: run `npm --prefix frontend run build` first")
            return 1

    folder = DIST / NAME
    shutil.rmtree(folder, ignore_errors=True)
    (folder / "fixtures").mkdir(parents=True)
    shutil.copy2(wheel, folder / wheel.name)
    # On the bytes, so the launcher keeps its CRLF line endings: cmd mis-parses LF-only batch files.
    launcher = (ROOT / "packaging" / "start-tradurre.bat").read_bytes()
    launcher = launcher.replace(b"__VERSION__", version.encode())
    launcher = launcher.replace(b"__WHEEL_URL__", f"file:///C:/{NAME}/{wheel.name}".encode())
    (folder / "start-tradurre.bat").write_bytes(launcher)
    for name in ("smoke.py", "WINDOWS-CHECKLIST.md"):
        shutil.copy2(ROOT / "packaging" / name, folder / name)
    for name in FIXTURES:
        shutil.copy2(ROOT / "tests" / "fixtures" / name, folder / "fixtures" / name)

    archive = DIST / f"{NAME}.zip"
    archive.unlink(missing_ok=True)
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.relative_to(DIST).as_posix())  # the folder at the zip's root
    for path in files:
        print(path.relative_to(DIST).as_posix())
    print(f"→ {archive.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
