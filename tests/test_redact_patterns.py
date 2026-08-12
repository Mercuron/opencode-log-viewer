from __future__ import annotations

from .conftest import load_fixture_events


def _login(client):
    assert client.post("/api/v1/auth/login", json={"password": "adminpw"}).status_code == 200


def test_default_patterns_are_seeded(conn):
    rows = conn.execute("SELECT pattern, is_default FROM redact_patterns ORDER BY id").fetchall()
    assert len(rows) == 3
    assert all(r["is_default"] == 1 for r in rows)


def test_crud_via_api(client):
    _login(client)
    r = client.post("/api/v1/settings/redact-patterns", json={"pattern": r"SECRET-\d+"})
    assert r.status_code == 200
    new_id = r.json()["id"]
    assert r.json()["is_default"] == 0

    listed = client.get("/api/v1/settings/redact-patterns").json()
    assert any(p["id"] == new_id for p in listed)

    assert client.patch(f"/api/v1/settings/redact-patterns/{new_id}", json={"enabled": False}).status_code == 200
    assert client.delete(f"/api/v1/settings/redact-patterns/{new_id}").status_code == 200
    assert client.delete(f"/api/v1/settings/redact-patterns/{new_id}").status_code == 404


def test_invalid_regex_is_rejected(client):
    _login(client)
    r = client.post("/api/v1/settings/redact-patterns", json={"pattern": "(unclosed"})
    assert r.status_code == 400


def test_ingest_never_redacts_stored_payload(client, conn):
    """Redaction is opt-in and applied only at export time (see test_export.py) - ingest
    always stores the raw payload, even with patterns enabled, so nothing is ever silently
    lost at rest."""
    _login(client)
    client.post("/api/v1/settings/redact-patterns", json={"pattern": r"TOPSECRET-\d+"})

    events = load_fixture_events()
    marked = dict(events[0])
    marked["event_id"] = "evt_redact_test"
    marked["sequence"] = 77001
    marked["payload"] = {
        "info": {"note": "token is TOPSECRET-12345, keep it safe"},
        "part": {"tool": "mcp__codegraph_frontend__codegraph_explore"},
    }

    headers = {"Authorization": "Bearer s3cret"}
    client.post("/api/v1/events/batch", json={"events": [marked]}, headers=headers)

    row = conn.execute("SELECT payload_json FROM events WHERE event_id = ?", ("evt_redact_test",)).fetchone()
    assert "TOPSECRET-12345" in row["payload_json"]
    assert "mcp__codegraph_frontend__codegraph_explore" in row["payload_json"]
    assert "[REDACTED]" not in row["payload_json"]
