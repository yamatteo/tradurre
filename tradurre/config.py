import os
from pathlib import Path

# TRADURRE_DB points the app at another database (the e2e tests use a throwaway one).
_DB_ENV = os.environ.get("TRADURRE_DB")
DB_PATH: Path = Path(_DB_ENV) if _DB_ENV else Path.home() / ".tradurre" / "tradurre.db"
HOST: str = "127.0.0.1"
PORT: int = 8000
