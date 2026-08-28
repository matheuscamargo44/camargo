"""CounterPickAdvisor: showing who beats the enemy laner.

The OP.GG call is stubbed - what is covered here is reading champ select
correctly (which enemy is even in my lane), degrading rather than guessing
when the answer is unknowable, and not spamming the log on a 1s poll.
"""
import copy

import pytest

from core.config import DEFAULT_CONFIG
from features.counter_pick_advisor import CounterPickAdvisor


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text if text is not None else str(self._payload)

    def json(self):
        return self._payload


class StubLCUClient:
    def is_league_connected(self):
        return True

    def lcu_request(self, method, endpoint, body=""):
        if endpoint == "/lol-game-data/assets/v1/champion-summary.json":
            return FakeResponse(200, [
                {"id": 122, "name": "Darius"},
                {"id": 103, "name": "Ahri"},
                {"id": -1, "name": "None"},
            ])
        raise AssertionError(f"unexpected call: {endpoint}")


COUNTERS = [
    {"name": "Jayce", "win_rate": 0.58},
    {"name": "Camille", "win_rate": 0.53},
    {"name": "K'Sante", "win_rate": 0.53},
]


def make_feature(monkeypatch, counters=COUNTERS, champions=None):
    import features.counter_pick_advisor as module

    calls = []

    def fake_counters(champion_name, position):
        calls.append((champion_name, position))
        if counters is None:
            raise RuntimeError("OP.GG is down")
        return counters

    monkeypatch.setattr(module.opgg_client, "get_champion_counters", fake_counters)

    config = copy.deepcopy(DEFAULT_CONFIG)
    if champions is not None:
        config["instalock"]["champions"] = champions
    events = []
    feature = CounterPickAdvisor(
        StubLCUClient(), config, on_event=lambda level, message: events.append(message)
    )
    return feature, calls, events


def session(my_position="TOP", their=None, cell_id=0):
    return {
        "localPlayerCellId": cell_id,
        "myTeam": [{"cellId": cell_id, "assignedPosition": my_position}],
        "theirTeam": their if their is not None else [{"assignedPosition": "TOP", "championId": 122}],
    }


# -- the happy path --


def test_the_enemy_in_my_lane_drives_the_recommendation(monkeypatch):
    feature, calls, _ = make_feature(monkeypatch)

    feature._update(session(), 0)
    recommendation = feature.get_status()["recommendation"]

    assert calls == [("Darius", "top")]
    assert recommendation["enemy"] == "Darius"
    assert recommendation["position"] == "top"
    assert [c["name"] for c in recommendation["counters"]] == ["Jayce", "Camille", "K'Sante"]


def test_a_counter_already_in_the_priority_list_is_flagged(monkeypatch):
    """Flagging what the player already queued is what turns the list from
    trivia into something they can act on."""
    feature, _, _ = make_feature(monkeypatch, champions=["camille", "Garen"])

    feature._update(session(), 0)
    counters = feature.get_status()["recommendation"]["counters"]

    assert [c["in_my_list"] for c in counters] == [False, True, False]


def test_only_the_first_three_counters_are_shown(monkeypatch):
    many = [{"name": f"Champ{i}", "win_rate": 0.5} for i in range(10)]
    feature, _, _ = make_feature(monkeypatch, counters=many)

    feature._update(session(), 0)

    assert len(feature.get_status()["recommendation"]["counters"]) == 3


def test_the_enemy_laner_is_matched_by_role_not_by_pick_order(monkeypatch):
    """The first enemy to lock is usually not the one in your lane."""
    feature, calls, _ = make_feature(monkeypatch)

    feature._update(
        session(
            my_position="MIDDLE",
            their=[
                {"assignedPosition": "TOP", "championId": 122},
                {"assignedPosition": "MIDDLE", "championId": 103},
            ],
        ),
        0,
    )

    assert calls == [("Ahri", "mid")]


# -- degrading instead of guessing --


@pytest.mark.parametrize(
    "case,payload",
    [
        # ARAM and blind pick have no assignedPosition at all.
        ("no assigned position", {"my_position": None}),
        # Enemy laner has not locked in yet.
        ("enemy has not picked", {"their": [{"assignedPosition": "TOP", "championId": 0}]}),
        # Nobody assigned to my lane on their side.
        ("no enemy in my lane", {"their": [{"assignedPosition": "JUNGLE", "championId": 122}]}),
    ],
)
def test_an_unknowable_matchup_shows_nothing(monkeypatch, case, payload):
    feature, calls, _ = make_feature(monkeypatch)

    feature._update(session(**payload), 0)

    assert feature.get_status()["recommendation"] is None, case
    assert calls == [], case


def test_an_opgg_failure_is_not_cached(monkeypatch):
    """A network blip on the first pick must not disable the advisor for
    every later pick in the same session."""
    feature, calls, _ = make_feature(monkeypatch, counters=None)

    feature._update(session(), 0)
    feature._update(session(), 0)

    assert feature.get_status()["recommendation"] is None
    assert len(calls) == 2  # retried, not served from a cached failure


def test_the_same_matchup_is_only_looked_up_once(monkeypatch):
    """The loop re-reads champ select every second; each of those must not
    become a ~3s OP.GG call."""
    feature, calls, _ = make_feature(monkeypatch)

    for _ in range(5):
        feature._update(session(), 0)

    assert len(calls) == 1


def test_the_recommendation_is_announced_once_per_matchup(monkeypatch):
    """Announcing on every 1s tick would bury the activity log."""
    feature, _, events = make_feature(monkeypatch)

    for _ in range(5):
        feature._update(session(), 0)

    assert events == ["Counter Picks: vs Darius try Jayce (58%)"]


def test_a_different_matchup_is_announced_again(monkeypatch):
    feature, _, events = make_feature(monkeypatch)

    feature._update(session(), 0)
    feature._update(session(my_position="MIDDLE", their=[{"assignedPosition": "MIDDLE", "championId": 103}]), 0)

    assert len(events) == 2
    assert "Ahri" in events[1]


def test_losing_champ_select_clears_the_advice():
    """It must not linger into the next lobby."""
    feature = CounterPickAdvisor(StubLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature._recommendation = {"enemy": "Darius"}

    feature._reset()

    assert feature.get_status()["recommendation"] is None


def test_the_advisor_has_no_switch():
    """It only ever displays something, and only while champ select is
    open. A toggle would add nothing to protect the player from, and would
    be one more thing to have left off on the pick where it mattered."""
    assert not hasattr(CounterPickAdvisor, "toggle")
    assert "enabled" not in CounterPickAdvisor(StubLCUClient(), copy.deepcopy(DEFAULT_CONFIG)).get_status()
