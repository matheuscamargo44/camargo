"""True end-to-end scenarios: real feature classes, real background polling
threads, a real `LCUClient` making real HTTP calls to a fake-but-real LCU
server (see fake_lcu_server.py) - the only things not real are League
itself and the Electron UI.

This is the layer nothing else in the suite covers: the API integration
tests (test_api_integration.py) exercise the HTTP contract without ever
starting a feature's background loop; the feature unit tests
(test_features/*.py) call feature methods directly, bypassing LCUClient
and real HTTP entirely. Here, a scenario mutates the fake server's state
the way a real League client session would change, and asserts on the
real HTTP requests the feature's real background thread actually sent -
re-validating several of this session's bug fixes one level more "for
real" than their original regression tests.
"""
import copy
import time

import pytest

import core.lcu_client as lcu_client_module
from core.config import DEFAULT_CONFIG
from core.lcu_client import LCUClient
from features.aram_bench_swap import AramBenchSwap
from features.auto_honor import AutoHonor
from features.auto_play_again import AutoPlayAgain
from features.autoban import AutoBan
from features.instalock import Instalock
from tests.e2e.fake_lcu_server import start_fake_lcu_server

pytestmark = pytest.mark.e2e

#: Real loop intervals (0.3-2s) - generous enough that a slow CI machine
#: won't flake, short enough that the suite doesn't crawl.
POLL_TIMEOUT_SECONDS = 5.0
POLL_INTERVAL_SECONDS = 0.05


def wait_until(predicate, timeout=POLL_TIMEOUT_SECONDS):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(POLL_INTERVAL_SECONDS)
    return predicate()


@pytest.fixture
def fake_league(monkeypatch):
    """A real LCUClient pointed at a real (fake) HTTP server, bypassing
    only credential *discovery* (there is no real leagueclientux.exe
    process to scan for in a test env) - everything downstream of that is
    the genuine client/server request-response cycle.
    """
    server = start_fake_lcu_server()
    port, token = str(server.port), "fake-token"

    monkeypatch.setattr(lcu_client_module, "find_league_client_credentials", lambda: (port, token))
    monkeypatch.setattr(lcu_client_module, "find_riot_client_credentials", lambda: (None, None))
    monkeypatch.setattr(lcu_client_module, "_service_url", lambda p: f"http://127.0.0.1:{p}" if p else None)

    client = LCUClient()
    assert client.is_league_connected()

    try:
        yield server, client
    finally:
        server.stop()


def make_config():
    return copy.deepcopy(DEFAULT_CONFIG)


# -- Instalock: falls through to the next priority pick when the enemy already has the first --


def test_instalock_falls_through_to_second_choice_when_enemy_has_the_first(fake_league):
    server, client = fake_league
    feature = Instalock(client, make_config())
    feature.champions = ["Yasuo", "Ahri"]
    feature.enabled = True

    server.state.open_champ_select(
        my_team=[{"cellId": 0, "championId": 0}],
        their_team=[{"cellId": 5, "championId": 157}],  # enemy already has Yasuo
    )
    server.state.add_pending_action(action_id=1, cell_id=0)

    feature.start()
    try:
        assert wait_until(lambda: server.state.requests_to("/lol-champ-select/v1/session/actions/1", "PATCH"))
    finally:
        feature.stop()

    locked = server.state.requests_to("/lol-champ-select/v1/session/actions/1", "PATCH")[0]
    assert locked["body"]["championId"] == 103  # Ahri, not Yasuo (id 157)


# -- AutoBan: same fallthrough behavior, for bans instead of picks --


def test_autoban_falls_through_a_champion_already_banned(fake_league):
    server, client = fake_league
    feature = AutoBan(client, make_config())
    feature.champions = ["Lux", "Ziggs"]
    feature.enabled = True
    feature.champ_dict = {"lux": 99, "ziggs": 115}

    server.state.open_champ_select(
        my_team=[{"cellId": 0, "championId": 0}],
        bans={"myTeamBans": [], "theirTeamBans": [99]},  # Lux already banned
    )
    server.state.add_pending_action(action_id=1, cell_id=0, action_type="ban")

    feature.start()
    try:
        assert wait_until(lambda: server.state.requests_to("/lol-champ-select/v1/session/actions/1", "PATCH"))
    finally:
        feature.stop()

    banned = server.state.requests_to("/lol-champ-select/v1/session/actions/1", "PATCH")[0]
    assert banned["body"]["championId"] == 115  # Ziggs, not Lux


