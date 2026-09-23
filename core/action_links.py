"""Short-lived, purpose-bound approval links for email recipients."""

import base64
import binascii
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from core.config import settings

LINK_LIFETIME_SECONDS = 24 * 60 * 60


def create_action_token(kind: str, object_id: str, action: str, *, now: int | None = None) -> str:
    payload = {"kind": kind, "id": object_id, "action": action.upper(),
               "exp": (int(time.time()) if now is None else now) + LINK_LIFETIME_SECONDS}
    body = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(settings.SECRET_KEY.encode(), body, hashlib.sha256).hexdigest()
    return f"{body.decode()}.{signature}"


def is_action_token_consumed(token: str | None) -> bool:
    """Check if token signature has already been consumed."""
    if not token or "." not in token:
        return True
    try:
        _, signature = token.split(".", 1)
        from database.db import get_db_connection
        conn = get_db_connection(read_only=True)
        try:
            tables = [t[0] for t in conn.execute("SHOW TABLES;").fetchall()]
            if "consumed_action_tokens" not in tables:
                return False
            row = conn.execute("SELECT 1 FROM consumed_action_tokens WHERE token_sig = ?", [signature]).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return False


def consume_action_token(token: str | None, kind: str, object_id: str, action: str) -> bool:
    """Mark a token as consumed once used in a POST action. Returns False if already consumed."""
    if not token or "." not in token:
        return False
    try:
        _, signature = token.split(".", 1)
        from database.db import get_db_connection
        conn = get_db_connection(read_only=False)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS consumed_action_tokens (
                    token_sig VARCHAR PRIMARY KEY,
                    kind VARCHAR NOT NULL,
                    object_id VARCHAR NOT NULL,
                    action VARCHAR NOT NULL,
                    consumed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            existing = conn.execute("SELECT 1 FROM consumed_action_tokens WHERE token_sig = ?", [signature]).fetchone()
            if existing:
                return False
            conn.execute(
                "INSERT INTO consumed_action_tokens (token_sig, kind, object_id, action) VALUES (?, ?, ?, ?)",
                [signature, kind, object_id, action.upper()]
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


def verify_action_token(token: str | None, kind: str, object_id: str, action: str, *, now: int | None = None) -> bool:
    if not token:
        return False
    if is_action_token_consumed(token):
        return False
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return (payload.get("kind") == kind and payload.get("id") == object_id
                and payload.get("action") == action.upper()
                and isinstance(payload.get("exp"), int)
                and payload["exp"] >= (int(time.time()) if now is None else now))
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error):
        return False


def build_action_url(base_url: str, kind: str, object_id: str, action: str) -> str:
    paths = {"pr": "/api/approval/quick-action", "leave": "/api/approval/leave-quick-action",
             "onboarding": "/api/approval/client-onboarding-action"}
    keys = {"pr": "pr_number", "leave": "leave_id", "onboarding": "onboarding_id"}
    query = urlencode({keys[kind]: object_id, "action": action.upper(),
                       "token": create_action_token(kind, object_id, action)})
    return f"{base_url.rstrip('/')}{paths[kind]}?{query}"
