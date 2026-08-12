from __future__ import annotations

import json
import sqlite3
from collections import defaultdict

from .redact import load_patterns, redact_value


def _truncate(text: str | None, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n\n… обрезано, исходный размер {len(text)} символов …"


def _fmt_ms(ms: int | None) -> str:
    if ms is None:
        return "?"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f} с"
    minutes, sec = divmod(seconds, 60)
    return f"{int(minutes)}:{sec:04.1f}"


def build_markdown(
    conn: sqlite3.Connection,
    session_id: str,
    limit: int = 1500,
    redact: bool = False,
    include_children: bool = False,
    _depth: int = 0,
) -> str | None:
    """Redaction is opt-in and applied only here, at export time - never at ingest (see
    viewer/ingest.py) - so it never touches what's stored or displayed elsewhere, only the
    copy/download the caller explicitly asked to have scrubbed. `include_children` pulls in
    each direct subagent session's own export as a nested section, one level deep only
    (`_depth` guards against a child that also requests children, keeping this to parent+kids
    rather than the whole tree)."""
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        return None
    session = dict(session)
    messages = [dict(r) for r in conn.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY seq", (session_id,))]
    parts = [dict(r) for r in conn.execute("SELECT * FROM parts WHERE session_id = ? ORDER BY seq", (session_id,))]
    detections = [dict(r) for r in conn.execute("SELECT * FROM detections WHERE session_id = ? ORDER BY level", (session_id,))]
    todos = [dict(r) for r in conn.execute("SELECT * FROM todo_snapshots WHERE session_id = ? ORDER BY id", (session_id,))]

    patterns = load_patterns(conn) if redact else []

    def scrub(text: str | None) -> str | None:
        if not redact or not text or not patterns:
            return text
        return redact_value(text, patterns)

    lines: list[str] = []
    lines.append(f"# Сессия {session_id}")
    lines.append("")
    lines.append(f"**{scrub(session.get('title')) or '(без названия)'}**")
    lines.append("")
    lines.append("## Сводка")
    lines.append("")
    lines.append(f"- Длительность: {_fmt_ms(session.get('duration_ms'))}")
    lines.append(f"- Не покрыто событиями: {_fmt_ms(session.get('unaccounted_ms'))}")
    lines.append(f"- Шагов (сообщений): {len(messages)}")
    lines.append(f"- Вызовов инструментов: {session.get('tool_calls')} (ошибок: {session.get('tool_errors')})")
    lines.append(f"- Компакций: {session.get('compactions')}")
    lines.append(f"- Ошибок сессии: {session.get('error_count')}")
    lines.append(
        f"- Токены: input={session.get('tokens_input')} output={session.get('tokens_output')} "
        f"reasoning={session.get('tokens_reasoning')} cache_read={session.get('tokens_cache_read')} "
        f"cache_write={session.get('tokens_cache_write')}"
    )
    lines.append(f"- Модель: {session.get('model')} · провайдер: {session.get('provider')} · агент: {session.get('agent')}")
    lines.append(f"- Проект: {session.get('project')} · директория: {session.get('directory')}")
    lines.append("")

    lines.append("## Что видно сразу (детекции)")
    lines.append("")
    if not detections:
        lines.append("_Детекторы ничего не нашли._")
    for d in detections:
        lines.append(f"- **[{d['level']}] {d['kind']}** — {d['message']}")
    lines.append("")

    lines.append("## Шаги модели")
    lines.append("")
    lines.append("| # | роль | всего | в инструментах | у модели | input | output | cache read | модель |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for m in messages:
        lines.append(
            f"| {m['seq']} | {m['role']} | {_fmt_ms(m['elapsed_ms'])} | {_fmt_ms(m['tool_time_ms'])} | "
            f"{_fmt_ms(m['model_time_ms'])} | {m['tokens_input']} | {m['tokens_output']} | "
            f"{m['tokens_cache_read']} | {m.get('model') or ''} |"
        )
    lines.append("")

    tool_stats: dict[str, dict] = defaultdict(lambda: {"calls": 0, "errors": 0, "total_ms": 0, "tokens_est": 0})
    for p in parts:
        if p["type"] != "tool":
            continue
        s = tool_stats[p["tool_name"] or "?"]
        s["calls"] += 1
        if p["status"] == "error":
            s["errors"] += 1
        s["total_ms"] += p["duration_ms"] or 0
        s["tokens_est"] += p["output_tokens_est"] or 0

    lines.append("## Инструменты")
    lines.append("")
    lines.append("| инструмент | вызовов | ошибок | всего | среднее | ≈токенов вывода |")
    lines.append("|---|---|---|---|---|---|")
    for name, s in sorted(tool_stats.items(), key=lambda kv: -kv[1]["total_ms"]):
        avg = s["total_ms"] / s["calls"] if s["calls"] else 0
        lines.append(f"| {name} | {s['calls']} | {s['errors']} | {_fmt_ms(s['total_ms'])} | {_fmt_ms(avg)} | ≈{s['tokens_est']} |")
    lines.append("")

    lines.append("## Чем заполнялся контекст (топ выводов по оценке токенов)")
    lines.append("")
    top_outputs = sorted((p for p in parts if p.get("output_tokens_est")), key=lambda p: -p["output_tokens_est"])[:10]
    if not top_outputs:
        lines.append("_Нет данных._")
    for p in top_outputs:
        lines.append(f"- шаг {p['seq']} · {p['tool_name'] or p['type']} · ≈{p['output_tokens_est']} токенов")
    lines.append("")

    lines.append("## История плана")
    lines.append("")
    if not todos:
        lines.append("_Todo-снимков не было._")
    for i, snap in enumerate(todos):
        items = json.loads(snap["items_json"])
        lines.append(f"**Снимок {i + 1}** ({snap.get('captured_at') or '?'})")
        for it in items:
            marker = {"completed": "[x]", "cancelled": "[~]", "in_progress": "[.]"}.get(it.get("status"), "[ ]")
            id_note = "" if it.get("id") else " _(без id)_"
            lines.append(f"- {marker} {it.get('content')}{id_note}")
        lines.append("")

    lines.append("## Лента шагов")
    lines.append("")
    for p in parts:
        header = f"### шаг {p['seq']} · {p['type']}" + (f" · {p['tool_name']}" if p["tool_name"] else "")
        lines.append(header)
        lines.append(f"_{p.get('status') or ''} · {_fmt_ms(p['duration_ms'])}_")
        if p.get("input_json"):
            lines.append("```json")
            lines.append(_truncate(scrub(p["input_json"]), limit))
            lines.append("```")
        if p.get("text"):
            lines.append(_truncate(scrub(p["text"]), limit))
        if p.get("output_text"):
            lines.append("```")
            lines.append(_truncate(scrub(p["output_text"]), limit))
            lines.append("```")
        if p.get("error"):
            lines.append(f"**Ошибка:** {scrub(p['error'])}")
        lines.append("")

    if include_children and _depth == 0:
        children = conn.execute(
            "SELECT id, title, agent FROM sessions WHERE parent_id = ? ORDER BY created_at", (session_id,)
        ).fetchall()
        for c in children:
            lines.append("---")
            lines.append("")
            lines.append(f"## Субагент: {c['agent'] or '?'} — {c['title'] or c['id']}")
            lines.append("")
            child_md = build_markdown(conn, c["id"], limit=limit, redact=redact, include_children=False, _depth=_depth + 1)
            if child_md:
                lines.append(child_md)
            else:
                lines.append("_(дочерняя сессия не найдена)_")
            lines.append("")

    return "\n".join(lines)
