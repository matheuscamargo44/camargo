import pytest
from core.config import DEFAULT_CONFIG
from features.auto_accept import AutoAccept


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


class FakeLCUClient:
    def __init__(self):
        self.calls = []
        self.next_response = FakeResponse()

    def lcu_request(self, method, endpoint, body=""):
        self.calls.append((method, endpoint, body))
        return self.next_response

    def is_league_connected(self):
        return True


def make_feature():
    import copy

    config = copy.deepcopy(DEFAULT_CONFIG)
    lcu = FakeLCUClient()
    events = []
    feature = AutoAccept(lcu, config, on_event=lambda level, message: events.append((level, message)))
    return feature, lcu, events


def test_toggle_flips_state_and_persists_config():
    feature, _, events = make_feature()

    assert feature.enabled is False
    feature.toggle()

    assert feature.enabled is True
    assert feature.config["auto_accept"]["enabled"] is True
    assert events[-1] == ("info", "Auto Accept enabled")


def test_accept_match_calls_lcu_and_emits_success():
    feature, lcu, events = make_feature()

    feature.accept_match()

    assert lcu.calls == [("POST", "/lol-matchmaking/v1/ready-check/accept", "")]
    assert events[-1] == ("success", "Match accepted")


def test_accept_match_raises_on_error_status():
    feature, lcu, _ = make_feature()
    lcu.next_response = FakeResponse(status_code=500)

    try:
        feature.accept_match()
        pytest.fail("expected RuntimeError")
    except RuntimeError:
        pass


def test_repeated_accept_failures_back_off_and_warn_once(monkeypatch):
    """A ready check that keeps failing to accept (already invalidated
    server-side, or a desynced client) must not be retried at full 0.5s
    cadence forever - that just floods the log without ever succeeding.
    """
    import time
    import features.auto_accept as auto_accept_module

    monkeypatch.setattr(auto_accept_module, "ACCEPT_FAILURE_BACKOFF_SECONDS", 0.05)
    monkeypatch.setattr(auto_accept_module, "ACCEPT_FAILURE_WARN_THRESHOLD", 3)

    feature, lcu, events = make_feature()
    feature.enabled = True

    def route(method, endpoint, body=""):
        if endpoint == "/lol-lobby/v2/lobby/matchmaking/search-state":
            return FakeResponse(status_code=200, json_data={"searchState": "Found"})
        return FakeResponse(status_code=500)

    lcu.lcu_request = route

    feature.start()
    try:
        time.sleep(0.3)
    finally:
        feature.stop()

    warn_events = [e for e in events if e[0] == "warn"]
    assert len(warn_events) == 1
    assert feature._consecutive_accept_failures >= 3


def test_a_ready_check_is_accepted_exactly_once(monkeypatch):
    """`searchState` describes the whole ~12s ready-check window, not a
    pending action - it stays "Found" after this feature already accepted.
    The 0.5s tick therefore used to re-POST the same accept for the rest of
    the window: a real session's log showed 32 POSTs and 23 "Match accepted"
    events across 2 ready checks, the tail of them ERROR tracebacks once the
    check resolved and there was nothing left to accept.
    """
    import time

    feature, lcu, events = make_feature()
    feature.enabled = True
    accepts = []

    def route(method, endpoint, body=""):
        if endpoint == "/lol-lobby/v2/lobby/matchmaking/search-state":
            return FakeResponse(status_code=200, json_data={"searchState": "Found"})
        accepts.append(endpoint)
        return FakeResponse(status_code=204)

    lcu.lcu_request = route

    feature.start()
    try:
        time.sleep(1.6)  # several 0.5s ticks, all inside one "Found" window
    finally:
        feature.stop()

    assert accepts == ["/lol-matchmaking/v1/ready-check/accept"]
    assert [e for e in events if e[0] == "success"] == [("success", "Match accepted")]


def test_the_next_ready_check_is_accepted_again(monkeypatch):
    """The latch must release when the window ends, or the feature would
    accept exactly one match per app launch."""
    import time

    feature, lcu, events = make_feature()
    feature.enabled = True
    accepts = []
    state = {"searching": False}

    def route(method, endpoint, body=""):
        if endpoint == "/lol-lobby/v2/lobby/matchmaking/search-state":
            found = "Searching" if state["searching"] else "Found"
            return FakeResponse(status_code=200, json_data={"searchState": found})
        accepts.append(endpoint)
        return FakeResponse(status_code=204)

    lcu.lcu_request = route

    feature.start()
    try:
        time.sleep(0.9)          # first check accepted, then latched
        state["searching"] = True
        time.sleep(0.9)          # window closes - latch releases
        state["searching"] = False
        time.sleep(0.9)          # a genuinely new check
    finally:
        feature.stop()

    assert len(accepts) == 2


def test_losing_the_client_mid_check_releases_the_latch():
    """Otherwise a client restart between the accept and the window closing
    would leave the latch stuck on for the next queue."""
    feature, _, _ = make_feature()
    feature.enabled = True
    feature._accepted_current_ready_check = True
    feature.lcu.is_league_connected = lambda: False

    # The disconnected branch ignores _sleep()'s return value, so stopping
    # the loop after one pass means actually setting the stop event.
    def stop_after_one_pass(_seconds):
        feature._stop_event.set()
        return True

    feature._sleep = stop_after_one_pass
    feature._loop()

    assert feature._accepted_current_ready_check is False
