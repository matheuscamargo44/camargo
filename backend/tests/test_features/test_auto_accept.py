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
        assert False, "expected RuntimeError"
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
