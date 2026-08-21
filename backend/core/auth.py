"""Shared secret guarding the local HTTP/WebSocket API.

The backend listens on 127.0.0.1, but that is not a security boundary: any
web page the user visits can reach a localhost port from inside the browser.
Without a secret, a malicious page could POST to /features/... and wipe the
account's loot or friend list.

The desktop app generates the token and hands it to the backend through the
environment when it spawns the process, so the secret never touches disk. If
the backend is started standalone (development), it generates its own and
logs it, which fails closed: nothing can talk to it until the token is used.
"""
import hmac
import logging
import os
import secrets

logger = logging.getLogger(__name__)

TOKEN_ENV_VAR = "CAMARGO_AUTH_TOKEN"
TOKEN_HEADER = "x-camargo-token"


def _resolve_token():
    token = os.environ.get(TOKEN_ENV_VAR, "").strip()
    if token:
        return token

    token = secrets.token_urlsafe(32)
    logger.warning(
        "%s is not set; generated a session token for standalone use: %s",
        TOKEN_ENV_VAR,
        token,
    )
    return token


AUTH_TOKEN = _resolve_token()


def is_valid_token(candidate):
    if not candidate:
        return False
    return hmac.compare_digest(candidate, AUTH_TOKEN)