# -- Aram Bench Swap: no ping-ponging once the top priority is already held --


def test_bench_swap_does_not_downgrade_once_top_priority_is_held(fake_league):
    """End-to-end re-validation of this session's ping-pong fix (see
    features/aram_bench_swap.py) - real loop, real HTTP swap calls."""
    server, client = fake_league
    feature = AramBenchSwap(client, make_config())
    feature.champions = ["Lux", "Ziggs"]
    feature.enabled = True
    feature.champ_dict = {"lux": 99, "ziggs": 115, "garen": 86}

    server.state.open_champ_select(
        my_team=[{"cellId": 0, "championId": 86}],  # currently holding Garen
        bench=[{"championId": 99}, {"championId": 115}],  # both Lux and Ziggs on the bench
    )

    feature.start()
    try:
        # First swap should go to Lux (top priority).
        assert wait_until(lambda: server.state.requests_to("/lol-champ-select/v1/session/bench/swap/99"))
        # The loop pauses 2s after a successful swap before checking again -
        # a ping-pong bug's second (downgrading) swap wouldn't appear until
        # after that cooldown, so this has to wait past it, not just a tick.
        time.sleep(3.0)
    finally:
        feature.stop()

    swap_calls = server.state.requests_to("/lol-champ-select/v1/session/bench/swap/")
    swapped_champion_ids = {int(r["path"].rsplit("/", 1)[1]) for r in swap_calls}
    assert swapped_champion_ids == {99}  # only ever swapped to Lux, never downgraded to Ziggs


# -- Auto Honor: duo tracking doesn't leak into an unrelated later game --


def test_auto_honor_does_not_vote_for_a_stale_duo_partner(fake_league):
    """End-to-end re-validation of the party-latch fix - a duo lobby
    followed by a solo lobby must not leave the duo's puuid live."""
    server, client = fake_league
    feature = AutoHonor(client, make_config())
    feature.config["auto_honor"]["enabled"] = True

    # Game 1: duo lobby with a friend.
    server.state.lobby = {
        "localMember": {"puuid": "me"},
        "members": [{"puuid": "me"}, {"puuid": "friend"}],
    }

    feature.start()
    try:
        assert wait_until(lambda: feature.party_member_puuids == {"friend"})

        # Solo lobby now - the duo is over.
        server.state.lobby = {"localMember": {"puuid": "me"}, "members": [{"puuid": "me"}]}
        assert wait_until(lambda: feature.party_member_puuids == set())

        # A new game's ballot includes "friend" as a regular teammate now.
        server.state.honor_ballot = {
            "gameId": 555,
            "eligibleAllies": [{"puuid": "friend", "summonerId": 9}],
        }
        time.sleep(1.0)  # give the loop several ticks to (not) vote
    finally:
        feature.stop()

    assert server.state.requests_to("/lol-honor-v2/v1/honor-player", "POST") == []


# -- Auto Play Again: fires exactly once across the real WaitingForStats -> EndOfGame sequence --


def test_play_again_fires_exactly_once_across_the_real_phase_sequence(fake_league):
    server, client = fake_league
    feature = AutoPlayAgain(client, make_config())
    feature.config["auto_play_again"]["enabled"] = True

    feature.start()
    try:
        server.state.gameflow_phase = "WaitingForStats"
        # Wait for the loop to actually observe and act on WaitingForStats
        # before moving on - flipping the phase too early would make the
        # loop's first read land directly on EndOfGame, skipping the
        # WaitingForStats->EndOfGame transition entirely and passing this
        # test regardless of whether the double-fire bug exists.
        assert wait_until(lambda: len(server.state.requests_to("/lol-lobby/v2/play-again", "POST")) >= 1)
        server.state.gameflow_phase = "EndOfGame"
        # The loop sleeps ~2s after handling a phase before it reads phase
        # again at all - waiting less than that would pass regardless of
        # whether the double-fire bug exists, the same trap bench_swap's
        # test above avoids for the same reason.
        time.sleep(3.0)
    finally:
        feature.stop()

    assert len(server.state.requests_to("/lol-lobby/v2/play-again", "POST")) == 1
