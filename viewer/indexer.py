from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from .intervals import covered_ms
from .tokenest import estimate_tokens


def iso_ms(ms: int | float | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def parse_iso(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return None


class _Session:
    def __init__(self, id_: str):
        self.id = id_
        self.source_id: str | None = None
        self.parent_id: str | None = None
        self.title: str | None = None
        self.project: str | None = None
        self.directory: str | None = None
        self.status: str | None = None
        self.created_ms: int | None = None
        self.updated_ms: int | None = None
        self.completed_ms: int | None = None
        self.model: str | None = None
        self.provider: str | None = None
        self.agent: str | None = None
        self.compactions = 0
        self.error_count = 0
        self.imported = 0


class _Message:
    def __init__(self, id_: str, seq: int):
        self.id = id_
        self.seq = seq
        self.role: str | None = None
        self.started_ms: int | None = None
        self.completed_ms: int | None = None
        self.model: str | None = None
        self.provider: str | None = None
        self.agent: str | None = None
        self.tokens = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0}
        self.finish_reason: str | None = None
        self.error: str | None = None


class _Part:
    def __init__(self, id_: str, message_id: str | None, seq: int, type_: str):
        self.id = id_
        self.message_id = message_id
        self.seq = seq
        self.type = type_
        self.started_ms: int | None = None
        self.ended_ms: int | None = None
        self.tool_name: str | None = None
        self.call_id: str | None = None
        self.status: str | None = None
        self.title: str | None = None
        self.error: str | None = None
        self.text: str | None = None
        self.input: Any = None
        self.output_text: str | None = None
        self.metadata: Any = None


def _fetch_events(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM events WHERE session_id = ? ORDER BY sequence ASC, observed_at ASC",
        (session_id,),
    ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["payload"] = json.loads(d["payload_json"])
        out.append(d)
    return out


def _wipe_session_derived(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM parts WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM todo_snapshots WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM detections WHERE session_id = ?", (session_id,))


def reindex_session(conn: sqlite3.Connection, session_id: str) -> None:
    """Rebuilds sessions/messages/parts/todo_snapshots for one session from
    its raw events. Caller owns the transaction. Safe to call repeatedly -
    fully deterministic given the same events (test #5: reindex parity)."""
    events = _fetch_events(conn, session_id)
    if not events:
        return

    session = _Session(session_id)
    messages: dict[str, _Message] = {}
    message_order: list[str] = []
    parts: dict[str, _Part] = {}
    pending_before: dict[str, dict] = {}
    pending_after: dict[str, dict] = {}
    todo_snapshots: list[tuple[str | None, list]] = []

    def get_message(mid: str) -> _Message:
        if mid not in messages:
            messages[mid] = _Message(mid, len(message_order))
            message_order.append(mid)
        return messages[mid]

    def apply_session_info(info: dict) -> None:
        session.title = info.get("title") or session.title
        session.parent_id = info.get("parentID") or session.parent_id
        time = info.get("time") or {}
        if time.get("created") is not None:
            session.created_ms = session.created_ms or time["created"]
        if time.get("updated") is not None:
            session.updated_ms = time["updated"]

    for ev in events:
        etype = ev["event_type"]
        payload = ev["payload"]
        context = json.loads(ev["context_json"]) if ev.get("context_json") else {}
        session.source_id = session.source_id or ev.get("source_id")
        session.imported = session.imported or ev.get("imported", 0)
        if context.get("project"):
            session.project = context["project"]
        if context.get("directory"):
            session.directory = context["directory"]

        if etype in ("session.created", "session.updated"):
            apply_session_info(payload.get("info") or {})
        elif etype == "session.deleted":
            session.status = "deleted"
        elif etype == "session.idle":
            session.status = "idle"
        elif etype == "session.status":
            status = (payload.get("status") or {}).get("type")
            if status:
                session.status = status
        elif etype == "session.compacted":
            session.compactions += 1
        elif etype == "session.error":
            session.error_count += 1
        elif etype == "message.updated":
            info = payload.get("info") or {}
            mid = info.get("id")
            if not mid:
                continue
            m = get_message(mid)
            m.role = info.get("role")
            time = info.get("time") or {}
            m.started_ms = time.get("created", m.started_ms)
            m.completed_ms = time.get("completed", m.completed_ms)
            if info.get("role") == "assistant":
                m.model = info.get("modelID")
                m.provider = info.get("providerID")
                m.agent = info.get("mode")
                tokens = info.get("tokens") or {}
                cache = tokens.get("cache") or {}
                m.tokens = {
                    "input": tokens.get("input", 0),
                    "output": tokens.get("output", 0),
                    "reasoning": tokens.get("reasoning", 0),
                    "cache_read": cache.get("read", 0),
                    "cache_write": cache.get("write", 0),
                }
                m.finish_reason = info.get("finish")
                err = info.get("error")
                m.error = (err or {}).get("data", {}).get("message") if err else None
                session.model = m.model or session.model
                session.provider = m.provider or session.provider
                session.agent = m.agent or session.agent
            else:
                m.model = info.get("model", {}).get("modelID") if isinstance(info.get("model"), dict) else m.model
                m.agent = info.get("agent") or m.agent
        elif etype == "message.part.updated":
            part = payload.get("part") or {}
            ptype = part.get("type")
            mid = part.get("messageID")
            if mid:
                get_message(mid)
            if ptype == "tool":
                call_id = part.get("callID")
                key = call_id or part.get("id")
                p = parts.get(key) or _Part(key, mid, len(parts), ptype)
                p.message_id = mid or p.message_id
                p.call_id = call_id
                p.tool_name = part.get("tool")
                state = part.get("state") or {}
                p.status = state.get("status")
                p.input = state.get("input")
                p.output_text = state.get("output", p.output_text)
                p.title = state.get("title", p.title)
                p.error = state.get("error")
                p.metadata = state.get("metadata")
                time = state.get("time") or {}
                p.started_ms = time.get("start", p.started_ms)
                p.ended_ms = time.get("end", p.ended_ms)
                parts[key] = p
                if call_id and call_id in pending_before:
                    before = pending_before.pop(call_id)
                    p.input = p.input or before.get("args")
                if call_id and call_id in pending_after:
                    after = pending_after.pop(call_id)
                    p.output_text = p.output_text or after.get("output")
                    p.title = p.title or after.get("title")
                    p.metadata = p.metadata or after.get("metadata")
            else:
                key = part.get("id")
                if not key:
                    continue
                p = parts.get(key) or _Part(key, mid, len(parts), ptype)
                p.message_id = mid or p.message_id
                time = part.get("time") or {}
                p.started_ms = time.get("start", p.started_ms)
                p.ended_ms = time.get("end", p.ended_ms)
                if ptype == "text":
                    p.text = part.get("text")
                elif ptype == "reasoning":
                    p.text = part.get("text")
                elif ptype == "step-finish":
                    tokens = part.get("tokens") or {}
                    cache = tokens.get("cache") or {}
                    p.metadata = {
                        "tokens_input": tokens.get("input", 0),
                        "tokens_output": tokens.get("output", 0),
                        "tokens_reasoning": tokens.get("reasoning", 0),
                        "tokens_cache_read": cache.get("read", 0),
                        "tokens_cache_write": cache.get("write", 0),
                        "reason": part.get("reason"),
                    }
                elif ptype == "subtask":
                    # A `task` call to a named subagent (e.g. a "scout"). This
                    # part never carries the spawned child session's id - only
                    # its own session.created (with parentID) does, so linking
                    # the two together is a best-effort, request-time join
                    # (see routes.py) rather than something stored here.
                    agent_name = part.get("agent") or "?"
                    p.tool_name = f"task:{agent_name}"
                    p.title = part.get("description")
                    p.input = {"agent": agent_name, "prompt": part.get("prompt"), "description": part.get("description")}
                parts[key] = p
        elif etype == "tool.execute.before":
            call_id = payload.get("callID")
            if call_id in parts:
                parts[call_id].input = parts[call_id].input or payload.get("args")
            else:
                pending_before[call_id] = payload
        elif etype == "tool.execute.after":
            call_id = payload.get("callID")
            if call_id in parts:
                p = parts[call_id]
                p.output_text = p.output_text or payload.get("output")
                p.title = p.title or payload.get("title")
                p.metadata = p.metadata or payload.get("metadata")
            else:
                pending_after[call_id] = payload
        elif etype == "todo.updated":
            todo_snapshots.append((ev.get("event_time") or ev.get("observed_at"), payload.get("todos") or []))

    # Session-level fallbacks if no session.created/updated ever arrived.
    if session.created_ms is None and events:
        session.created_ms = parse_iso(events[0].get("event_time") or events[0]["observed_at"])
    if session.updated_ms is None and events:
        session.updated_ms = parse_iso(events[-1].get("event_time") or events[-1]["observed_at"])
    if message_order:
        last_msg = messages[message_order[-1]]
        session.completed_ms = last_msg.completed_ms or session.updated_ms

    _wipe_session_derived(conn, session_id)

    # Minimal upsert first: messages/parts below carry FK references to
    # sessions(id), which must exist before they're inserted.
    conn.execute(
        """
        INSERT INTO sessions (id, source_id, parent_id, title, project, directory, status, created_at, updated_at, imported)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            source_id=excluded.source_id, parent_id=excluded.parent_id, title=excluded.title,
            project=excluded.project, directory=excluded.directory, status=excluded.status,
            created_at=excluded.created_at, updated_at=excluded.updated_at, imported=excluded.imported
        """,
        (
            session.id,
            session.source_id,
            session.parent_id,
            session.title,
            session.project,
            session.directory,
            session.status,
            iso_ms(session.created_ms),
            iso_ms(session.updated_ms),
            session.imported,
        ),
    )

    duration_ms = None
    if session.created_ms is not None and session.completed_ms is not None:
        duration_ms = max(0, session.completed_ms - session.created_ms)

    tool_calls = 0
    tool_errors = 0
    covered: list[tuple[int, int]] = []

    # message-level tool_time accumulation
    msg_tool_time: dict[str, int] = {mid: 0 for mid in message_order}

    # Compute-only pass: parts.message_id has a FK on messages(id), so
    # messages must be inserted first. Durations/tool_time are needed to
    # insert messages, so we compute them here without writing yet.
    part_rows = []
    for key, p in parts.items():
        duration = None
        if p.started_ms is not None and p.ended_ms is not None:
            duration = max(0, p.ended_ms - p.started_ms)
            covered.append((p.started_ms, p.ended_ms))
        if p.type == "tool":
            tool_calls += 1
            if p.status == "error":
                tool_errors += 1
            if p.message_id and duration:
                msg_tool_time[p.message_id] = msg_tool_time.get(p.message_id, 0) + duration
        output_bytes = len(p.output_text.encode("utf-8")) if p.output_text else None
        output_tokens_est = estimate_tokens(p.output_text) if p.output_text else None
        part_rows.append((p, duration, output_bytes, output_tokens_est))

    session_tokens = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0}
    for mid in message_order:
        m = messages[mid]
        elapsed = None
        if m.started_ms is not None and m.completed_ms is not None:
            elapsed = max(0, m.completed_ms - m.started_ms)
            # The message's own request/response window counts as "covered"
            # even where no individual part has explicit timing (OpenCode's
            # step-start/step-finish carry no time field at all) - part
            # intervals are a subset of this and merge_intervals() dedupes.
            covered.append((m.started_ms, m.completed_ms))
        tool_time = msg_tool_time.get(mid, 0)
        model_time = max(0, elapsed - tool_time) if elapsed is not None else None
        for k in session_tokens:
            session_tokens[k] += m.tokens.get(k, 0)
        conn.execute(
            """
            INSERT INTO messages (id, session_id, seq, role, started_at, completed_at, elapsed_ms, tool_time_ms,
                                   model_time_ms, model, provider, agent, tokens_input, tokens_output,
                                   tokens_reasoning, tokens_cache_read, tokens_cache_write, finish_reason, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                m.id,
                session_id,
                m.seq,
                m.role,
                iso_ms(m.started_ms),
                iso_ms(m.completed_ms),
                elapsed,
                tool_time,
                model_time,
                m.model,
                m.provider,
                m.agent,
                m.tokens.get("input", 0),
                m.tokens.get("output", 0),
                m.tokens.get("reasoning", 0),
                m.tokens.get("cache_read", 0),
                m.tokens.get("cache_write", 0),
                m.finish_reason,
                m.error,
            ),
        )

    for p, duration, output_bytes, output_tokens_est in part_rows:
        conn.execute(
            """
            INSERT INTO parts (id, message_id, session_id, seq, type, started_at, ended_at, duration_ms,
                                tool_name, call_id, status, title, error, text, input_json, output_text,
                                output_bytes, output_tokens_est, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p.id,
                p.message_id,
                session_id,
                p.seq,
                p.type,
                iso_ms(p.started_ms),
                iso_ms(p.ended_ms),
                duration,
                p.tool_name,
                p.call_id,
                p.status,
                p.title,
                p.error,
                p.text,
                json.dumps(p.input, ensure_ascii=False) if p.input is not None else None,
                p.output_text,
                output_bytes,
                output_tokens_est,
                json.dumps(p.metadata, ensure_ascii=False) if p.metadata is not None else None,
            ),
        )

    for captured_at, todos in todo_snapshots:
        conn.execute(
            "INSERT INTO todo_snapshots (session_id, captured_at, items_json) VALUES (?, ?, ?)",
            (session_id, captured_at, json.dumps(todos, ensure_ascii=False)),
        )

    unaccounted_ms = None
    if duration_ms is not None:
        covered_total = covered_ms(covered, session.created_ms, session.completed_ms)
        unaccounted_ms = max(0, duration_ms - covered_total)

    conn.execute(
        """
        INSERT INTO sessions (id, source_id, parent_id, title, project, directory, status, created_at, updated_at,
                               completed_at, duration_ms, model, provider, agent, tokens_input, tokens_output,
                               tokens_reasoning, tokens_cache_read, tokens_cache_write, tool_calls, tool_errors,
                               compactions, error_count, unaccounted_ms, imported)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            source_id=excluded.source_id, parent_id=excluded.parent_id, title=excluded.title,
            project=excluded.project, directory=excluded.directory, status=excluded.status,
            created_at=excluded.created_at, updated_at=excluded.updated_at, completed_at=excluded.completed_at,
            duration_ms=excluded.duration_ms, model=excluded.model, provider=excluded.provider, agent=excluded.agent,
            tokens_input=excluded.tokens_input, tokens_output=excluded.tokens_output,
            tokens_reasoning=excluded.tokens_reasoning, tokens_cache_read=excluded.tokens_cache_read,
            tokens_cache_write=excluded.tokens_cache_write, tool_calls=excluded.tool_calls,
            tool_errors=excluded.tool_errors, compactions=excluded.compactions, error_count=excluded.error_count,
            unaccounted_ms=excluded.unaccounted_ms, imported=excluded.imported
        """,
        (
            session.id,
            session.source_id,
            session.parent_id,
            session.title,
            session.project,
            session.directory,
            session.status,
            iso_ms(session.created_ms),
            iso_ms(session.updated_ms),
            iso_ms(session.completed_ms),
            duration_ms,
            session.model,
            session.provider,
            session.agent,
            session_tokens["input"],
            session_tokens["output"],
            session_tokens["reasoning"],
            session_tokens["cache_read"],
            session_tokens["cache_write"],
            tool_calls,
            tool_errors,
            session.compactions,
            session.error_count,
            unaccounted_ms if unaccounted_ms is not None else 0,
            session.imported,
        ),
    )

    from .detectors import run_detectors

    run_detectors(conn, session_id)
