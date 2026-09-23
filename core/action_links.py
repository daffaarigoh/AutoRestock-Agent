"""Short-lived, purpose-bound approval links for email recipients."""

import base64
import binascii
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from core.config import settings

LINK_LIFETIME_SECONDS = 7 * 24 * 60 * 60


def create_action_token(kind: str, object_id: str, action: str, *, now: int | None = None) -> str:
    payload = {"kind": kind, "id": object_id, "action": action.upper(),
               "exp": (int(time.time()) if now is None else now) + LINK_LIFETIME_SECONDS}
    body = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(settings.SECRET_KEY.encode(), body, hashlib.sha256).hexdigest()
    return f"{body.decode()}.{signature}"


def verify_action_token(token: str | None, kind: str, object_id: str, action: str, *, now: int | None = None) -> bool:
    if not token:
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
