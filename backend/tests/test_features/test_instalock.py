"""Instalock.resolve_champion: picking the best still-available priority
entry, excluding what's taken on both teams."""
import copy

from core.config import DEFAULT_CONFIG
from features.instalock import Instalock


class StubLCUClient:
    def is_league_connected(self):
        return True

    def lcu_request(self, method, endpoint, body=""):
        raise AssertionError("this test does not expect an LCU call")


def make_feature(champions):
    feature = Instalock(StubLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature.champ_dict = {"lux": 99, "yasuo": 157, "ahri": 103}
    feature.champions = champions
    return feature


def _session(my_team=None, their_team=None, bans=None):
    return {
        "myTeam": my_team or [],
        "theirTeam": their_team or [],
        "bans": bans or {},
    }


def test_falls_through_when_the_enemy_already_locked_the_top_pick():
    """The bug: without checking theirTeam, resolve_champion kept returning
    an enemy-locked champion forever, and every lock attempt against it was
    rejected by the LCU."""
    feature = make_feature(["Yasuo", "Ahri"])
    session = _session(
        my_team=[{"cellId": 0, "championId": 0}],
        their_team=[{"cellId": 5, "championId": 157}],  # enemy already has Yasuo
    )

    assert feature.resolve_champion(session, cell_id=0) == "Ahri"


def test_still_locks_the_top_pick_when_the_enemy_has_something_else():
    feature = make_feature(["Yasuo", "Ahri"])
    session = _session(
        my_team=[{"cellId": 0, "championId": 0}],
        their_team=[{"cellId": 5, "championId": 99}],  # enemy has Lux, not Yasuo
    )

    assert feature.resolve_champion(session, cell_id=0) == "Yasuo"


def test_no_available_champion_resolves_to_none():
    feature = make_feature(["Yasuo"])
    session = _session(their_team=[{"cellId": 5, "championId": 157}])

    assert feature.resolve_champion(session, cell_id=0) is None
