from __future__ import annotations

import asyncio
import gzip
import json
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from .auth import make_session_cookie, require_ingest_auth, require_ui_session, COOKIE_NAME
from .export import build_markdown
from .importers.inference_log import correlate_and_store, parse_llama_server_log
from .importers.opencode_storage import import_storage
from .retention import db_size_bytes, delete_session

router = APIRouter()


def _settings(request: Request):
    return request.app.state.settings


def _conn(request: Request):
    return request.app.state.conn


# ---------------------------------------------------------------- health --

@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request):
    if not getattr(request.app.state, "ready", False):
        raise HTTPException(status_code=503, detail="not ready")
    return {"status": "ready"}


@router.get("/stats")
async def stats(request: Request):
    conn = _conn(request)
    settings = _settings(request)
    sources = conn.execute("SELECT COUNT(*) AS n FROM sources").fetchone()["n"]
    sessions = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
    events = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    return {
        "sources": sources,
        "sessions": sessions,
        "events": events,
        "db_size_bytes": db_size_bytes(settings.db_path),
    }


# ------------------------------------------------------------------ auth --

class LoginBody(BaseModel):
    password: str


@router.post("/auth/login")
async def login(body: LoginBody, request: Request):
    settings = _settings(request)
    if not settings.ui_password:
        return JSONResponse({"status": "ok", "auth_disabled": True})
    if body.password != settings.ui_password:
        raise HTTPException(status_code=401, detail="invalid password")
    token = make_session_cookie(settings)
    response = JSONResponse({"status": "ok"})
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict", max_age=60 * 60 * 24 * 30)
    return response


@router.post("/auth/logout")
async def logout():
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(COOKIE_NAME)
    return response


# ---------------------------------------------------------------- ingest --

@router.post("/events/batch")
async def events_batch(request: Request):
    settings = _settings(request)
    require_ingest_auth(request, settings)

    raw = await request.body()
    if request.headers.get("content-encoding") == "gzip":
        try:
            raw = gzip.decompress(raw)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"invalid gzip body: {exc}") from None

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from None

    events = body.get("events")
    if not isinstance(events, list):
        raise HTTPException(status_code=400, detail="events must be a list")

    worker = request.app.state.worker
    result = await worker.submit(events)
    return {
        "accepted": result.accepted,
        "duplicates": result.duplicates,
        "rejected": result.rejected,
        "errors": result.errors,
    }


# -------------------------------------------------------------- sources --

