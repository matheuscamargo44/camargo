"""The activity log is the only place a failure becomes visible to the user."""
import logging

import pytest
from fastapi.testclient import TestClient

import api.server as server
from core.activity_log import ActivityLog
from core.auth import AUTH_TOKEN, TOKEN_HEADER

AUTH = {TOKEN_HEADER: AUTH_TOKEN}


@pytest.fixture
def client():
    server.ACTIVITY_LOG.clear()
    with TestClient(server.app) as test_client:
        yield test_client


def make_record(message, level=logging.INFO, name="features.instalock", exc_info=None):
    return logging.LogRecord(name, level, __file__, 1, message, None, exc_info)


def test_captures_message_level_and_source():
    log = ActivityLog()
    log.emit(make_record("Locked Garen"))

    entry = log.entries()[0]
    assert entry["message"] == "Locked Garen"
    assert entry["level"] == "INFO"
    assert entry["source"] == "features.instalock"
    assert entry["detail"] is None


def test_keeps_the_traceback_of_an_exception():
    log = ActivityLog()
    try:
        raise ValueError("champion not found")
    except ValueError:
        import sys

        log.emit(make_record("lock failed", logging.ERROR, exc_info=sys.exc_info()))

    entry = log.entries()[0]
    assert "ValueError: champion not found" in entry["detail"]


def test_repeats_collapse_into_a_counter():
    """A loop failing every 2s must not push everything else out."""
    log = ActivityLog()
    for _ in range(50):
        log.emit(make_record("client unreachable", logging.WARNING))
    log.emit(make_record("Locked Garen"))

    entries = log.entries()
    assert len(entries) == 2
    assert entries[0]["count"] == 50
    assert entries[1]["count"] == 1


def test_drops_the_oldest_when_full():
    log = ActivityLog(capacity=3)
    for i in range(6):
        log.emit(make_record(f"event {i}"))

    assert [e["message"] for e in log.entries()] == ["event 3", "event 4", "event 5"]


def test_access_logs_are_excluded():
    log = ActivityLog()
    log.emit(make_record("GET /features", name="uvicorn.access"))
    assert log.entries() == []


def test_endpoints_require_the_token(client):
    assert client.get("/logs").status_code == 401
    assert client.post("/logs/client", json={"message": "x"}).status_code == 401
    assert client.delete("/logs").status_code == 401


def test_polling_returns_only_new_entries(client):
    logging.getLogger("features.autoban").warning("first")
    first = client.get("/logs", headers=AUTH).json()
    assert any(e["message"] == "first" for e in first["entries"])

    logging.getLogger("features.autoban").warning("second")
    second = client.get("/logs", headers=AUTH, params={"after": first["next"]}).json()

    messages = [e["message"] for e in second["entries"]]
    assert "second" in messages
    assert "first" not in messages


def test_renderer_errors_land_in_the_same_log(client):
    client.post(
        "/logs/client",
        headers=AUTH,
        json={
            "level": "error",
            "message": "TypeError: btn.getAttribute is not a function",
            "detail": "at buildToggleControl (feature-card.js:190)",
            "source": "toggle",
        },
    )

    entries = client.get("/logs", headers=AUTH).json()["entries"]
    entry = next(e for e in entries if "TypeError" in e["message"])
    assert entry["level"] == "ERROR"
    assert entry["source"] == "renderer.toggle"
    assert "feature-card.js:190" in entry["detail"]


def test_client_log_rejects_an_empty_message(client):
    assert client.post("/logs/client", headers=AUTH, json={"message": "   "}).status_code == 400


def test_clear_empties_the_log(client):
    logging.getLogger("features.dodge").error("boom")
    assert client.get("/logs", headers=AUTH).json()["entries"]

    client.delete("/logs", headers=AUTH)
    remaining = client.get("/logs", headers=AUTH).json()["entries"]
    # only the "cleared" note itself
    assert [e["message"] for e in remaining] == ["Activity log cleared"]
