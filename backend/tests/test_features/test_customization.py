"""Badges.change: profile badge/title updates."""
from features.customization import Badges


class StubLCUClient:
    def __init__(self, player_data, update_status=200):
        self._player_data = player_data
        self._update_status = update_status
        self.last_payload = None

    def is_league_connected(self):
        return True

    def lcu_request(self, method, endpoint, body=None):
        if endpoint == "/lol-challenges/v1/summary-player-data/local-player":
            return _Response(200, self._player_data)
        self.last_payload = body
        return _Response(self._update_status, None)


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def make_feature(player_data):
    return Badges(StubLCUClient(player_data), {})


def test_empty_mode_works_when_no_title_is_equipped():
    """The bug: the LCU returns "title": null (not a missing key) for a
    player with no challenge title equipped - data.get("title", {}) does
    not catch a null value, only a missing one, so .get("itemId") crashed
    with AttributeError on the single most common account state."""
    feature = make_feature({"title": None, "topChallenges": []})

    result = feature.change("empty")

    assert result == []


def test_title_is_included_in_the_payload_when_one_is_equipped():
    feature = make_feature({"title": {"itemId": 42}, "topChallenges": []})

    feature.change("empty")

    assert feature.lcu.last_payload["title"] == "42"


def test_copy_mode_duplicates_the_top_badge():
    feature = make_feature({"title": None, "topChallenges": [{"id": 7}]})

    result = feature.change("copy")

    assert result == [7, 7, 7]


def test_copy_mode_with_no_badges_to_copy_raises():
    feature = make_feature({"title": None, "topChallenges": []})

    try:
        feature.change("copy")
        assert False, "expected a ValueError"
    except ValueError:
        pass
