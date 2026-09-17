import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Cookie, HTTPException

from .config import get_settings

COOKIE_NAME = "net2net_session"
SESSION_SECONDS = 12 * 60 * 60


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_text, digest_text = encoded.split("$", 2)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hash_password(password, base64.urlsafe_b64decode(salt_text)).split("$", 2)[2]
        return hmac.compare_digest(candidate, digest_text)
    except (ValueError, TypeError):
        return False


def create_token(subject: str, role: str, display_name: str) -> str:
    payload = {"sub": subject, "role": role, "name": display_name, "exp": int(time.time()) + SESSION_SECONDS}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(get_settings().app_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def read_token(token: str) -> dict:
    try:
        body, signature = token.rsplit(".", 1)
        expected = hmac.new(get_settings().app_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if payload["exp"] < time.time():
            raise ValueError
        return payload
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Session expired or invalid") from exc


def current_identity(net2net_session: str | None = Cookie(default=None)) -> dict:
    if not net2net_session:
        raise HTTPException(401, "Login required")
    return read_token(net2net_session)
