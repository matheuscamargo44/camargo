import copy

from core.config import DEFAULT_CONFIG
from features.dodge import Dodge


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


class FakeLCUClient:
    def __init__(self, status_codes):
        self._status_codes = list(status_codes)
        self.calls = []

    def lcu_request(self, method, endpoint, body=""):
        self.calls.append((method, endpoint))
        return FakeResponse(self._status_codes.pop(0))


def make_feature(status_codes):
    lcu = FakeLCUClient(status_codes)
    events = []
    feature = Dodge(lcu, copy.deepcopy(DEFAULT_CONFIG), on_event=lambda l, m: events.append((l, m)))
    return feature, lcu, events


def test_dodge_succeeds_when_any_request_succeeds():
    feature, lcu, events = make_feature([404, 404, 200, 404, 404])

    feature.dodge()

    assert len(lcu.calls) == 5
    assert events[-1][0] == "success"


def test_dodge_raises_when_all_requests_fail():
    feature, _, _ = make_feature([404] * 5)

    try:
        feature.dodge()
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
