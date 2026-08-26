"""AutoHonor: party/duo tracking and honor-target selection."""
import copy

from core.config import DEFAULT_CONFIG
from features.auto_honor import AutoHonor


class StubLCUClient:
    def __init__(self, lobby_response=None):
        self._lobby_response = lobby_response

    def is_league_connected(self):
        return True

    def lcu_request(self, method, endpoint, body=""):
        raise AssertionError("this test does not expect an LCU call")


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def make_feature():
    return AutoHonor(StubLCUClient(), copy.deepcopy(DEFAULT_CONFIG))


def test_party_members_are_synced_from_a_duo_lobby(monkeypatch):
    feature = make_feature()
    lobby = {
        "localMember": {"puuid": "me"},
        "members": [{"puuid": "me"}, {"puuid": "friend"}],
    }
    monkeypatch.setattr(feature.lcu, "lcu_request", lambda method, endpoint: _Response(200, lobby))

    feature._update_party_members()

    assert feature.party_member_puuids == {"friend"}


def test_a_later_solo_lobby_clears_the_stale_duo(monkeypatch):
    """The bug: only assigning when non-empty meant a duo's party ids
    survived forever into every later solo lobby - a random future
    teammate who happened to share one of those stale ids would be
    auto-honored as if they were still that duo partner."""
    feature = make_feature()
    feature.party_member_puuids = {"friend"}
    feature.party_member_summoner_ids = {42}

    solo_lobby = {"localMember": {"puuid": "me"}, "members": [{"puuid": "me"}]}
    monkeypatch.setattr(feature.lcu, "lcu_request", lambda method, endpoint: _Response(200, solo_lobby))

    feature._update_party_members()

    assert feature.party_member_puuids == set()
    assert feature.party_member_summoner_ids == set()


def test_a_failed_lobby_fetch_leaves_the_last_known_party_intact(monkeypatch):
    """/lol-lobby/v2/lobby only exists pre-game - a non-200 later (e.g.
    mid-game) must not erase the party info the post-game ballot needs."""
    feature = make_feature()
    feature.party_member_puuids = {"friend"}
    monkeypatch.setattr(feature.lcu, "lcu_request", lambda method, endpoint: _Response(404, {}))

    feature._update_party_members()

    assert feature.party_member_puuids == {"friend"}


def test_pick_honor_target_matches_a_known_party_member():
    feature = make_feature()
    feature.party_member_puuids = {"friend"}

    target = feature.pick_honor_target([{"puuid": "stranger"}, {"puuid": "friend"}])

    assert target == {"puuid": "friend"}


def test_pick_honor_target_is_none_when_nobody_eligible_is_known():
    feature = make_feature()

    assert feature.pick_honor_target([{"puuid": "stranger"}]) is None
