from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

_FILENAME_RE = re.compile(r"^(\d+)_.*\.sql$")


def migrations_dir() -> Path:
    env = os.environ.get("VIEWER_MIGRATIONS_DIR")
    if env:
        return Path(env)
    cwd_candidate = Path.cwd() / "migrations"
    if cwd_candidate.is_dir():
        return cwd_candidate
    return Path(__file__).resolve().parents[1] / "migrations"


def discover_migrations(directory: Path) -> list[tuple[int, Path]]:
    items = []
    for f in directory.glob("*.sql"):
        m = _FILENAME_RE.match(f.name)
        if not m:
            continue
        items.append((int(m.group(1)), f))
    return sorted(items, key=lambda x: x[0])


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def apply_migrations(conn: sqlite3.Connection, directory: Path | None = None) -> int:
    directory = directory or migrations_dir()
    version = current_version(conn)
    applied = 0
    for number, path in discover_migrations(directory):
        if number <= version:
            continue
        sql = path.read_text(encoding="utf-8")
        # executescript() issues its own implicit commit before running, so
        # it cannot be wrapped in a manual BEGIN/COMMIT here.
        conn.executescript(sql)
        conn.execute(f"PRAGMA user_version = {number}")
        applied += 1
    return applied
