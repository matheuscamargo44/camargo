"""Handshake rules for the local API.

The token stops an ordinary web page from driving the League client through
127.0.0.1, which is reachable from any browser the user has open.
"""
import pytest
from fastapi.testclient import TestClient

import api.server as server
from core.auth import AUTH_TOKEN, TOKEN_HEADER, WS_SUBPROTOCOL

WS_URL = "/ws/events"
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


@pytest.mark.parametrize("origin", ["null", "file://"])
def test_websocket_accepts_every_renderer_origin(client, origin):
    """Chromium sends `null` for fetch but `file://` for the WS handshake.

    Only accepting `null` here broke the event stream in v0.3.0: the renderer
    reconnected every 3 seconds and never got through.
    """
    with client.websocket_connect(
        WS_URL, subprotocols=[WS_SUBPROTOCOL, AUTH_TOKEN], headers={"Origin": origin}
    ) as ws:
        assert ws.accepted_subprotocol == WS_SUBPROTOCOL


def test_websocket_rejects_a_web_page_even_with_the_token(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            WS_URL,
            subprotocols=[WS_SUBPROTOCOL, AUTH_TOKEN],
            headers={"Origin": "https://evil.example"},
        ):
            pass


@pytest.mark.parametrize(
    "subprotocols",
    [None, [WS_SUBPROTOCOL], [WS_SUBPROTOCOL, "wrong-token"], ["other.v1", AUTH_TOKEN]],
)
def test_websocket_rejects_a_bad_handshake(client, subprotocols):
    from starlette.websockets import WebSocketDisconnect

    kwargs = {"subprotocols": subprotocols} if subprotocols else {}
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(WS_URL, headers={"Origin": "null"}, **kwargs):
            pass
