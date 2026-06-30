from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Optional

from starlette.requests import Request
from starlette.responses import Response


SESSION_COOKIE_NAME = "h21_session"
SESSION_MAX_AGE = 30 * 24 * 60 * 60  # 30 days


def _ensure_signing_secret(data_dir: Path) -> str:
    """Load or create a persistent signing secret in the data directory."""
    secret_path = data_dir / "signing_secret"
    if secret_path.exists():
        return secret_path.read_text().strip()
    secret = secrets.token_hex(32)
    secret_path.write_text(secret)
    secret_path.chmod(0o600)
    return secret


def _sign(payload: str, secret: str) -> str:
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _verify(token: str, secret: str) -> Optional[str]:
    """Verify a signed token. Returns the payload if valid, else None."""
    parts = token.rsplit(".", 1)
    if len(parts) != 2:
        return None
    payload, signature = parts
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return payload


def create_session_token(user_id: int, secret: str) -> str:
    payload = json.dumps({"user_id": user_id, "exp": int(time.time()) + SESSION_MAX_AGE})
    return _sign(payload, secret)


def validate_session_token(token: str, secret: str) -> Optional[int]:
    """Return user_id if the token is valid and not expired, else None."""
    payload = _verify(token, secret)
    if payload is None:
        return None
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data.get("user_id")


def get_session_user_id(request: Request, secret: str) -> Optional[int]:
    """Extract user_id from the session cookie, if valid."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is None:
        return None
    return validate_session_token(token, secret)


def set_session_cookie(response: Response, user_id: int, secret: str) -> None:
    token = create_session_token(user_id, secret)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
