import copy

import pytest

from core.config import DEFAULT_CONFIG
from features.valorant_instalock import ValorantInstalock

AGENT_DIRECTORY = {
    "data": [
        {"displayName": "Jett", "uuid": "add6443a-41bd-e414-f6ad-e58d267f4e95"},
        {"displayName": "Sova", "uuid": "320b2a48-4d9b-a075-30f1-1f93a9b638fa"},
    ]
}


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}

    def json(self):
        return self._json_data


class FakeValorantClient:
    def __init__(self):
        self.calls = []
        self.region = None
        self.agent_directory_response = FakeResponse(json_data=AGENT_DIRECTORY)

    def set_region(self, region):
        self.region = region

    def is_connected(self):
        return True

    def fetch_agent_directory(self):
        return self.agent_directory_response

    def fetch_presence(self):
        raise NotImplementedError

    def pregame_fetch_match(self):
        raise NotImplementedError

    def pregame_select_character(self, agent_uuid):
        self.calls.append(("select", agent_uuid))

    def pregame_lock_character(self, agent_uuid):
        self.calls.append(("lock", agent_uuid))


def make_feature():
    config = copy.deepcopy(DEFAULT_CONFIG)
    valorant = FakeValorantClient()
    events = []
    feature = ValorantInstalock(
        valorant, config, on_event=lambda level, message: events.append((level, message))
    )
    return feature, valorant, events


def presence_with(session_loop_state="PREGAME"):
    return {"matchPresenceData": {"sessionLoopState": session_loop_state}}


def test_toggle_flips_state_and_persists_config():
    feature, _, events = make_feature()

    assert feature.enabled is False
    feature.toggle()

    assert feature.enabled is True
    assert feature.config["valorant_instalock"]["enabled"] is True
    assert events[-1] == ("info", "Valorant Instalock enabled")


def test_agent_name_lookup_is_case_insensitive():
    feature, _, _ = make_feature()
    feature.update_agent_list()

    assert feature.agent_name_to_uuid("jett") == "add6443a-41bd-e414-f6ad-e58d267f4e95"
    assert feature.agent_name_to_uuid("JETT") == "add6443a-41bd-e414-f6ad-e58d267f4e95"
    assert feature.agent_name_to_uuid("Nobody") is None


def test_setting_an_unknown_agent_is_rejected():
    feature, _, _ = make_feature()

    with pytest.raises(ValueError, match="not found"):
        feature.set_agent("Notanagent")


def test_setting_none_disables_the_feature():
    feature, _, _ = make_feature()
    feature.enabled = True

    assert feature.set_agent("None") == "None"
    assert feature.enabled is False


def test_setting_an_agent_enables_the_feature(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature, _, _ = make_feature()

    assert feature.set_agent("Sova") == "Sova"
    assert feature.enabled is True
    assert feature.get_status()["enabled"] is True


def test_set_region_rejects_an_unknown_region():
    feature, _, _ = make_feature()

    with pytest.raises(ValueError, match="Unknown region"):
        feature.set_region("mars")


def test_set_region_pins_the_client_and_config(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature, valorant, _ = make_feature()

    assert feature.set_region("eu") == "eu"
    assert valorant.region == "eu"
    assert feature.config["valorant_instalock"]["region"] == "eu"


def test_set_region_auto_clears_the_override(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature, valorant, _ = make_feature()
    feature.set_region("na")

    assert feature.set_region("auto") == "auto"
    assert valorant.region is None
    assert feature.config["valorant_instalock"]["region"] == ""


def test_find_pending_match_ignores_a_falsy_presence():
    feature, _, _ = make_feature()

    assert feature.find_pending_match(None) is None
    assert feature.find_pending_match({}) is None


def test_find_pending_match_ignores_non_pregame_states():
    feature, _, _ = make_feature()

    assert feature.find_pending_match(presence_with("MENUS")) is None
    assert feature.find_pending_match(presence_with("INGAME")) is None


def test_find_pending_match_returns_the_match_id_during_pregame():
    feature, valorant, _ = make_feature()
    valorant.pregame_fetch_match = lambda: {"ID": "match-1"}

    assert feature.find_pending_match(presence_with()) == "match-1"


def test_find_pending_match_ignores_a_match_already_seen():
    feature, valorant, _ = make_feature()
    valorant.pregame_fetch_match = lambda: {"ID": "match-1"}
    feature._seen_matches.add("match-1")

    assert feature.find_pending_match(presence_with()) is None


def test_lock_agent_selects_and_locks_then_remembers_the_match(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature, valorant, events = make_feature()
    feature.set_agent("Jett")

    feature._lock_agent("match-1")

    assert valorant.calls == [
        ("select", "add6443a-41bd-e414-f6ad-e58d267f4e95"),
        ("lock", "add6443a-41bd-e414-f6ad-e58d267f4e95"),
    ]
    assert "match-1" in feature._seen_matches
    assert events[-1] == ("success", "Locked Jett")


def test_lock_agent_does_nothing_without_a_configured_agent():
    feature, valorant, _ = make_feature()

    feature._lock_agent("match-1")

    assert valorant.calls == []
    assert "match-1" not in feature._seen_matches
