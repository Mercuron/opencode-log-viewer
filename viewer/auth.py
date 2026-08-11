from __future__ import annotations

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .config import Settings

COOKIE_NAME = "vsession"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def require_ingest_auth(request: Request, settings: Settings) -> None:
    if not settings.ingest_secret:
        raise HTTPException(status_code=401, detail="ingest secret not configured on server")
    header = request.headers.get("authorization", "")
    if header != f"Bearer {settings.ingest_secret}":
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_cookie_key, salt="opencode-log-viewer-ui")


def make_session_cookie(settings: Settings) -> str:
    return _serializer(settings).dumps({"ui": True})


def verify_session_cookie(settings: Settings, token: str | None) -> bool:
    if not token:
        return False
    try:
        _serializer(settings).loads(token, max_age=COOKIE_MAX_AGE)
        return True
    except BadSignature:
        return False


def require_ui_session(request: Request, settings: Settings) -> None:
    if not settings.ui_password:
        return  # UI auth disabled: no password configured (local/dev use).
    token = request.cookies.get(COOKIE_NAME)
    if not verify_session_cookie(settings, token):
        raise HTTPException(status_code=401, detail="not authenticated")
