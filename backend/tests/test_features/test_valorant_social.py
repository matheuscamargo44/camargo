import pytest
from features.valorant_social import ValorantChatToggle


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}

    def json(self):
        return self._json_data


class FakeValorantClient:
    def __init__(self, connected=True):
        self.connected = connected
        self.calls = []
        self.session_state = "connected"
        self.next_response = None

    def is_connected(self):
        return self.connected

    def local_request(self, method, endpoint, body=None):
        self.calls.append((method, endpoint, body))
        if self.next_response is not None:
            return self.next_response
        if endpoint == "/chat/v1/session":
            return FakeResponse(json_data={"state": self.session_state})
        return FakeResponse(status_code=200)


def make_feature(connected=True):
    valorant = FakeValorantClient(connected=connected)
    events = []
    feature = ValorantChatToggle(valorant, {}, on_event=lambda level, message: events.append((level, message)))
    return feature, valorant, events


def test_get_status_reads_the_real_session_state():
    feature, valorant, _ = make_feature()
    valorant.session_state = "disconnected"

    assert feature.get_status() == {"key": "valorant_chat_toggle", "disconnected": True}


def test_get_status_caches_within_the_ttl():
    feature, valorant, _ = make_feature()

    feature.get_status()
    calls_after_first = len(valorant.calls)
    feature.get_status()

    assert len(valorant.calls) == calls_after_first  # no second round trip


def test_get_status_skips_the_read_when_not_connected():
    feature, valorant, _ = make_feature(connected=False)

    status = feature.get_status()

    assert status == {"key": "valorant_chat_toggle", "disconnected": False}
    assert valorant.calls == []


def test_toggle_suspends_chat_when_connected():
    feature, valorant, events = make_feature()

    result = feature.toggle()

    assert result is True
    assert feature.disconnected is True
    assert valorant.calls[-1] == ("POST", "/chat/v1/suspend", {"config": "disable"})
    assert events[-1] == ("info", "Chat disconnected")


def test_toggle_resumes_chat_when_already_disconnected():
    feature, valorant, events = make_feature()
    feature.disconnected = True

    result = feature.toggle()

    assert result is False
    assert valorant.calls[-1] == ("POST", "/chat/v1/resume", None)
    assert events[-1] == ("info", "Chat reconnected")


def test_toggle_raises_on_a_failed_response():
    feature, valorant, _ = make_feature()
    valorant.next_response = FakeResponse(status_code=500)

    try:
        feature.toggle()
        pytest.fail("expected RuntimeError")
    except RuntimeError as exc:
        assert "500" in str(exc)
