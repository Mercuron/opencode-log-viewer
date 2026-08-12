-- Exact per-request context composition, when the plugin's experimental
-- chat-transform hooks are new enough to send it (see docs/EVENT-INVENTORY.md
-- in opencode-log-plugin). Sessions from older plugins/imports simply have
-- no rows here; the UI falls back to the part-based estimate in that case.
CREATE TABLE context_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    message_id TEXT,
    captured_at TEXT,
    system_chars INTEGER NOT NULL DEFAULT 0,
    total_chars INTEGER NOT NULL DEFAULT 0,
    breakdown_json TEXT NOT NULL
);
CREATE INDEX idx_context_snapshots_session ON context_snapshots(session_id);

-- Redaction rules, editable from Settings instead of only via the
-- REDACT_PATTERNS env var. Seeded once from the three defaults that used to
-- be hardcoded (viewer/config.py::DEFAULT_REDACT_PATTERNS); the env var is
-- now only a first-boot seed, not the live source of truth.
CREATE TABLE redact_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

INSERT INTO redact_patterns (pattern, enabled, is_default, created_at) VALUES
    ('(?i)password\s*=\s*\S+', 1, 1, datetime('now')),
    ('(?i)pwd\s*=\s*\S+', 1, 1, datetime('now')),
    ('[A-Za-z0-9_-]{32,}', 1, 1, datetime('now'));
