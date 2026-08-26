"""Regression tests for the background-loop lifecycle.

Five features once shipped with a `_loop()` and a `_stop_event` that nothing
ever created, because the base class `start()` was a no-op: the toggles turned
green and the automation never ran. These tests fail if a feature declares a
loop that `start()` does not actually run.
"""
import copy
import threading
import time

from core.config import DEFAULT_CONFIG
from features.base import ThreadedFeature
from features.registry import FEATURE_CLASSES, FeatureRegistry


class StubLCUClient:
    """Reports the client as absent, so every loop takes its idle branch."""

    def is_league_connected(self):
        return False

    def lcu_request(self, method, endpoint, body=""):
        raise AssertionError("loops must not call the client while disconnected")

    riot_request = lcu_request


def make_registry(monkeypatch):
    monkeypatch.setattr("features.registry.LCUClient", StubLCUClient)
    monkeypatch.setattr("features.registry.load_config", lambda: copy.deepcopy(DEFAULT_CONFIG))
    return FeatureRegistry()


def loop_feature_keys():
    return sorted(cls.key for cls in FEATURE_CLASSES if issubclass(cls, ThreadedFeature))


def _is_loop_thread(thread, expected_keys):
    """A "camargo-" prefix alone isn't a unique-enough signal any more:
    `FeatureRegistry._status_pool` names its own worker threads
    "camargo-status_N", which - now that the API integration tests share
    one long-lived registry/client for the whole session instead of
    tearing one down per test - can genuinely be alive at the same time as
    a *different*, test-local registry's loop threads this file spins up.
    Matched against the exact expected key set instead of the bare prefix.
    """
    return thread.name.startswith("camargo-") and thread.name.removeprefix("camargo-") in expected_keys


def test_every_feature_with_a_loop_uses_the_shared_lifecycle():
    for cls in FEATURE_CLASSES:
        has_own_loop = "_loop" in vars(cls)
        if has_own_loop:
            assert issubclass(cls, ThreadedFeature), f"{cls.key} defines _loop but is not threaded"
        if issubclass(cls, ThreadedFeature):
            assert has_own_loop, f"{cls.key} is threaded but never implements _loop"
            assert cls.start is ThreadedFeature.start, f"{cls.key} overrides start()"


def test_start_all_runs_one_thread_per_loop_feature(monkeypatch):
    registry = make_registry(monkeypatch)
    expected = loop_feature_keys()
    assert expected, "expected at least one background feature"

    registry.start_all()
    try:
        time.sleep(0.2)
        running = sorted(
            t.name.removeprefix("camargo-")
            for t in threading.enumerate()
            if _is_loop_thread(t, expected) and t.is_alive()
        )
        assert running == expected
    finally:
        registry.stop_all()


def test_stop_all_joins_every_thread(monkeypatch):
    registry = make_registry(monkeypatch)
    expected = loop_feature_keys()
    registry.start_all()
    time.sleep(0.2)

    started = time.perf_counter()
    registry.stop_all()
    elapsed = time.perf_counter() - started

    leftover = [t.name for t in threading.enumerate() if _is_loop_thread(t, expected)]
    assert leftover == []
    # Loops sleep in 0.3-2s steps; waiting them out would take seconds.
    assert elapsed < 1.0, f"stop_all took {elapsed:.2f}s, loops are not waking on the stop event"


def test_start_is_idempotent(monkeypatch):
    registry = make_registry(monkeypatch)
    expected = loop_feature_keys()
    registry.start_all()
    try:
        registry.start_all()
        time.sleep(0.2)
        names = [t.name for t in threading.enumerate() if _is_loop_thread(t, expected)]
        assert len(names) == len(set(names)) == len(expected)
    finally:
        registry.stop_all()


def test_chat_toggle_reads_the_real_state(monkeypatch):
    """The switch used to report the last toggle, not the client's state."""
    import copy

    from core.config import DEFAULT_CONFIG
    from features.social import ChatToggle

    class Response:
        status_code = 200

        def json(self):
            return {"state": "disconnected"}

    class Client(StubLCUClient):
        def is_league_connected(self):
            return True

        def riot_request(self, method, endpoint, body=""):
            return Response()

    feature = ChatToggle(Client(), copy.deepcopy(DEFAULT_CONFIG))

    # Fresh instance: nothing has been toggled yet.
    assert feature.disconnected is False
    assert feature.get_status()["disconnected"] is True


def test_chat_toggle_stays_quiet_while_the_client_is_closed(caplog):
    """A closed client is a normal state; it must not fill the log."""
    import copy
    import logging

    from core.config import DEFAULT_CONFIG
    from features.social import ChatToggle

    feature = ChatToggle(StubLCUClient(), copy.deepcopy(DEFAULT_CONFIG))

    with caplog.at_level(logging.DEBUG, logger="features.social"):
        for _ in range(5):
            feature._state_read_at = 0.0
            feature.get_status()

    assert caplog.records == []
