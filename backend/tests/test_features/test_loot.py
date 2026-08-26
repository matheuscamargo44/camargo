"""MassDisenchant.get_status: tallying loot without crashing on a null lootId."""
from features.loot import MassDisenchant


class StubLCUClient:
    def __init__(self, loot_list):
        self._loot_list = loot_list

    def is_league_connected(self):
        return True

    def lcu_request(self, method, endpoint, body=None):
        return _Response(200, self._loot_list)


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def make_feature(loot_list):
    return MassDisenchant(StubLCUClient(loot_list), {})


def test_get_status_survives_a_null_loot_id():
    """The bug: item.get("lootId", "") returns None (not the default) when
    the key exists with a null value - a placeholder/event loot entry shaped
    that way crashed .startswith() with an unhandled AttributeError."""
    feature = make_feature([
        {"type": "CHEST", "lootId": None, "count": 1},
        {"type": "CHAMPION", "lootId": "CHAMPION_1", "count": 2},
    ])

    status = feature.get_status()

    assert status["champion_shards"] == 2


def test_get_status_still_counts_a_real_chest():
    feature = make_feature([
        {"type": "CHEST", "lootId": "CHEST_generic", "count": 3},
    ])

    status = feature.get_status()

    assert status["chests"] == 3


def test_open_chests_survives_a_null_loot_id():
    """The real bug here was a crash (AttributeError on .startswith()), not
    a wrong count - this only needs to prove it doesn't raise."""
    feature = make_feature([
        {"type": "CHEST", "lootId": None, "count": 1},
    ])

    feature.open_chests()  # must not raise
