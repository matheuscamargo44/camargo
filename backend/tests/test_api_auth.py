"""Handshake rules for the local API.

The token stops an ordinary web page from driving the League client through
127.0.0.1, which is reachable from any browser the user has open.
"""
import pytest
from fastapi.testclient import TestClient

import api.server as server
from core.auth import AUTH_TOKEN, TOKEN_HEADER

AUTH = {TOKEN_HEADER: AUTH_TOKEN}


@pytest.fixture
def client():
    with TestClient(server.app) as test_client:
        yield test_client


def test_http_requires_the_token(client):
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={TOKEN_HEADER: "wrong"}).status_code == 401
    assert client.get("/health", headers=AUTH).status_code == 200


def test_actions_reject_an_unauthenticated_caller(client):
    # The shape a malicious page would use: no token, its own origin.
    response = client.post(
        "/features/mass_disenchant/actions/disenchant_all",
        headers={"Origin": "https://evil.example"},
        json={},
    )
    assert response.status_code == 401


def test_feature_events_reach_the_log(caplog):
    """The UI shows no notifications, so the log is the only consumer left."""
    import logging

    with caplog.at_level(logging.INFO, logger="api.server"):
        server._on_event("success", "Locked Garen")
        server._on_event("warn", "Could not dodge")

    assert "[success] Locked Garen" in caplog.text
    assert "[warn] Could not dodge" in caplog.text
    assert caplog.records[-1].levelno == logging.WARNING
