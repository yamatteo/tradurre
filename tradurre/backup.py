"""Database snapshots at start (SPEC §4 "Never lose work"; PLAN.md, "Database snapshots at start").

Each start copies the database into `backups/` next to it, keeping the last 10. They protect against an app bug, a
bad migration or a bad correction; not against losing the disk.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def snapshot(db_path: Path, keep: int = 10, now: datetime | None = None) -> Path | None:
    """Copy the database at `db_path` to `backups/<stem>-<YYYYmmdd-HHMMSS>.db` and drop all but the `keep` newest.

    Returns the snapshot's path, or None when there is no database yet or the snapshot failed: a failed snapshot
    never stops the app.
    """
    if not db_path.is_file():
        return None
    folder = db_path.parent / "backups"
    try:
        folder.mkdir(exist_ok=True)
        base = f"{db_path.stem}-{(now or datetime.now(timezone.utc)):%Y%m%d-%H%M%S}"
        target = folder / f"{base}.db"
        k = 2
        while target.exists():
            target = folder / f"{base}-{k}.db"
            k += 1
        src = sqlite3.connect(db_path)
        try:
            dst = sqlite3.connect(target)
            try:
                # The backup API copies a consistent database, WAL included.
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        # By stem: "x-120000-2" sorts after "x-120000", though "x-120000-2.db" sorts before "x-120000.db".
        snapshots = sorted(folder.glob(f"{db_path.stem}-*.db"), key=lambda p: p.stem)
        for old in snapshots[:-keep] if keep > 0 else snapshots:
            old.unlink()
        return target
    except (OSError, sqlite3.Error) as e:
        print(f"Tradurre: database snapshot failed: {e}", flush=True)
        return None
