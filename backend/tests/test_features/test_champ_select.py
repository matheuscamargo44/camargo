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
    {"id": 103, "name": "Ahri"},
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


def test_adding_an_unknown_champion_is_rejected(feature_and_type):
    feature, _ = feature_and_type

    with pytest.raises(ValueError, match="not found"):
        feature.add_champion("Notachampion")


def test_removing_the_last_champion_disables_the_feature(tmp_path, monkeypatch, feature_and_type):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature, _ = feature_and_type
    feature.add_champion("Yasuo")

    assert feature.remove_champion("Yasuo") == []
    assert feature.enabled is False


def test_adding_a_champion_enables_the_feature(tmp_path, monkeypatch, feature_and_type):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature, _ = feature_and_type

    assert feature.add_champion("Yasuo") == ["Yasuo"]
    assert feature.enabled is True
    assert feature.get_status()["enabled"] is True


def test_adding_the_same_champion_twice_does_not_duplicate(tmp_path, monkeypatch, feature_and_type):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature, _ = feature_and_type

    feature.add_champion("Yasuo")
    feature.add_champion("yasuo")  # case-insensitive dedup

    assert feature.champions == ["Yasuo"]


def test_priority_order_is_preserved_across_add_and_remove(tmp_path, monkeypatch, feature_and_type):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature, _ = feature_and_type

    feature.add_champion("Yasuo")
    feature.add_champion("Garen")
    feature.add_champion("Ahri")
    feature.remove_champion("Garen")

    assert feature.champions == ["Yasuo", "Ahri"]


def team_session(taken_champ_ids=(), banned_ids=(), cell_id=3):
    return {
        "localPlayerCellId": cell_id,
        "myTeam": [{"cellId": cell_id, "championId": 0}]
        + [{"cellId": 100 + i, "championId": champ_id} for i, champ_id in enumerate(taken_champ_ids)],
        "bans": {"myTeamBans": list(banned_ids), "theirTeamBans": []},
    }


