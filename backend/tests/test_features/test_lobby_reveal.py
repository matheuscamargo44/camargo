"""LobbyReveal: turning a champ-select lobby into a third-party scouting URL.

The provider matrix (3 sites, 2 Riot-ID spellings, 2 region spellings) is
the part most likely to be silently wrong - a malformed URL still opens a
browser, it just lands on a 404 - so it is covered directly against
`build_reveal_url`, with no client involved.
"""
import copy

import pytest

from core.config import DEFAULT_CONFIG
from features.lobby_reveal import LobbyReveal, build_reveal_url


class StubLCUClient:
    """Answers the three endpoints reveal() reads, from canned data."""

    def __init__(self, team=None, summoners=None, region="na", chat=None):
        self.team = team if team is not None else []
        self.summoners = summoners or {}
        self.region = region
        self.chat = chat
        self.riot_calls = 0

    def is_league_connected(self):
        return True

    def lcu_request(self, method, endpoint, body=""):
        if endpoint == "/lol-champ-select/v1/session":
            return FakeResponse(200, {"myTeam": self.team})
        if endpoint == "/riotclient/region-locale":
            return FakeResponse(200, {"webRegion": self.region})
        if endpoint.startswith("/lol-summoner/v1/summoners/"):
            summoner_id = endpoint.rsplit("/", 1)[1]
            if summoner_id in self.summoners:
                return FakeResponse(200, self.summoners[summoner_id])
            return FakeResponse(404, {})
        raise AssertionError(f"unexpected LCU call: {endpoint}")

    def riot_request(self, method, endpoint, body=""):
        self.riot_calls += 1
        assert endpoint == "/chat/v5/participants"
        return FakeResponse(200, self.chat if self.chat is not None else {})


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def make_feature(client, provider=None):
    config = copy.deepcopy(DEFAULT_CONFIG)
    if provider:
        config["lobby_reveal"]["provider"] = provider
    return LobbyReveal(client, config)


# -- the URL matrix --


def test_porofessor_url_uses_the_plain_region_and_hash_riot_ids():
    url = build_reveal_url("porofessor", "br", ["Ahri#BR1", "Zed#BR1"])
    assert url == "https://porofessor.gg/pregame/br/Ahri%23BR1,Zed%23BR1/soloqueue/season"


def test_opgg_url_passes_summoners_as_a_query_parameter():
    url = build_reveal_url("opgg", "br", ["Ahri#BR1", "Zed#BR1"])
    assert url == "https://www.op.gg/multisearch/br?summoners=Ahri%23BR1,Zed%23BR1"


def test_ugg_url_uses_the_platform_id_and_dashed_riot_ids():
    """U.GG is the odd one out on both axes at once - a dashed Riot ID and
    Riot's platform id (na1) rather than the web region (na) the client
    itself reports."""
    url = build_reveal_url("ugg", "na", ["Ahri#NA1", "Zed#NA1"])
    assert url == "https://u.gg/lol/multisearch?summoners=Ahri-NA1,Zed-NA1&region=na1"


def test_ugg_passes_an_unmapped_region_through_unchanged():
    """A region Riot adds after this shipped should degrade to 'probably
    right', not raise."""
    url = build_reveal_url("ugg", "me", ["Ahri#ME1"])
    assert "region=me" in url


def test_the_hash_in_a_riot_id_is_always_escaped():
    """An unescaped # starts a URL fragment, which would silently truncate
    the summoner list at the first player on every provider that takes
    Name#TAG."""
    for provider in ("porofessor", "opgg"):
        assert "%23" in build_reveal_url(provider, "na", ["Ahri#NA1", "Zed#NA1"])
        assert "#" not in build_reveal_url(provider, "na", ["Ahri#NA1", "Zed#NA1"])


def test_the_comma_separator_stays_readable():
    assert ",Zed" in build_reveal_url("opgg", "na", ["Ahri#NA1", "Zed#NA1"])


@pytest.mark.parametrize(
    "provider,region,ids",
    [("nowhere", "na", ["Ahri#NA1"]), ("opgg", "na", []), ("opgg", "", ["Ahri#NA1"])],
)
def test_an_unusable_request_raises_instead_of_building_a_broken_url(provider, region, ids):
    with pytest.raises(ValueError):
        build_reveal_url(provider, region, ids)


# -- reading the lobby --


def test_visible_names_are_read_from_the_summoner_endpoint(monkeypatch):
    client = StubLCUClient(
        team=[{"summonerId": 1}, {"summonerId": 2}],
        summoners={
            "1": {"gameName": "Ahri", "tagLine": "NA1"},
            "2": {"gameName": "Zed", "tagLine": "NA1"},
        },
    )
    feature = make_feature(client)
    opened = _capture_browser(monkeypatch)

    result = feature.reveal()

    assert result["count"] == 2
    assert "Ahri%23NA1,Zed%23NA1" in opened[0]
    assert client.riot_calls == 0  # no need for the chat fallback here


