import requests

import core.lcu_client
from core.lcu_client import LCUClient, _headers, _service_url, _split_arg


def test_split_arg_extracts_value():
    assert _split_arg("--app-port=1234", "--app-port=") == "1234"


def test_split_arg_returns_none_when_prefix_missing():
    assert _split_arg("--other=1234", "--app-port=") is None


def test_service_url_none_without_port():
    assert _service_url(None) is None


def test_service_url_builds_local_https_url():
    assert _service_url("1234") == "https://127.0.0.1:1234"


def test_headers_empty_without_token():
    assert _headers(None) == {}


def test_headers_include_basic_auth():
    headers = _headers("secret")
    assert headers["Authorization"].startswith("Basic ")
    assert headers["Content-Type"] == "application/json"


class ScanCounter:
    """Stands in for the psutil process walk, counting how often it runs."""

    def __init__(self, port="1234", token="secret"):
        self.calls = 0
        self.port = port
        self.token = token

    def __call__(self):
        self.calls += 1
        return self.port, self.token


def make_client(monkeypatch, league_scan, riot_scan=None):
    monkeypatch.setattr(core.lcu_client, "find_league_client_credentials", league_scan)
    monkeypatch.setattr(
        core.lcu_client, "find_riot_client_credentials", riot_scan or ScanCounter("4321", "riot")
    )
    return LCUClient()


def test_connection_checks_reuse_the_cached_scan(monkeypatch):
    scan = ScanCounter()
    client = make_client(monkeypatch, scan)
    assert scan.calls == 1  # the one from __init__

    for _ in range(50):
        assert client.is_league_connected() is True

    assert scan.calls == 1, "connection checks must not rescan every process"


def test_cache_expires_after_the_ttl(monkeypatch):
    scan = ScanCounter()
    client = make_client(monkeypatch, scan)

    now = [1000.0]
    monkeypatch.setattr(core.lcu_client.time, "monotonic", lambda: now[0])

    client._league_scanned_at = now[0]
    client.is_league_connected()
    assert scan.calls == 1

    now[0] += core.lcu_client.CREDENTIAL_TTL_SECONDS + 0.1
    client.is_league_connected()
    assert scan.calls == 2, "a stale cache must trigger a rescan"


def test_failed_request_rescans_immediately(monkeypatch):
    scan = ScanCounter()
    client = make_client(monkeypatch, scan)
    calls_before = scan.calls

    # A client restart moves the port; the first attempt fails, the retry must
    # pick up new credentials instead of waiting out the TTL.
    attempts = []

    def fake_request(method, url, **kwargs):
        attempts.append(url)
        if len(attempts) == 1:
            raise requests.exceptions.ConnectionError("client restarted")
        return "ok"

    monkeypatch.setattr(core.lcu_client.requests, "request", fake_request)
    scan.port = "9999"

    assert client.lcu_request("GET", "/x") == "ok"
    assert scan.calls > calls_before, "a transport failure must force a rescan"
    assert attempts[-1] == "https://127.0.0.1:9999/x"
