from __future__ import annotations

from datetime import UTC, datetime, timedelta

from viewer.ingest import write_batch
from viewer.retention import apply_retention

from .conftest import load_fixture_events


def test_retention_deletes_whole_old_sessions_without_orphans(conn, settings):
    events = load_fixture_events()
    write_batch(conn, events, settings)

    # Fixture timestamps are a fixed synthetic epoch, not "now" - pin both
    # sessions explicitly so the test doesn't drift with wall-clock time.
    old_iso = (datetime.now(UTC) - timedelta(days=200)).isoformat()
    recent_iso = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    conn.execute("UPDATE sessions SET created_at = ? WHERE id = 'ses_00fdbcb3affezdUs1su8KIvq3b'", (old_iso,))
    conn.execute("UPDATE sessions SET created_at = ? WHERE id = 'ses_00fdbcb3affezdUs1su8KIvq3c'", (recent_iso,))

    settings.retention_days = 90
    settings.retention_max_gb = 10_000  # disable size-based path for this test
    deleted = apply_retention(conn, settings)

    assert "ses_00fdbcb3affezdUs1su8KIvq3b" in deleted

    for table, column in [
        ("events", "session_id"), ("messages", "session_id"), ("parts", "session_id"),
        ("todo_snapshots", "session_id"), ("detections", "session_id"), ("sessions", "id"),
    ]:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {column} = ?", ("ses_00fdbcb3affezdUs1su8KIvq3b",)).fetchone()
        assert row["n"] == 0, f"orphaned rows left in {table}"

    remaining = conn.execute("SELECT id FROM sessions").fetchall()
    assert any(r["id"] == "ses_00fdbcb3affezdUs1su8KIvq3c" for r in remaining)


def test_retention_noop_when_nothing_exceeds_thresholds(conn, settings):
    write_batch(conn, load_fixture_events(), settings)
    settings.retention_days = 36_500
    settings.retention_max_gb = 10_000
    deleted = apply_retention(conn, settings)
    assert deleted == []