def test_instalock_resolve_champion_skips_a_champion_a_teammate_already_has(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature = Instalock(FakeLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature.add_champion("Yasuo")
    feature.add_champion("Garen")

    # A teammate already locked Yasuo (id 157): fall through to Garen.
    session = team_session(taken_champ_ids=[157])

    assert feature.resolve_champion(session, cell_id=3) == "Garen"


def test_instalock_resolve_champion_skips_a_banned_champion(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature = Instalock(FakeLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature.add_champion("Yasuo")
    feature.add_champion("Garen")

    session = team_session(banned_ids=[157])  # Yasuo banned

    assert feature.resolve_champion(session, cell_id=3) == "Garen"


def test_instalock_resolve_champion_returns_none_when_the_whole_list_is_unavailable(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature = Instalock(FakeLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature.add_champion("Yasuo")

    session = team_session(taken_champ_ids=[157])

    assert feature.resolve_champion(session, cell_id=3) is None


def lane_session(enemy_champion_id, my_position="TOP", enemy_position="TOP", cell_id=3):
    return {
        "localPlayerCellId": cell_id,
        "myTeam": [{"cellId": cell_id, "championId": 0, "assignedPosition": my_position}],
        "theirTeam": [{"cellId": 200, "championId": enemy_champion_id, "assignedPosition": enemy_position}],
        "bans": {"myTeamBans": [], "theirTeamBans": []},
    }


def _must_not_be_called(*args, **kwargs):
    raise AssertionError("opgg_client.get_lane_matchup should not have been called")


def test_smart_counter_pick_promotes_a_favorable_matchup_over_default_order(tmp_path, monkeypatch):
    import core.config
    import features.instalock as instalock_module

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature = Instalock(FakeLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature.add_champion("Garen")
    feature.add_champion("Yasuo")
    feature.smart_counter_pick = True

    def fake_get_lane_matchup(my_champion, opponent_champion, position):
        favored = "Yasuo" if my_champion == "Yasuo" else "Ahri"
        return {"lane_advantage_champion": favored, "recommended_play_style": "aggressive", "opponent_champion_tip": ""}

    monkeypatch.setattr(instalock_module.opgg_client, "get_lane_matchup", fake_get_lane_matchup)

    session = lane_session(enemy_champion_id=103)  # Ahri, locked top - Garen loses that matchup

    assert feature.resolve_champion(session, cell_id=3) == "Yasuo"


def test_smart_counter_pick_does_nothing_when_disabled(tmp_path, monkeypatch):
    import core.config
    import features.instalock as instalock_module

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature = Instalock(FakeLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature.add_champion("Garen")
    feature.add_champion("Yasuo")
    feature.smart_counter_pick = False
    monkeypatch.setattr(instalock_module.opgg_client, "get_lane_matchup", _must_not_be_called)

    session = lane_session(enemy_champion_id=103)

    assert feature.resolve_champion(session, cell_id=3) == "Garen"


def test_smart_counter_pick_does_nothing_before_the_enemy_laner_locks(tmp_path, monkeypatch):
    import core.config
    import features.instalock as instalock_module

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature = Instalock(FakeLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature.add_champion("Garen")
    feature.smart_counter_pick = True
    monkeypatch.setattr(instalock_module.opgg_client, "get_lane_matchup", _must_not_be_called)

    session = lane_session(enemy_champion_id=0)  # not locked yet

    assert feature.resolve_champion(session, cell_id=3) == "Garen"


def test_smart_counter_pick_falls_back_silently_when_opgg_fails(tmp_path, monkeypatch):
    import core.config
    import features.instalock as instalock_module

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature = Instalock(FakeLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature.add_champion("Garen")
    feature.add_champion("Yasuo")
    feature.smart_counter_pick = True

    def raise_error(*args, **kwargs):
        raise RuntimeError("OP.GG unreachable")

    monkeypatch.setattr(instalock_module.opgg_client, "get_lane_matchup", raise_error)

    session = lane_session(enemy_champion_id=103)

    # A failed lookup must never block locking - falls back to the plain,
    # already-existing priority order.
    assert feature.resolve_champion(session, cell_id=3) == "Garen"


def test_smart_counter_pick_caches_the_matchup_per_champion_pair(tmp_path, monkeypatch):
    import core.config
    import features.instalock as instalock_module

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature = Instalock(FakeLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature.add_champion("Garen")
    feature.smart_counter_pick = True

    calls = []

    def fake_get_lane_matchup(my_champion, opponent_champion, position):
        calls.append((my_champion, opponent_champion, position))
        return {"lane_advantage_champion": "Garen", "recommended_play_style": "aggressive", "opponent_champion_tip": ""}

    monkeypatch.setattr(instalock_module.opgg_client, "get_lane_matchup", fake_get_lane_matchup)

    session = lane_session(enemy_champion_id=103)
    feature.resolve_champion(session, cell_id=3)
    feature.resolve_champion(session, cell_id=3)

    assert len(calls) == 1


def test_autoban_resolve_champion_skips_an_already_banned_champion(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature = AutoBan(FakeLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature.add_champion("Yasuo")
    feature.add_champion("Garen")

    session = {"bans": {"myTeamBans": [], "theirTeamBans": [157]}}  # Yasuo banned by enemy

    assert feature.resolve_champion(session) == "Garen"


def test_autoban_resolve_champion_ignores_teammate_picks(tmp_path, monkeypatch):
    """Unlike Instalock, a teammate locking a champion doesn't stop it from
    being banned — only an existing ban does.
    """
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature = AutoBan(FakeLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature.add_champion("Yasuo")

    session = team_session(taken_champ_ids=[157])  # a teammate has Yasuo, but nothing is banned

    assert feature.resolve_champion(session) == "Yasuo"


def test_locking_sends_the_champion_id_to_champ_select(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    lcu = FakeLCUClient()
    feature = Instalock(lcu, copy.deepcopy(DEFAULT_CONFIG))
    feature.add_champion("Garen")

    feature._lock_champion({"id": 11}, "Garen")

    method, endpoint, body = lcu.calls[-1]
    assert method == "PATCH"
    assert endpoint == "/lol-champ-select/v1/session/actions/11"
    assert body == {"completed": True, "championId": 86}


def test_banning_sends_the_champion_id_to_champ_select(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    lcu = FakeLCUClient()
    feature = AutoBan(lcu, copy.deepcopy(DEFAULT_CONFIG))
    feature.add_champion("Yasuo")

    feature._ban_champion({"id": 11}, "Yasuo")

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
    feature.add_champion("Garen")

    with pytest.raises(RuntimeError, match="500"):
        feature._lock_champion({"id": 11}, "Garen")


def test_get_available_queues_filters_to_curated_currently_enabled_queues(tmp_path, monkeypatch):
    """/lol-game-queues/v1/queues lists every queue Riot has ever defined -
    TFT, custom-lobby duplicates, coop-vs-AI, and rotating modes currently
    toggled off - in the client's own display language. Only a curated,
    currently-enabled, English-labeled subset should reach the picker.
    """
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    lcu = FakeLCUClient(
        responses={
            "/lol-game-queues/v1/queues": FakeResponse(
                json_data=[
                    # Curated, enabled, visible: kept.
                    {"id": 420, "name": "Ranqueada Solo/Duo", "isRanked": True, "isVisible": True, "isEnabled": True},
                    {"id": 1750, "name": "Arena 3x6", "isRanked": False, "isVisible": True, "isEnabled": True},
                    # ARAM has no pick step at all (champion is randomly
                    # assigned) - excluded even though it's visible and
                    # enabled; it's simply not in the curated allowlist.
                    {"id": 450, "name": "ARAM", "isRanked": False, "isVisible": True, "isEnabled": True},
                    # Curated but currently toggled off (a rotating mode not
                    # running right now): excluded.
                    {"id": 1900, "name": "URF", "isRanked": False, "isVisible": True, "isEnabled": False},
                    # Not in the curated allowlist at all (e.g. TFT, a
                    # custom-lobby duplicate, a coop-vs-AI queue): excluded
                    # even though it's visible and enabled.
                    {"id": 1100, "name": "TFT Ranked", "isRanked": True, "isVisible": True, "isEnabled": True},
                    # Custom-lobby id: excluded (not a real key).
                    {"id": -1, "name": "Custom", "isRanked": False, "isVisible": True, "isEnabled": True},
                ]
            )
        }
    )
    feature = Instalock(lcu, copy.deepcopy(DEFAULT_CONFIG))

    assert feature.get_available_queues() == [
        {"id": 1750, "name": "Arena", "is_ranked": False},
        {"id": 420, "name": "Ranked Solo/Duo", "is_ranked": True},
    ]


def test_toggle_mode_adds_and_removes(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    feature = Instalock(FakeLCUClient(), copy.deepcopy(DEFAULT_CONFIG))

    assert feature.toggle_mode(420) == [420]
    assert feature.toggle_mode(450) == [420, 450]
    assert feature.toggle_mode(420) == [450]


def test_current_queue_id_reads_the_gameflow_session(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    lcu = FakeLCUClient(
        responses={"/lol-gameflow/v1/session": FakeResponse(json_data={"gameData": {"queue": {"id": 420}}})}
    )
    feature = Instalock(lcu, copy.deepcopy(DEFAULT_CONFIG))

    assert feature.current_queue_id() == 420


def test_current_queue_id_returns_none_when_unavailable(tmp_path, monkeypatch):
    import core.config

    monkeypatch.setattr(core.config, "CONFIG_PATH", tmp_path / "config.json")
    lcu = FakeLCUClient(responses={"/lol-gameflow/v1/session": FakeResponse(status_code=404, json_data={})})
    feature = Instalock(lcu, copy.deepcopy(DEFAULT_CONFIG))

    assert feature.current_queue_id() is None
