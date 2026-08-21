"""The features that had no test at all: background, badges, status message,
remove friends and restart UX. Several are destructive, so their failure
paths matter as much as the happy ones.
"""
import copy

import pytest

from core.config import DEFAULT_CONFIG
from features.customization import Background, Badges, StatusMessage
from features.social import RemoveFriends, RestartUX


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}

    def json(self):
        return self._json_data


class FakeLCUClient:
    def __init__(self, responses=None, default=None):
        self.calls = []
        self.responses = responses or {}
        self.default = default or FakeResponse()

    def is_league_connected(self):
        return True

    def lcu_request(self, method, endpoint, body=""):
        self.calls.append((method, endpoint, body))
        # Exact match only: "/lol-chat/v1/friends" must not also answer for
        # "/lol-chat/v1/friends/<id>", which is a different call.
        if endpoint in self.responses:
            return self.responses[endpoint]
        return self.default

    riot_request = lcu_request


def build(cls, lcu):
    return cls(lcu, copy.deepcopy(DEFAULT_CONFIG))


# --- Background ---------------------------------------------------------

def test_background_sends_the_skin_id():
    lcu = FakeLCUClient()
    build(Background, lcu).change("12345")

    method, endpoint, body = lcu.calls[-1]
    assert method == "POST"
    assert endpoint.endswith("/summoner-profile")
    assert body == {"key": "backgroundSkinId", "value": 12345}


def test_background_rejects_a_non_numeric_skin():
    with pytest.raises(ValueError):
        build(Background, FakeLCUClient()).change("garen")


def test_background_raises_when_the_client_refuses():
    lcu = FakeLCUClient(default=FakeResponse(status_code=500))
    with pytest.raises(RuntimeError, match="500"):
        build(Background, lcu).change(1)


# --- Badges -------------------------------------------------------------

PLAYER_DATA = {"topChallenges": [{"id": "401101"}], "title": {"itemId": 5}, "bannerId": "banner-1"}


def test_badges_empty_mode_clears_the_challenge_ids():
    lcu = FakeLCUClient(default=FakeResponse(json_data=PLAYER_DATA))
    assert build(Badges, lcu).change("empty") == []

    _, endpoint, body = lcu.calls[-1]
    assert "update-player-preferences" in endpoint
    assert body["challengeIds"] == []


def test_badges_copy_mode_repeats_the_top_badge():
    lcu = FakeLCUClient(default=FakeResponse(json_data=PLAYER_DATA))
    assert build(Badges, lcu).change("copy") == [401101, 401101, 401101]


def test_badges_copy_mode_needs_something_to_copy():
    lcu = FakeLCUClient(default=FakeResponse(json_data={"topChallenges": []}))
    with pytest.raises(ValueError, match="no badges"):
        build(Badges, lcu).change("copy")


def test_badges_rejects_an_unknown_mode():
    with pytest.raises(ValueError, match="Unknown badge mode"):
        build(Badges, FakeLCUClient()).change("sparkly")


@pytest.mark.parametrize("glitched_id", [-1, 6, 99])
def test_badges_glitched_id_must_be_in_range(glitched_id):
    lcu = FakeLCUClient(default=FakeResponse(json_data=PLAYER_DATA))
    with pytest.raises(ValueError, match="between 0 and 5"):
        build(Badges, lcu).change("glitched", glitched_id)


def test_badges_glitched_mode_repeats_the_chosen_id():
    lcu = FakeLCUClient(default=FakeResponse(json_data=PLAYER_DATA))
    assert build(Badges, lcu).change("glitched", 3) == [3, 3, 3]


# --- Status message -----------------------------------------------------

def test_status_message_is_sent_to_chat():
    lcu = FakeLCUClient()
    build(StatusMessage, lcu).change("afk farmando")

    method, endpoint, body = lcu.calls[-1]
    assert (method, endpoint) == ("PUT", "/lol-chat/v1/me")
    assert body == {"statusMessage": "afk farmando"}


def test_status_message_raises_when_rejected():
    lcu = FakeLCUClient(default=FakeResponse(status_code=400))
    with pytest.raises(RuntimeError, match="400"):
        build(StatusMessage, lcu).change("x")


# --- Remove friends (destructive) ---------------------------------------

FRIENDS = [{"pid": "a@pvp"}, {"pid": "b@pvp"}, {"name": "no-pid"}]


def test_remove_all_deletes_every_friend_with_an_id():
    lcu = FakeLCUClient(
        responses={"/lol-chat/v1/friends": FakeResponse(json_data=FRIENDS)},
        default=FakeResponse(status_code=204),
    )
    feature = build(RemoveFriends, lcu)

    removed, failed = feature.remove_all()

    assert (removed, failed) == (2, 1), "the entry without a pid counts as failed"
    deletes = [c for c in lcu.calls if c[0] == "DELETE"]
    assert [c[1] for c in deletes] == ["/lol-chat/v1/friends/a@pvp", "/lol-chat/v1/friends/b@pvp"]


def test_remove_all_reports_failures_instead_of_stopping():
    lcu = FakeLCUClient(
        responses={"/lol-chat/v1/friends": FakeResponse(json_data=[{"pid": "a@pvp"}, {"pid": "b@pvp"}])},
        default=FakeResponse(status_code=500),
    )

    removed, failed = build(RemoveFriends, lcu).remove_all()

    assert (removed, failed) == (0, 2)


def test_remove_all_raises_when_the_friend_list_cannot_be_read():
    lcu = FakeLCUClient(responses={"/lol-chat/v1/friends": FakeResponse(status_code=503)})
    with pytest.raises(RuntimeError, match="503"):
        build(RemoveFriends, lcu).remove_all()


# --- Restart UX ---------------------------------------------------------

def test_restart_ux_calls_the_riot_client():
    lcu = FakeLCUClient()
    build(RestartUX, lcu).restart()

    method, endpoint, _ = lcu.calls[-1]
    assert (method, endpoint) == ("POST", "/riotclient/kill-and-restart-ux")


def test_restart_ux_raises_on_failure():
    lcu = FakeLCUClient(default=FakeResponse(status_code=500))
    with pytest.raises(RuntimeError, match="500"):
        build(RestartUX, lcu).restart()