@router.get("/sources")
async def list_sources(request: Request):
    require_ui_session(request, _settings(request))
    conn = _conn(request)
    rows = conn.execute(
        """
        SELECT s.*, COUNT(se.id) AS session_count,
               MAX(se.updated_at) AS last_session_at,
               SUM(CASE WHEN se.status IN ('busy', 'retry') THEN 1 ELSE 0 END) AS active_count
        FROM sources s
        LEFT JOIN sessions se ON se.source_id = s.id
        GROUP BY s.id
        ORDER BY s.last_seen_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


class RenameSourceBody(BaseModel):
    display_name: str | None = None


@router.patch("/sources/{source_id}")
async def rename_source(source_id: str, body: RenameSourceBody, request: Request):
    require_ui_session(request, _settings(request))
    conn = _conn(request)
    cur = conn.execute("UPDATE sources SET display_name = ? WHERE id = ?", (body.display_name, source_id))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="source not found")
    return {"status": "ok"}


# ------------------------------------------------------------- sessions --

@router.get("/sessions")
async def list_sessions(
    request: Request,
    source_id: str | None = None,
    project: str | None = None,
    status: str | None = None,
    model: str | None = None,
    has_errors: bool | None = None,
    has_detections: bool | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 100,
):
    require_ui_session(request, _settings(request))
    conn = _conn(request)

    clauses = []
    params: list = []
    if source_id:
        clauses.append("s.source_id = ?")
        params.append(source_id)
    if project:
        clauses.append("s.project = ?")
        params.append(project)
    if status:
        clauses.append("s.status = ?")
        params.append(status)
    if model:
        clauses.append("s.model = ?")
        params.append(model)
    if has_errors:
        clauses.append("(s.error_count > 0 OR s.tool_errors > 0)")
    if since:
        clauses.append("s.created_at >= ?")
        params.append(since)
    if until:
        clauses.append("s.created_at <= ?")
        params.append(until)
    if q:
        clauses.append(
            "(s.title LIKE ? OR EXISTS (SELECT 1 FROM parts p WHERE p.session_id = s.id AND (p.text LIKE ? OR p.output_text LIKE ?)))"
        )
        like = f"%{q}%"
        params.extend([like, like, like])
    if has_detections:
        clauses.append("EXISTS (SELECT 1 FROM detections d WHERE d.session_id = s.id)")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT s.* FROM sessions s {where} ORDER BY s.created_at DESC LIMIT ?", (*params, limit)
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    require_ui_session(request, _settings(request))
    conn = _conn(request)
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    messages = conn.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY seq", (session_id,)).fetchall()
    parts = conn.execute("SELECT * FROM parts WHERE session_id = ? ORDER BY seq", (session_id,)).fetchall()
    detections = conn.execute("SELECT * FROM detections WHERE session_id = ? ORDER BY level", (session_id,)).fetchall()
    todos = conn.execute("SELECT * FROM todo_snapshots WHERE session_id = ? ORDER BY id", (session_id,)).fetchall()
    children = conn.execute(
        "SELECT id, title, status, agent, created_at FROM sessions WHERE parent_id = ? ORDER BY created_at", (session_id,)
    ).fetchall()
    inference = conn.execute("SELECT * FROM inference_spans WHERE session_id = ?", (session_id,)).fetchall()
    context_snapshots = conn.execute(
        "SELECT * FROM context_snapshots WHERE session_id = ? ORDER BY id", (session_id,)
    ).fetchall()

    tool_stats: dict[str, dict] = {}
    for p in parts:
        if p["type"] != "tool":
            continue
        s = tool_stats.setdefault(p["tool_name"] or "?", {"calls": 0, "errors": 0, "total_ms": 0, "tokens_est": 0})
        s["calls"] += 1
        if p["status"] == "error":
            s["errors"] += 1
        s["total_ms"] += p["duration_ms"] or 0
        s["tokens_est"] += p["output_tokens_est"] or 0

    # output_tokens_est also covers text/reasoning content (falls back to p.text when there's
    # no tool output - see indexer.py); input_tokens_est covers tool call arguments, which
    # used to be invisible here entirely despite counting toward the model's real context.
    context_attribution = sorted(
        (
            {
                "part_id": p["id"],
                "seq": p["seq"],
                "tool_name": p["tool_name"],
                "output_tokens_est": p["output_tokens_est"],
                "input_tokens_est": p["input_tokens_est"],
            }
            for p in parts
            if p["output_tokens_est"] or p["input_tokens_est"]
        ),
        key=lambda x: -((x["output_tokens_est"] or 0) + (x["input_tokens_est"] or 0)),
    )[:15]

    context_growth = [
        {"seq": m["seq"], "tokens_input": m["tokens_input"], "message_id": m["id"]} for m in messages if m["role"] == "assistant"
    ]

    # Best-effort link from a `task` call (a "subtask" part) to the child
    # session it spawned. Nothing in the event stream names that child
    # session directly, so this pairs subtask parts and same-agent children
    # in chronological order within each agent group - correct as long as
    # subagents of the same name run sequentially, not concurrently (true
    # for this deployment, not guaranteed in general). Never claimed as
    # exact: exposed as {"match": "heuristic"}.
    part_rows = [dict(p) for p in parts]
    children_by_agent: dict[str, list[dict]] = {}
    for c in children:
        children_by_agent.setdefault(c["agent"] or "", []).append(dict(c))
    subtask_seen: dict[str, int] = {}
    for p in part_rows:
        if p["type"] != "subtask" or not p.get("input_json"):
            continue
        try:
            agent_name = json.loads(p["input_json"]).get("agent")
        except (json.JSONDecodeError, AttributeError):
            agent_name = None
        candidates = children_by_agent.get(agent_name or "", [])
        idx = subtask_seen.get(agent_name or "", 0)
        if agent_name and idx < len(candidates):
            p["linked_session_id"] = candidates[idx]["id"]
            p["linked_session_match"] = "heuristic"
            subtask_seen[agent_name or ""] = idx + 1

    return {
        "session": dict(session),
        "messages": [dict(m) for m in messages],
        "parts": part_rows,
        "detections": [dict(d) for d in detections],
        "todo_snapshots": [dict(t) for t in todos],
        "children": [dict(c) for c in children],
        "inference_spans": [dict(i) for i in inference],
        "context_snapshots": [dict(c) for c in context_snapshots],
        "tool_stats": tool_stats,
        "context_attribution": context_attribution,
        "context_growth": context_growth,
    }


class UpdateSessionBody(BaseModel):
    notes: str | None = None


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, body: UpdateSessionBody, request: Request):
    require_ui_session(request, _settings(request))
    conn = _conn(request)
    cur = conn.execute("UPDATE sessions SET notes = ? WHERE id = ?", (body.notes, session_id))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="session not found")
    return {"status": "ok"}


@router.get("/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    request: Request,
    format: str = "md",
    limit: int = 1500,
    redact: bool = False,
    include_children: bool = False,
):
    require_ui_session(request, _settings(request))
    if format != "md":
        raise HTTPException(status_code=400, detail="only format=md is supported")
    conn = _conn(request)
    md = build_markdown(conn, session_id, limit=limit, redact=redact, include_children=include_children)
    if md is None:
        raise HTTPException(status_code=404, detail="session not found")
    return PlainTextResponse(md, media_type="text/markdown")


@router.get("/sessions/{session_id}/stream")
async def stream_session(session_id: str, request: Request):
    require_ui_session(request, _settings(request))
    bus = request.app.state.bus
    queue = bus.subscribe(session_id)

    async def event_source():
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    await asyncio.wait_for(queue.get(), timeout=15)
                    yield "event: update\ndata: {}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bus.unsubscribe(session_id, queue)

    return StreamingResponse(event_source(), media_type="text/event-stream")


# -------------------------------------------------------------- imports --

class ImportStorageBody(BaseModel):
    path: str
    source_name: str


@router.post("/import/storage")
async def import_storage_endpoint(body: ImportStorageBody, request: Request):
    require_ui_session(request, _settings(request))
    conn = _conn(request)
    settings = _settings(request)
    try:
        result = await asyncio.to_thread(import_storage, conn, settings, body.path, body.source_name)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {
        "accepted": result.accepted,
        "duplicates": result.duplicates,
        "rejected": result.rejected,
        "sessions_touched": len(result.touched_sessions),
    }


class ImportInferenceBody(BaseModel):
    source_name: str
    format: str = "llama-server"
    log: str
    session_id: str | None = None


@router.post("/import/inference")
async def import_inference_endpoint(body: ImportInferenceBody, request: Request):
    require_ui_session(request, _settings(request))
    if body.format != "llama-server":
        raise HTTPException(status_code=400, detail="only format=llama-server is supported")
    conn = _conn(request)
    spans = parse_llama_server_log(body.log)

    target_session = body.session_id
    if not target_session:
        row = conn.execute(
            """
            SELECT s.id FROM sessions s JOIN sources src ON src.id = s.source_id
            WHERE src.name = ? ORDER BY s.created_at DESC LIMIT 1
            """,
            (body.source_name,),
        ).fetchone()
        target_session = row["id"] if row else None

    if not target_session:
        return {"parsed_spans": len(spans), "stored": 0, "reason": "no matching session found"}

    stored = await asyncio.to_thread(correlate_and_store, conn, target_session, spans)
    return {"parsed_spans": len(spans), "stored": stored, "session_id": target_session}


# ----------------------------------------------------- redaction rules --

@router.get("/settings/redact-patterns")
async def list_redact_patterns(request: Request):
    require_ui_session(request, _settings(request))
    conn = _conn(request)
    rows = conn.execute("SELECT * FROM redact_patterns ORDER BY id").fetchall()
    return [dict(r) for r in rows]


class RedactPatternBody(BaseModel):
    pattern: str


@router.post("/settings/redact-patterns")
async def add_redact_pattern(body: RedactPatternBody, request: Request):
    require_ui_session(request, _settings(request))
    try:
        re.compile(body.pattern)
    except re.error as exc:
        raise HTTPException(status_code=400, detail=f"invalid regex: {exc}") from None
    conn = _conn(request)
    try:
        conn.execute(
            "INSERT INTO redact_patterns (pattern, enabled, is_default, created_at) VALUES (?, 1, 0, datetime('now'))",
            (body.pattern,),
        )
    except Exception as exc:  # noqa: BLE001 - UNIQUE constraint, surfaced as a normal 400
        raise HTTPException(status_code=400, detail=f"could not add pattern: {exc}") from None
    row = conn.execute("SELECT * FROM redact_patterns WHERE pattern = ?", (body.pattern,)).fetchone()
    return dict(row)


class UpdateRedactPatternBody(BaseModel):
    enabled: bool


@router.patch("/settings/redact-patterns/{pattern_id}")
async def toggle_redact_pattern(pattern_id: int, body: UpdateRedactPatternBody, request: Request):
    require_ui_session(request, _settings(request))
    conn = _conn(request)
    cur = conn.execute("UPDATE redact_patterns SET enabled = ? WHERE id = ?", (1 if body.enabled else 0, pattern_id))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="pattern not found")
    return {"status": "ok"}


@router.delete("/settings/redact-patterns/{pattern_id}")
async def delete_redact_pattern(pattern_id: int, request: Request):
    require_ui_session(request, _settings(request))
    conn = _conn(request)
    cur = conn.execute("DELETE FROM redact_patterns WHERE id = ?", (pattern_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="pattern not found")
    return {"status": "ok"}


# ------------------------------------------------------- storage admin --

@router.get("/admin/storage")
async def admin_storage(request: Request):
    require_ui_session(request, _settings(request))
    settings = _settings(request)
    return {"db_size_bytes": db_size_bytes(settings.db_path)}


class CleanupBody(BaseModel):
    older_than_days: int


@router.post("/admin/cleanup/estimate")
async def cleanup_estimate(body: CleanupBody, request: Request):
    require_ui_session(request, _settings(request))
    conn = _conn(request)
    cutoff = f"-{body.older_than_days} days"
    row = conn.execute(
        """
        SELECT COUNT(*) AS session_count,
               COALESCE((
                   SELECT SUM(LENGTH(e.payload_json)) FROM events e WHERE e.session_id IN (
                       SELECT id FROM sessions WHERE created_at IS NOT NULL AND created_at < datetime('now', ?)
                   )
               ), 0) AS events_chars,
               COALESCE((
                   SELECT SUM(p.output_bytes) FROM parts p WHERE p.session_id IN (
                       SELECT id FROM sessions WHERE created_at IS NOT NULL AND created_at < datetime('now', ?)
                   )
               ), 0) AS parts_bytes
        FROM sessions WHERE created_at IS NOT NULL AND created_at < datetime('now', ?)
        """,
        (cutoff, cutoff, cutoff),
    ).fetchone()
    # events_chars is a character count (SQLite LENGTH on TEXT), not exact
    # bytes - close enough for an estimate, always presented with "≈".
    estimated_bytes = int(row["events_chars"]) + int(row["parts_bytes"] or 0)
    return {"sessions_count": row["session_count"], "estimated_bytes": estimated_bytes}


@router.post("/admin/cleanup/execute")
async def cleanup_execute(body: CleanupBody, request: Request):
    require_ui_session(request, _settings(request))
    conn = _conn(request)
    cutoff = f"-{body.older_than_days} days"
    rows = conn.execute(
        "SELECT id FROM sessions WHERE created_at IS NOT NULL AND created_at < datetime('now', ?)", (cutoff,)
    ).fetchall()
    for row in rows:
        await asyncio.to_thread(delete_session, conn, row["id"])
    return {"deleted_sessions": len(rows)}


class MergeSourcesBody(BaseModel):
    from_id: str
    into_id: str


@router.post("/admin/sources/merge")
async def merge_sources(body: MergeSourcesBody, request: Request):
    """Reassigns every session/event from one source to another and drops the now-empty
    source row. Exists because source_id is derived from the agent's hostname+name (see
    opencode-log-plugin), which can change across a container recreation - the same physical
    agent then shows up as a brand new source until merged here."""
    require_ui_session(request, _settings(request))
    conn = _conn(request)
    if body.from_id == body.into_id:
        raise HTTPException(status_code=400, detail="from_id and into_id must differ")
    from_row = conn.execute("SELECT * FROM sources WHERE id = ?", (body.from_id,)).fetchone()
    into_row = conn.execute("SELECT * FROM sources WHERE id = ?", (body.into_id,)).fetchone()
    if not from_row or not into_row:
        raise HTTPException(status_code=404, detail="source not found")

    conn.execute("BEGIN IMMEDIATE")
    try:
        sessions_moved = conn.execute(
            "UPDATE sessions SET source_id = ? WHERE source_id = ?", (body.into_id, body.from_id)
        ).rowcount
        events_moved = conn.execute(
            "UPDATE events SET source_id = ? WHERE source_id = ?", (body.into_id, body.from_id)
        ).rowcount
        conn.execute(
            "UPDATE sources SET first_seen_at = MIN(first_seen_at, ?), last_seen_at = MAX(last_seen_at, ?) WHERE id = ?",
            (from_row["first_seen_at"], from_row["last_seen_at"], body.into_id),
        )
        conn.execute("DELETE FROM sources WHERE id = ?", (body.from_id,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"sessions_moved": sessions_moved, "events_moved": events_moved}