def test_hidden_names_fall_back_to_the_riot_chat_service(monkeypatch):
    """Riot hides teammate names in champ select for most queues now, which
    makes the summoner lookup come back empty exactly when the feature is
    most wanted. The chat service still exposes them."""
    client = StubLCUClient(
        team=[{"summonerId": 1, "nameVisibilityType": "HIDDEN"}],
        chat={
            "participants": [
                {"cid": "abc|champ-select", "game_name": "Ahri", "game_tag": "NA1"},
                {"cid": "abc|champ-select", "game_name": "Zed", "game_tag": "NA1"},
            ]
        },
    )
    feature = make_feature(client)
    opened = _capture_browser(monkeypatch)

    result = feature.reveal()

    assert client.riot_calls == 1
    assert result["count"] == 2
    assert "Ahri%23NA1,Zed%23NA1" in opened[0]


def test_chat_rooms_other_than_champ_select_are_ignored(monkeypatch):
    """The chat service lists every room the client is in - a friend in a
    private conversation is not in this lobby."""
    client = StubLCUClient(
        team=[{"nameVisibilityType": "HIDDEN"}],
        chat={
            "participants": [
                {"cid": "abc|champ-select", "game_name": "Ahri", "game_tag": "NA1"},
                {"cid": "xyz|private", "game_name": "Friend", "game_tag": "NA1"},
            ]
        },
    )
    feature = make_feature(client)
    opened = _capture_browser(monkeypatch)

    feature.reveal()

    assert "Ahri" in opened[0]
    assert "Friend" not in opened[0]


def test_a_placeholder_summoner_id_is_skipped(monkeypatch):
    """An unfilled bot/empty slot comes back as id 0 and has no profile to
    look up."""
    client = StubLCUClient(
        team=[{"summonerId": 0}, {"summonerId": 1}],
        summoners={"1": {"gameName": "Ahri", "tagLine": "NA1"}},
    )
    feature = make_feature(client)
    opened = _capture_browser(monkeypatch)

    assert feature.reveal()["count"] == 1
    assert "Ahri" in opened[0]


def test_outside_champ_select_it_refuses_rather_than_opening_a_blank_page(monkeypatch):
    """The LCU answers a closed champ select with 200 and an RPC_ERROR
    body, not a 404 - checking the status code alone would sail past it."""

    class ClosedClient(StubLCUClient):
        def lcu_request(self, method, endpoint, body=""):
            if endpoint == "/lol-champ-select/v1/session":
                response = FakeResponse(200, {})
                response.text = '{"errorCode":"RPC_ERROR"}'
                return response
            return super().lcu_request(method, endpoint, body)

    feature = make_feature(ClosedClient())
    opened = _capture_browser(monkeypatch)

    with pytest.raises(RuntimeError):
        feature.reveal()
    assert opened == []


def test_an_unreadable_region_refuses_rather_than_guessing(monkeypatch):
    client = StubLCUClient(
        team=[{"summonerId": 1}],
        summoners={"1": {"gameName": "Ahri", "tagLine": "NA1"}},
        region="",
    )
    feature = make_feature(client)
    opened = _capture_browser(monkeypatch)

    with pytest.raises(RuntimeError):
        feature.reveal()
    assert opened == []


# -- provider setting --


def test_the_configured_provider_is_the_one_opened(monkeypatch):
    client = StubLCUClient(
        team=[{"summonerId": 1}], summoners={"1": {"gameName": "Ahri", "tagLine": "NA1"}}
    )
    feature = make_feature(client, provider="ugg")
    opened = _capture_browser(monkeypatch)

    feature.reveal()

    assert opened[0].startswith("https://u.gg/")


def test_set_provider_rejects_an_unknown_site(monkeypatch):
    monkeypatch.setattr("features.lobby_reveal.save_config", lambda config: None)
    feature = make_feature(StubLCUClient())

    with pytest.raises(ValueError):
        feature.set_provider("nowhere")


def test_a_config_naming_a_dropped_provider_falls_back_instead_of_raising():
    """Config is a user-editable file on disk - a stale value in it must
    not make the feature permanently unusable."""
    client = StubLCUClient()
    feature = make_feature(client)
    feature.config["lobby_reveal"]["provider"] = "some-site-we-dropped"

    assert feature.get_status()["provider"] == "porofessor"


def _capture_browser(monkeypatch):
    opened = []
    monkeypatch.setattr("features.lobby_reveal.webbrowser.open", opened.append)
    return opened
