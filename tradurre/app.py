from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from tradurre.config import DB_PATH
from tradurre.db import get_connection, init_db

# Populated by `npm run build` in frontend/ (vite outDir), and shipped inside the wheel.
FRONTEND_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(DB_PATH)
    try:
        init_db(conn)
    finally:
        conn.close()
    app.state.db_path = DB_PATH
    yield


app = FastAPI(title="Tradurre", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from tradurre.api import projects, pairs, search, import_, export, books  # noqa: E402, F401

app.include_router(projects.router, prefix="/api/v1")
app.include_router(pairs.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(import_.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")
app.include_router(books.router, prefix="/api/v2")

# Serve frontend static files (production mode)
if FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="static")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Real files at the root (e.g. favicon.ico from frontend/public) are served
        # as-is; anything else gets index.html for SPA client-side routing.
        candidate = (FRONTEND_DIR / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(FRONTEND_DIR.resolve()):
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIR / "index.html")
