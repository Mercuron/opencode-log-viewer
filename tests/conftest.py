from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture_events() -> list[dict]:
    files = sorted(glob.glob(str(FIXTURES_DIR / "*" / "*.json")))
    return [json.loads(Path(f).read_text(encoding="utf-8")) for f in files]


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VIEWER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("INGEST_SECRET", "s3cret")
    monkeypatch.setenv("UI_PASSWORD", "adminpw")
    monkeypatch.setenv("SESSION_COOKIE_KEY", "testkey")
    monkeypatch.setenv("VIEWER_DISABLE_RETENTION", "1")
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    from viewer.config import get_settings

    return get_settings()


@pytest.fixture
def conn(settings):
    from viewer.db import open_db
    from viewer.migrations import apply_migrations

    c = open_db(settings)
    apply_migrations(c)
    yield c
    c.close()


@pytest.fixture
def app(settings):
    from viewer.app import create_app

    return create_app(settings)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
