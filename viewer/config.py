from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_patterns(name: str) -> list[re.Pattern]:
    raw = os.environ.get(name, "")
    patterns = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            patterns.append(re.compile(chunk))
        except re.error:
            continue
    return patterns


DEFAULT_REDACT_PATTERNS = [
    r"(?i)password\s*=\s*\S+",
    r"(?i)pwd\s*=\s*\S+",
    r"[A-Za-z0-9_-]{32,}",
]


@dataclass
class Settings:
    data_dir: str = field(default_factory=lambda: os.environ.get("VIEWER_DATA_DIR", "/data"))
    db_path: str = field(default="")
    ingest_secret: str | None = field(default_factory=lambda: os.environ.get("INGEST_SECRET"))
    ui_password: str | None = field(default_factory=lambda: os.environ.get("UI_PASSWORD"))
    session_cookie_key: str = field(
        default_factory=lambda: os.environ.get("SESSION_COOKIE_KEY", "dev-insecure-cookie-key-change-me")
    )
    retention_days: int = field(default_factory=lambda: _env_int("RETENTION_DAYS", 90))
    retention_max_gb: int = field(default_factory=lambda: _env_int("RETENTION_MAX_GB", 20))
    max_event_payload_bytes: int = field(default_factory=lambda: _env_int("MAX_EVENT_PAYLOAD_BYTES", 2 * 1024 * 1024))
    export_default_limit: int = field(default_factory=lambda: _env_int("EXPORT_DEFAULT_LIMIT", 1500))
    redact_patterns: list[re.Pattern] = field(
        default_factory=lambda: _env_patterns("REDACT_PATTERNS") or [re.compile(p) for p in DEFAULT_REDACT_PATTERNS]
    )

    def __post_init__(self) -> None:
        if not self.db_path:
            self.db_path = os.environ.get("VIEWER_DB_PATH", os.path.join(self.data_dir, "viewer.db"))


def get_settings() -> Settings:
    return Settings()
