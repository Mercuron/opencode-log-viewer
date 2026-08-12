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


def test_export_redact_false_by_default_leaves_raw_data(conn, settings, client):
    events = load_fixture_events()
    for e in events:
        if e["event_type"] == "message.part.updated" and (e["payload"].get("part") or {}).get("type") == "tool":
            state = e["payload"]["part"].get("state") or {}
            if state.get("status") == "completed":
                state["output"] = "token is TOPSECRET-12345, keep it safe"
    write_batch(conn, events, settings)

    assert client.post("/api/v1/auth/login", json={"password": "adminpw"}).status_code == 200
    client.post("/api/v1/settings/redact-patterns", json={"pattern": r"TOPSECRET-\d+"})

    md_clean = build_markdown(conn, SESSION_ID)
    assert "TOPSECRET-12345" in md_clean

    md_redacted = build_markdown(conn, SESSION_ID, redact=True)
    assert "TOPSECRET-12345" not in md_redacted
    assert "[REDACTED]" in md_redacted


def test_export_include_children_appends_subagent_section(conn, settings):
    write_batch(conn, load_fixture_events(), settings)

    md_without = build_markdown(conn, SESSION_ID, include_children=False)
    assert "sql-review subagent" not in md_without

    md_with = build_markdown(conn, SESSION_ID, include_children=True)
    assert "## Субагент:" in md_with
    assert "sql-review subagent" in md_with
