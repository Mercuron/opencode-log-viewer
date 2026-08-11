from __future__ import annotations

import argparse
import sys

from .config import get_settings
from .db import open_db
from .importers.inference_log import correlate_and_store, parse_llama_server_log
from .importers.opencode_storage import import_storage
from .indexer import reindex_session
from .migrations import apply_migrations
from .retention import apply_retention


def _open(settings=None):
    settings = settings or get_settings()
    conn = open_db(settings)
    apply_migrations(conn)
    return conn, settings


def cmd_import(args: argparse.Namespace) -> int:
    conn, settings = _open()
    result = import_storage(conn, settings, args.path, args.source)
    print(f"accepted={result.accepted} duplicates={result.duplicates} rejected={result.rejected} sessions={len(result.touched_sessions)}")
    if result.errors:
        print(f"errors: {result.errors[:5]}", file=sys.stderr)
    return 0


def cmd_import_inference(args: argparse.Namespace) -> int:
    conn, settings = _open()
    with open(args.file, encoding="utf-8", errors="replace") as f:
        log_text = f.read()
    spans = parse_llama_server_log(log_text)
    session_id = args.session_id
    if not session_id:
        row = conn.execute(
            "SELECT s.id FROM sessions s JOIN sources src ON src.id = s.source_id WHERE src.name = ? ORDER BY s.created_at DESC LIMIT 1",
            (args.source,),
        ).fetchone()
        session_id = row["id"] if row else None
    if not session_id:
        print("no matching session found for --source; pass --session-id explicitly", file=sys.stderr)
        return 1
    stored = correlate_and_store(conn, session_id, spans)
    print(f"parsed_spans={len(spans)} stored={stored} session_id={session_id}")
    return 0


def cmd_reindex(args: argparse.Namespace) -> int:
    conn, _settings = _open()
    if args.session:
        conn.execute("BEGIN IMMEDIATE")
        try:
            reindex_session(conn, args.session)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        print(f"reindexed session {args.session}")
        return 0

    session_ids = [r["id"] for r in conn.execute("SELECT DISTINCT session_id FROM events WHERE session_id IS NOT NULL")]
    for sid in session_ids:
        conn.execute("BEGIN IMMEDIATE")
        try:
            reindex_session(conn, sid)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    print(f"reindexed {len(session_ids)} session(s)")
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    conn, settings = _open()
    deleted = apply_retention(conn, settings)
    print(f"deleted {len(deleted)} session(s)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="viewer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="import historical OpenCode storage")
    p_import.add_argument("--path", required=True)
    p_import.add_argument("--source", required=True)
    p_import.set_defaults(func=cmd_import)

    p_inf = sub.add_parser("import-inference", help="import llama-server inference log")
    p_inf.add_argument("--format", default="llama-server", choices=["llama-server"])
    p_inf.add_argument("--file", required=True)
    p_inf.add_argument("--source", required=True)
    p_inf.add_argument("--session-id", default=None)
    p_inf.set_defaults(func=cmd_import_inference)

    p_reindex = sub.add_parser("reindex", help="rebuild normalized tables from raw events")
    p_reindex.add_argument("--session", default=None)
    p_reindex.set_defaults(func=cmd_reindex)

    p_prune = sub.add_parser("prune", help="run retention immediately")
    p_prune.set_defaults(func=cmd_prune)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
