"""Shared-password access with per-reviewer attribution.

One crew password (APP_ACCESS_PASSWORD) gates every action that changes state;
each reviewer logs in with their own name, which is embedded in the session
token and stamped onto decisions and the audit trail. Reading the dashboard
stays open — a shared demo link should show, not act.

Tokens are self-contained HMAC-signed blobs (name + expiry), so there is no
session table and a restart invalidates nothing. Setting no password disables
the gate (local dev, tests) — the deployment sets it.
"""

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

TOKEN_TTL_S = 12 * 3600


def _password() -> str:
    return os.getenv("APP_ACCESS_PASSWORD", "")


def auth_enabled() -> bool:
    return bool(_password())


def _key() -> bytes:
    # Derived from the password: rotating the password revokes every token.
    return hashlib.sha256(("pm-triage-token:" + _password()).encode()).digest()


def issue_token(reviewer: str) -> str:
    payload = json.dumps({"reviewer": reviewer, "exp": int(time.time()) + TOKEN_TTL_S})
    body = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{sig}"


def verify_token(token: str) -> str | None:
    """Returns the reviewer name, or None if invalid/expired."""
    try:
        body, sig = token.rsplit(".", 1)
        expect = hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if payload["exp"] < time.time():
            return None
        return payload["reviewer"]
    except Exception:
        return None


_bearer = HTTPBearer(auto_error=False)


def current_reviewer(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """FastAPI dependency for state-changing routes. With the gate disabled it
    yields "" and route handlers fall back to body-supplied names."""
    if not auth_enabled():
        return ""
    if creds is None:
        raise HTTPException(401, "login required (Bearer token)")
    reviewer = verify_token(creds.credentials)
    if not reviewer:
        raise HTTPException(401, "invalid or expired session — log in again")
    return reviewer
