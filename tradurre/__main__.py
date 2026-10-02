import argparse
import socket
import threading
import time
import webbrowser

import uvicorn

from tradurre.app import FRONTEND_DIR
from tradurre.config import HOST, PORT


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
    parser.add_argument("--port", type=int, default=PORT, help=f"Port to listen on (default {PORT})")
    args = parser.parse_args()

    url = f"http://{HOST}:{args.port}"
    if not args.dev:
        if not (FRONTEND_DIR / "index.html").is_file():
            print(f"warning: no built frontend in {FRONTEND_DIR}; run `npm run build` in frontend/ first.")
        print(f"Tradurre is running at {url} -- close this window (or press Ctrl+C) to stop it.", flush=True)
        if not args.no_browser:
            threading.Thread(target=_open_browser_when_ready, args=(url, HOST, args.port), daemon=True).start()

    uvicorn.run("tradurre.app:app", host=HOST, port=args.port, reload=args.dev)


if __name__ == "__main__":
    main()
