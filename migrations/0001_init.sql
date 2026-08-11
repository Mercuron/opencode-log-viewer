-- Raw events are the source of truth; every other table here is a
-- rebuildable index (see `viewer reindex`).

CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    hostname TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    opencode_version TEXT,
    plugin_version TEXT
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id),
    parent_id TEXT,
    title TEXT,
    project TEXT,
    directory TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER,
    model TEXT,
    provider TEXT,
    agent TEXT,
    tokens_input INTEGER NOT NULL DEFAULT 0,
    tokens_output INTEGER NOT NULL DEFAULT 0,
    tokens_reasoning INTEGER NOT NULL DEFAULT 0,
    tokens_cache_read INTEGER NOT NULL DEFAULT 0,
    tokens_cache_write INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    tool_errors INTEGER NOT NULL DEFAULT 0,
    compactions INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    unaccounted_ms INTEGER NOT NULL DEFAULT 0,
    imported INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_sessions_source ON sessions(source_id, created_at DESC);
CREATE INDEX idx_sessions_parent ON sessions(parent_id);

CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    seq INTEGER NOT NULL,
    role TEXT,
    started_at TEXT,
    completed_at TEXT,
    elapsed_ms INTEGER,
    tool_time_ms INTEGER NOT NULL DEFAULT 0,
    model_time_ms INTEGER,
    model TEXT,
    provider TEXT,
    agent TEXT,
    tokens_input INTEGER NOT NULL DEFAULT 0,
    tokens_output INTEGER NOT NULL DEFAULT 0,
    tokens_reasoning INTEGER NOT NULL DEFAULT 0,
    tokens_cache_read INTEGER NOT NULL DEFAULT 0,
    tokens_cache_write INTEGER NOT NULL DEFAULT 0,
    finish_reason TEXT,
    error TEXT
);
CREATE INDEX idx_messages_session ON messages(session_id, seq);

CREATE TABLE parts (
    id TEXT PRIMARY KEY,
    message_id TEXT REFERENCES messages(id),
    session_id TEXT NOT NULL REFERENCES sessions(id),
    seq INTEGER NOT NULL,
    type TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    duration_ms INTEGER,
    tool_name TEXT,
    call_id TEXT,
    status TEXT,
    title TEXT,
    error TEXT,
    text TEXT,
    input_json TEXT,
    output_text TEXT,
    output_bytes INTEGER,
    output_tokens_est INTEGER,
    metadata_json TEXT
);
CREATE INDEX idx_parts_message ON parts(message_id, seq);
CREATE INDEX idx_parts_session ON parts(session_id, seq);
CREATE INDEX idx_parts_tool ON parts(session_id, tool_name);
CREATE INDEX idx_parts_call ON parts(call_id);

CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    source_id TEXT,
    session_id TEXT,
    sequence INTEGER,
    event_type TEXT NOT NULL,
    event_time TEXT,
    observed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    context_json TEXT,
    truncated INTEGER NOT NULL DEFAULT 0,
    original_size INTEGER,
    imported INTEGER NOT NULL DEFAULT 0,
    ingested_at TEXT NOT NULL
);
CREATE INDEX idx_events_session ON events(session_id, sequence);
CREATE INDEX idx_events_source ON events(source_id, observed_at);
CREATE INDEX idx_events_type ON events(event_type);

CREATE TABLE todo_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    captured_at TEXT,
    items_json TEXT NOT NULL
);
CREATE INDEX idx_todo_session ON todo_snapshots(session_id, id);

CREATE TABLE inference_spans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    message_id TEXT,
    request_started_at TEXT,
    request_ended_at TEXT,
    prompt_tokens INTEGER,
    prompt_eval_ms INTEGER,
    eval_tokens INTEGER,
    eval_ms INTEGER,
    cache_hit_tokens INTEGER,
    n_past INTEGER,
    source_log TEXT,
    match_confidence REAL
);
CREATE INDEX idx_inference_session ON inference_spans(session_id);

CREATE TABLE detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    kind TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    evidence_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_detections_session ON detections(session_id);

CREATE TABLE import_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    source_name TEXT,
    path TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    sessions_imported INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT
);
