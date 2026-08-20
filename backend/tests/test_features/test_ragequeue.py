import copy

from core.config import DEFAULT_CONFIG
from features.ragequeue import RageQueue


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}

    def json(self):
        return self._json_data


class FakeLCUClient:
    def __init__(self):
        self.calls = []

    def lcu_request(self, method, endpoint, body=""):
        self.calls.append((method, endpoint, body))
        return FakeResponse(200)


def make_feature():
    lcu = FakeLCUClient()
    events = []
    feature = RageQueue(lcu, copy.deepcopy(DEFAULT_CONFIG), on_event=lambda l, m: events.append((l, m)))
    return feature, lcu, events


def test_configure_positionless_queue():
    feature, _, events = make_feature()

    feature.configure(queue_id=450)

    assert feature.queue_id == 450
    assert feature.enabled is True
    assert events[-1] == ("success", "Ragequeue configured for ARAM")


def test_configure_rejects_unknown_queue():
    feature, _, _ = make_feature()

    try:
        feature.configure(queue_id=99999)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_disable_resets_state():
    feature, _, events = make_feature()
    feature.configure(queue_id=420, first_position="TOP", second_position="JUNGLE")

    feature.disable()

    assert feature.enabled is False
    assert feature.config["ragequeue"]["enabled"] is False
    assert events[-1] == ("info", "Ragequeue disabled")
