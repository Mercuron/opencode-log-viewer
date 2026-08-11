from __future__ import annotations

from viewer.export import build_markdown
from viewer.ingest import write_batch

from .conftest import load_fixture_events

SESSION_ID = "ses_00fdbcb3affezdUs1su8KIvq3b"

EXPECTED_SECTIONS = [
    "## Сводка",
    "## Что видно сразу (детекции)",
    "## Шаги модели",
    "## Инструменты",
    "## Чем заполнялся контекст",
    "## История плана",
    "## Лента шагов",
]


def test_export_contains_all_sections(conn, settings):
    write_batch(conn, load_fixture_events(), settings)
    md = build_markdown(conn, SESSION_ID)
    assert md is not None
    for section in EXPECTED_SECTIONS:
        assert section in md, f"missing section: {section}"


def test_export_truncates_large_outputs_with_original_size_note(conn, settings):
    events = load_fixture_events()
    # Repeated *words* (not one 32+ char run) so the default REDACT_PATTERNS
    # secret-looking-token rule doesn't swallow the whole thing first.
    big_output = "row value " * 500
    assert len(big_output) == 5000
    for e in events:
        if e["event_type"] == "message.part.updated" and (e["payload"].get("part") or {}).get("type") == "tool":
            state = e["payload"]["part"].get("state") or {}
            if state.get("status") == "completed":
                state["output"] = big_output
    write_batch(conn, events, settings)

    md = build_markdown(conn, SESSION_ID, limit=100)
    assert big_output[:100] in md
    assert big_output not in md
    assert "исходный размер 5000 символов" in md


def test_export_missing_session_returns_none(conn):
    assert build_markdown(conn, "does-not-exist") is None
