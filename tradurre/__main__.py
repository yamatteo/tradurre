import argparse
import socket
import threading
import time
import webbrowser
from importlib.metadata import version
from pathlib import Path

import uvicorn

from tradurre.app import FRONTEND_DIR
from tradurre.config import HOST, PORT

# Only in a source checkout: an installed wheel has no frontend/ next to the package.
FRONTEND_SRC = Path(__file__).resolve().parent.parent / "frontend"


def _stale_build(frontend_src: Path, static: Path) -> bool:
    """Whether the built frontend in `static` is older than the frontend sources in `frontend_src`."""
    built = static / "index.html"
    if not frontend_src.is_dir() or not built.is_file():
        return False
    sources = [p for p in (frontend_src / "src").rglob("*") if p.is_file()]
    sources += [p for p in (frontend_src / "index.html", frontend_src / "package.json") if p.is_file()]
    return any(p.stat().st_mtime > built.stat().st_mtime for p in sources)


def _open_browser_when_ready(url: str, host: str, port: int, timeout: float = 30.0) -> None:
    # Poll until uvicorn accepts connections rather than guessing a delay: first
    # startup (schema creation, slow disks) can take a while.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    else:
        return
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(prog="tradurre", description="Literary translation workbench")
    parser.add_argument("--dev", action="store_true", help="Development mode: auto-reload on code changes, don't open a browser")
    parser.add_argument("--no-browser", action="store_true", help="Don't open the browser on startup")
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('tradurre')}")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port to listen on (default {PORT})")
    args = parser.parse_args()

    url = f"http://{HOST}:{args.port}"
    if _stale_build(FRONTEND_SRC, FRONTEND_DIR):
        print(f"warning: the built frontend in {FRONTEND_DIR} is older than frontend/src; run 'npm run build' in "
              "frontend/ (or use the Vite dev server on http://localhost:5173 with --dev).", flush=True)
    if not args.dev:
        if not (FRONTEND_DIR / "index.html").is_file():
            print(f"warning: no built frontend in {FRONTEND_DIR}; run `npm run build` in frontend/ first.")
        print(f"Tradurre is running at {url} -- close this window (or press Ctrl+C) to stop it.", flush=True)
        if not args.no_browser:
            threading.Thread(target=_open_browser_when_ready, args=(url, HOST, args.port), daemon=True).start()

    uvicorn.run("tradurre.app:app", host=HOST, port=args.port, reload=args.dev)


if __name__ == "__main__":
    main()
