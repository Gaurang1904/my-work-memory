import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings


SESSION_TTL_SECONDS = 60 * 60 * 12
PBKDF2_PREFIX = "pbkdf2_sha256"


def is_auth_configured(settings: Settings) -> bool:
    return bool(settings.session_secret and (settings.admin_password_hash or settings.admin_password))


def hash_password(password: str, iterations: int = 390000) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"{PBKDF2_PREFIX}${iterations}${salt}${base64.urlsafe_b64encode(digest).decode('ascii')}"


def verify_password(password: str, settings: Settings) -> bool:
    if settings.admin_password_hash:
        try:
            algorithm, iterations, salt, expected = settings.admin_password_hash.split("$", 3)
        except ValueError:
            return False
        if algorithm != PBKDF2_PREFIX:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
        actual = base64.urlsafe_b64encode(digest).decode("ascii")
        return hmac.compare_digest(actual, expected)

    return bool(settings.admin_password) and hmac.compare_digest(password, settings.admin_password)


def create_session_token(username: str, settings: Settings) -> str:
    payload = {"u": username, "exp": int(time.time()) + SESSION_TTL_SECONDS}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    signature = hmac.new(
        settings.session_secret.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{encoded_payload}.{encoded_signature}"


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def read_session_token(token: str, settings: Settings) -> dict[str, Any] | None:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
    except ValueError:
        return None

    expected_signature = hmac.new(
        settings.session_secret.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    actual_signature = _decode_base64url(encoded_signature)
    if not hmac.compare_digest(actual_signature, expected_signature):
        return None

    try:
        payload = json.loads(_decode_base64url(encoded_payload).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if payload.get("exp", 0) < int(time.time()):
        return None

    return payload


def get_admin_session(request: Request, settings: Settings | None = None) -> dict[str, Any] | None:
    settings = settings or get_settings()
    if not is_auth_configured(settings):
        return None
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    return read_session_token(token, settings)


def require_admin_api(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    if not is_auth_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin auth is not configured. Set ADMIN_PASSWORD or ADMIN_PASSWORD_HASH and SESSION_SECRET.",
        )

    session = get_admin_session(request, settings)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required.")
    return session
