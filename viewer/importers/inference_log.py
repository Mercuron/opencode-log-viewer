from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

_PROMPT_RE = re.compile(r"prompt eval time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s*tokens")
_EVAL_RE = re.compile(r"(?<!prompt )eval time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s*tokens")
_SLOT_RE = re.compile(r"slot\s+\w+:\s*id\s*(\d+)")
_N_PAST_RE = re.compile(r"n_past\s*=\s*(\d+)")
_TIMESTAMP_RE = re.compile(r"^\[?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)")


@dataclass
class InferenceSpanRaw:
    slot_id: int | None
    n_past: int | None
    prompt_tokens: int | None
    prompt_eval_ms: float | None
    eval_tokens: int | None
    eval_ms: float | None
    log_timestamp: str | None
    source_log: str


def parse_llama_server_log(text: str, source_log: str = "llama-server") -> list[InferenceSpanRaw]:
    spans: list[InferenceSpanRaw] = []
    slot_id: int | None = None
    n_past: int | None = None
    prompt_tokens: int | None = None
    prompt_eval_ms: float | None = None
    eval_tokens: int | None = None
    eval_ms: float | None = None
    last_timestamp: str | None = None

    def reset():
        nonlocal slot_id, n_past, prompt_tokens, prompt_eval_ms, eval_tokens, eval_ms
        slot_id = n_past = prompt_tokens = eval_tokens = None
        prompt_eval_ms = eval_ms = None

    for line in text.splitlines():
        ts = _TIMESTAMP_RE.match(line)
        if ts:
            last_timestamp = ts.group(1)

        slot_m = _SLOT_RE.search(line)
        if slot_m:
            slot_id = int(slot_m.group(1))

        n_past_m = _N_PAST_RE.search(line)
        if n_past_m:
            n_past = int(n_past_m.group(1))

        prompt_m = _PROMPT_RE.search(line)
        if prompt_m:
            prompt_eval_ms = float(prompt_m.group(1))
            prompt_tokens = int(prompt_m.group(2))
            continue

        eval_m = _EVAL_RE.search(line)
        if eval_m:
            eval_ms = float(eval_m.group(1))
            eval_tokens = int(eval_m.group(2))

        if "total time" in line and (prompt_tokens is not None or eval_tokens is not None):
            spans.append(
                InferenceSpanRaw(
                    slot_id=slot_id, n_past=n_past, prompt_tokens=prompt_tokens, prompt_eval_ms=prompt_eval_ms,
                    eval_tokens=eval_tokens, eval_ms=eval_ms, log_timestamp=last_timestamp, source_log=source_log,
                )
            )
            reset()

    if prompt_tokens is not None or eval_tokens is not None:
        spans.append(
            InferenceSpanRaw(
                slot_id=slot_id, n_past=n_past, prompt_tokens=prompt_tokens, prompt_eval_ms=prompt_eval_ms,
                eval_tokens=eval_tokens, eval_ms=eval_ms, log_timestamp=last_timestamp, source_log=source_log,
            )
        )
    return spans


def correlate_and_store(conn: sqlite3.Connection, session_id: str, spans: list[InferenceSpanRaw]) -> int:
    """Matches spans to assistant messages by chronological position.
    Without reliable wall-clock timestamps on both sides this is a
    best-effort match - confidence is marked low and the UI must say so,
    never invent precision (5.7)."""
    messages = conn.execute(
        "SELECT id, started_at, completed_at FROM messages WHERE session_id = ? AND role = 'assistant' ORDER BY seq",
        (session_id,),
    ).fetchall()
    if not messages or not spans:
        return 0

    now = datetime.now(UTC).isoformat()
    stored = 0
    for message, span in zip(messages, spans):
        confidence = 0.7 if span.log_timestamp else 0.3
        conn.execute(
            """
            INSERT INTO inference_spans (session_id, message_id, request_started_at, request_ended_at,
                                          prompt_tokens, prompt_eval_ms, eval_tokens, eval_ms, cache_hit_tokens,
                                          n_past, source_log, match_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, message["id"], span.log_timestamp, span.log_timestamp,
                span.prompt_tokens, int(span.prompt_eval_ms) if span.prompt_eval_ms else None,
                span.eval_tokens, int(span.eval_ms) if span.eval_ms else None, None,
                span.n_past, span.source_log, confidence,
            ),
        )
        stored += 1
    return stored
