"""Instalock and AutoBan: the two features that act during champ select.

Both had no tests at all, despite being the ones that touch a live game.
"""
import copy

import pytest

from core.config import DEFAULT_CONFIG
from features.autoban import AutoBan
from features.instalock import Instalock

CHAMPION_SUMMARY = [
    {"id": -1, "name": "None"},
    {"id": 86, "name": "Garen"},
    {"id": 157, "name": "Yasuo"},
]


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="{}"):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


class FakeLCUClient:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def is_league_connected(self):
        return True

    def lcu_request(self, method, endpoint, body=""):
        self.calls.append((method, endpoint, body))
        if endpoint in self.responses:
            return self.responses[endpoint]
        if "champion-summary" in endpoint:
            return FakeResponse(json_data=CHAMPION_SUMMARY)
        return FakeResponse()


@pytest.fixture(params=[(Instalock, "pick"), (AutoBan, "ban")], ids=["instalock", "autoban"])
def feature_and_type(request):
    cls, action_type = request.param
    feature = cls(FakeLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    return feature, action_type


def session_with(action_type, cell_id=3, completed=False, actor=3):
    return {
        "localPlayerCellId": cell_id,
        "actions": [
            [{"id": 10, "actorCellId": 9, "type": action_type, "completed": False}],
            [{"id": 11, "actorCellId": actor, "type": action_type, "completed": completed}],
        ],
    }


def test_finds_only_the_local_players_own_action(feature_and_type):
    feature, action_type = feature_and_type
    feature.enabled = True

    action = feature.find_pending_action(session_with(action_type), cell_id=3)

    assert action["id"] == 11, "must skip another player's action in the same phase"


def test_ignores_an_action_already_completed(feature_and_type):
    feature, action_type = feature_and_type
    feature.enabled = True

    assert feature.find_pending_action(session_with(action_type, completed=True), cell_id=3) is None


def test_ignores_the_other_phase_type(feature_and_type):
    feature, action_type = feature_and_type
    feature.enabled = True
    other = "ban" if action_type == "pick" else "pick"

    assert feature.find_pending_action(session_with(other), cell_id=3) is None


def test_does_nothing_while_disabled(feature_and_type):
    feature, action_type = feature_and_type
    feature.enabled = False

    assert feature.find_pending_action(session_with(action_type), cell_id=3) is None


def test_no_action_without_a_local_cell(feature_and_type):
    feature, action_type = feature_and_type
    feature.enabled = True

    assert feature.find_pending_action(session_with(action_type), cell_id=None) is None


def test_champion_name_lookup_is_case_insensitive(feature_and_type):
    feature, _ = feature_and_type
    feature.update_champion_list()

    assert feature.champ_name_to_id("garen") == 86
    assert feature.champ_name_to_id("GAREN") == 86
    assert feature.champ_name_to_id("Nobody") == -1


def test_setting_an_unknown_champion_is_rejected(feature_and_type):
    feature, _ = feature_and_type

    with pytest.raises(ValueError, match="not found"):
        feature.set_champion("Notachampion")


def test_setting_none_disables_the_feature(feature_and_type):
    feature, _ = feature_and_type
    feature.enabled = True

    assert feature.set_champion("None") == "None"
    assert feature.enabled is False


def test_setting_a_champion_enables_the_feature(feature_and_type, tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature, _ = feature_and_type

    assert feature.set_champion("Yasuo") == "Yasuo"
    assert feature.enabled is True
    assert feature.get_status()["enabled"] is True


def test_locking_sends_the_champion_id_to_champ_select(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    lcu = FakeLCUClient()
    feature = Instalock(lcu, copy.deepcopy(DEFAULT_CONFIG))
    feature.set_champion("Garen")

    feature._lock_champion({"id": 11})

    method, endpoint, body = lcu.calls[-1]
    assert method == "PATCH"
    assert endpoint == "/lol-champ-select/v1/session/actions/11"
    assert body == {"completed": True, "championId": 86}


def test_banning_sends_the_champion_id_to_champ_select(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    lcu = FakeLCUClient()
    feature = AutoBan(lcu, copy.deepcopy(DEFAULT_CONFIG))
    feature.set_champion("Yasuo")

    feature._ban_champion({"id": 11})

    method, endpoint, body = lcu.calls[-1]
    assert method == "PATCH"
    assert endpoint == "/lol-champ-select/v1/session/actions/11"
    assert body == {"completed": True, "championId": 157}


def test_a_rejected_lock_raises(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    lcu = FakeLCUClient(
        responses={"/lol-champ-select/v1/session/actions/11": FakeResponse(status_code=500)}
    )
    feature = Instalock(lcu, copy.deepcopy(DEFAULT_CONFIG))
    feature.set_champion("Garen")

    with pytest.raises(RuntimeError, match="500"):
        feature._lock_champion({"id": 11})
