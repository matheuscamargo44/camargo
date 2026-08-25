"""LiveClientData: the only source for local-player level/champion/game-mode
during a live match. `get_all_game_data` must degrade to None (never raise)
for the normal idle case - the API is only up during an active match, so a
connection refused is the common state, not a fault.
"""
import requests

from core.live_client_data import get_all_game_data, local_player


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


def test_no_match_in_progress_returns_none_without_raising(monkeypatch):
    def fake_get(url, verify=None, timeout=None):
        raise requests.exceptions.ConnectionError("refused")

    import core.live_client_data as live_client_data_module

    monkeypatch.setattr(live_client_data_module.requests, "get", fake_get)

    assert get_all_game_data() is None


def test_a_successful_response_is_parsed(monkeypatch):
    payload = {"gameData": {"gameMode": "KIWI"}, "activePlayer": {"riotId": "camargo#amor"}, "allPlayers": []}

    def fake_get(url, verify=None, timeout=None):
        return FakeResponse(json_data=payload)

    import core.live_client_data as live_client_data_module

    monkeypatch.setattr(live_client_data_module.requests, "get", fake_get)

    assert get_all_game_data() == payload


def test_a_non_200_status_returns_none(monkeypatch):
    def fake_get(url, verify=None, timeout=None):
        return FakeResponse(status_code=404)

    import core.live_client_data as live_client_data_module

    monkeypatch.setattr(live_client_data_module.requests, "get", fake_get)

    assert get_all_game_data() is None


def test_local_player_matches_active_player_by_riot_id():
    data = {
        "activePlayer": {"riotId": "camargo#amor"},
        "allPlayers": [
            {"riotId": "Hanke#vini", "championName": "Malzahar", "level": 5},
            {"riotId": "camargo#amor", "championName": "Ahri", "level": 7},
        ],
    }

    player = local_player(data)

    assert player["championName"] == "Ahri"
    assert player["level"] == 7


def test_local_player_returns_none_when_not_resolvable():
    assert local_player({"activePlayer": {}, "allPlayers": []}) is None
