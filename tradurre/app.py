from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from tradurre.config import DB_PATH
from tradurre.db import get_connection, init_db

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(DB_PATH)
    init_db(conn)
    app.state.db = conn
    yield
    conn.close()


app = FastAPI(title="Tradurre", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from tradurre.api import projects, pairs, search, import_, export  # noqa: E402, F401

app.include_router(projects.router, prefix="/api/v1")
app.include_router(pairs.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(import_.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")

# Serve frontend static files (production mode)
if FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="static")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Serve index.html for all non-API routes (SPA client-side routing)
        return FileResponse(FRONTEND_DIR / "index.html")
