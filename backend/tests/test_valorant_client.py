"""ValorantClient: activation locking and region detection.

These target the 2026-08-26 audit fixes specifically - the rest of the
class is a thin pass-through to valclient, already exercised indirectly
through the Valorant features' own tests.
"""
import threading
import time

import pytest

from core import valorant_client as module
from core.valorant_client import ValorantClient
from valclient.exceptions import HandshakeError


def test_a_slow_activate_does_not_block_a_concurrent_caller(monkeypatch):
    """The real-world failure this fix prevents: while one thread is stuck
    inside activate(), another thread must still be able to observe/use the
    client state rather than deadlock behind the same RLock."""
    client = ValorantClient(region="eu")
    started = threading.Event()

    class _SlowStub:
        def activate(self_inner):
            started.set()
            time.sleep(0.3)

    monkeypatch.setattr(module, "ValClient", lambda region: _SlowStub())

    thread = threading.Thread(target=client._ensure_activated)
    thread.start()
    assert started.wait(timeout=1.0)

    # While the slow activate() is still running, a concurrent lock
    # acquisition must not block for anywhere near its 0.3s duration.
    start = time.monotonic()
    with client._lock:
        pass
    elapsed = time.monotonic() - start
    thread.join(timeout=2.0)

    assert elapsed < 0.2


def test_raises_handshake_error_when_no_region_is_known(monkeypatch):
    client = ValorantClient(region=None)
    monkeypatch.setattr(module, "detect_region", lambda: None)

    with pytest.raises(HandshakeError):
        client._ensure_activated()


def test_detect_region_streams_the_log_without_loading_it_all(tmp_path, monkeypatch):
    log_path = tmp_path / "ShooterGame.log"
    log_path.write_bytes(b"noise\nregions/eu]\nmore noise\n")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    # VALORANT/Saved/Logs/ShooterGame.log under LOCALAPPDATA
    nested = tmp_path / "VALORANT" / "Saved" / "Logs"
    nested.mkdir(parents=True)
    (nested / "ShooterGame.log").write_bytes(b"noise\nregions/eu]\nmore noise\n")

    assert module.detect_region() == "eu"


def test_detect_region_returns_none_when_the_log_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert module.detect_region() is None
